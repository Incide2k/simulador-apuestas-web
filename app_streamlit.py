import json
import os
import random
import time
from dataclasses import dataclass

import streamlit as st

from conector_football_data import (
    LIGAS_FD,
    calcular_ratings_desde_partidos,
    extraer_jornadas_proximas,
    sincronizar_laliga,
)
from conector_momios import (
    buscar_momio_partido,
    sincronizar_momios_laliga,
)
from modelos_sim import (
    construir_tabla_posiciones,
    evaluar_todos_los_modelos,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UMBRAL_EV_MINIMO = 2.5
TOPE_STAKE_BANCA = 0.10
LIMITE_EXPOSICION_JORNADA = 0.25
DEPOSITO_RAPIDO = 250.0
MERCADOS_DISPONIBLES = ["1", "X", "2", "OVER25", "UNDER25"]
MODELOS_DISPONIBLES = ["Poisson", "Monte Carlo", "Elo-Forma"]


@dataclass
class Equipo:
    nombre: str
    ataque: float
    defensa: float
    ataque_local: float = 1.10
    defensa_local: float = 1.00
    ataque_visitante: float = 1.10
    defensa_visitante: float = 1.00
    forma: float = 1.0


def _asegurar_equipo(equipos: dict[str, Equipo], nombre: str) -> Equipo:
    if nombre not in equipos:
        equipos[nombre] = Equipo(nombre=nombre, ataque=1.10, defensa=1.00, forma=1.0)
    return equipos[nombre]


def _aplicar_momios_externos(momios_mercado: dict, loc_nombre: str, vis_nombre: str, base_act: dict) -> dict:
    m_ext = buscar_momio_partido(momios_mercado, loc_nombre, vis_nombre) or {}
    fuente = m_ext.get("bookmaker") if m_ext.get("cuota_1") else "Modelo"
    return {
        "fuente_cuota": fuente,
        "cuota_1": round(float(m_ext.get("cuota_1") or base_act["cuota_1"]), 2),
        "cuota_x": round(float(m_ext.get("cuota_x") or base_act["cuota_x"]), 2),
        "cuota_2": round(float(m_ext.get("cuota_2") or base_act["cuota_2"]), 2),
        "cuota_over25": round(float(m_ext.get("cuota_over25") or base_act["cuota_over25"]), 2),
        "cuota_under25": round(float(m_ext.get("cuota_under25") or base_act["cuota_under25"]), 2),
    }


def _construir_partidos_jornada(
    encuentros: list[dict],
    equipos: dict[str, Equipo],
    momios_mercado: dict,
    modelo_activo: str,
    md: int,
) -> list[dict]:
    partidos = []
    for idx, enc in enumerate(encuentros, start=1):
        loc = _asegurar_equipo(equipos, enc["local"])
        vis = _asegurar_equipo(equipos, enc["visitante"])
        modelos = evaluar_todos_los_modelos(loc, vis, margen=0.06)
        act = modelos[modelo_activo]
        cuotas = _aplicar_momios_externos(momios_mercado, loc.nombre, vis.nombre, act)
        partidos.append({
            "id": idx,
            "local": loc.nombre,
            "visitante": vis.nombre,
            "fecha": enc.get("fecha", ""),
            "matchday": md,
            "modelos": modelos,
            "xg_local": act["xg_local"],
            "xg_visitante": act["xg_visitante"],
            "prob_1": act["prob_1"],
            "prob_x": act["prob_x"],
            "prob_2": act["prob_2"],
            "prob_over25": act["prob_over25"],
            "prob_under25": act["prob_under25"],
            **cuotas,
        })
    return partidos


def _get_cuota_prob(partido: dict, mercado: str) -> tuple[float, float]:
    mapa_c = {
        "1": partido["cuota_1"],
        "X": partido["cuota_x"],
        "2": partido["cuota_2"],
        "OVER25": partido["cuota_over25"],
        "UNDER25": partido["cuota_under25"],
    }
    mapa_p = {
        "1": partido["prob_1"],
        "X": partido["prob_x"],
        "2": partido["prob_2"],
        "OVER25": partido["prob_over25"],
        "UNDER25": partido["prob_under25"],
    }
    return float(mapa_c[mercado]), float(mapa_p[mercado])


def _ev_pct(partido: dict, mercado: str) -> float:
    cuota, prob = _get_cuota_prob(partido, mercado)
    return ((prob * cuota) - 1.0) * 100.0


def _consenso_y_ventaja(partido: dict, mercado: str) -> tuple[str, bool]:
    cuota, _ = _get_cuota_prob(partido, mercado)
    p_imp = 1.0 / max(1.01, cuota)
    clave = {
        "1": "prob_1",
        "X": "prob_x",
        "2": "prob_2",
        "OVER25": "prob_over25",
        "UNDER25": "prob_under25",
    }[mercado]
    p_pois = partido["modelos"]["Poisson"][clave]
    p_mc = partido["modelos"]["Monte Carlo"][clave]
    p_elo = partido["modelos"]["Elo-Forma"][clave]

    ok_p = p_pois > p_imp
    ok_mc = p_mc > p_imp
    ok_elo = p_elo > p_imp

    if ok_p and ok_mc and ok_elo:
        consenso = "TRIPLE P+MC+ELO"
    elif ok_p and ok_mc:
        consenso = "CONSENSO P+MC"
    elif ok_p or ok_mc or ok_elo:
        consenso = "PARCIAL"
    else:
        consenso = "SIN CONSENSO"

    ev = _ev_pct(partido, mercado)
    ventaja = (ev >= UMBRAL_EV_MINIMO) and ok_p and ok_mc
    return consenso, ventaja


def _mejor_mercado_partido(partido: dict) -> dict:
    mejor = None
    for m in MERCADOS_DISPONIBLES:
        cuota, prob = _get_cuota_prob(partido, m)
        ev = _ev_pct(partido, m)
        consenso, ventaja = _consenso_y_ventaja(partido, m)
        item = {
            "mercado": m,
            "cuota": cuota,
            "prob": prob,
            "ev_pct": ev,
            "consenso": consenso,
            "ventaja": ventaja,
        }
        if mejor is None or item["ev_pct"] > mejor["ev_pct"]:
            mejor = item
    return mejor


def _diagnostico_mercado(partido: dict, mercado: str) -> dict:
    if mercado in ("1", "X", "2"):
        cuotas = [partido["cuota_1"], partido["cuota_x"], partido["cuota_2"]]
    else:
        cuotas = [partido["cuota_over25"], partido["cuota_under25"]]
    suma_imp = sum(1.0 / max(1.01, float(q)) for q in cuotas)
    overround_pct = max(0.0, (suma_imp - 1.0) * 100.0)
    _, prob_mod = _get_cuota_prob(partido, mercado)
    cuota_justa = round(1.0 / max(0.02, min(0.95, prob_mod)), 2)
    return {
        "cuota_justa": cuota_justa,
        "overround_pct": round(overround_pct, 1),
    }


def _kelly_sugerido(banca: float, prob: float, cuota: float, fraccion: float = 0.25) -> float:
    b = cuota - 1.0
    if b <= 0 or banca <= 0:
        return 0.0
    kelly = ((b * prob) - (1.0 - prob)) / b
    if kelly <= 0:
        return 0.0
    return round(min(banca * kelly * fraccion, banca * TOPE_STAKE_BANCA), 2)


def _cargar_liga(codigo_liga: str, forzar_red: bool = False) -> dict:
    meta = LIGAS_FD.get(codigo_liga, LIGAS_FD["PD"])
    paquete = sincronizar_laliga(forzar=forzar_red, codigo_liga=codigo_liga)
    momios = sincronizar_momios_laliga(forzar=forzar_red, sport_key=meta["odds_key"])

    equipos: dict[str, Equipo] = {}
    if paquete:
        ratings = calcular_ratings_desde_partidos(paquete.get("finished", []), factor_decaimiento=0.94)
        for nom, r in ratings.items():
            equipos[nom] = Equipo(
                nombre=nom,
                ataque=r["ataque"],
                defensa=r["defensa"],
                ataque_local=r.get("ataque_local", r["ataque"]),
                defensa_local=r.get("defensa_local", r["defensa"]),
                ataque_visitante=r.get("ataque_visitante", r["ataque"]),
                defensa_visitante=r.get("defensa_visitante", r["defensa"]),
                forma=r["forma"],
            )
        tabla = construir_tabla_posiciones(paquete.get("finished", []))
        jornadas_reales = extraer_jornadas_proximas(paquete.get("upcoming", []))
    else:
        tabla = []
        jornadas_reales = {}

    return {
        "equipos": equipos,
        "momios": momios,
        "tabla": tabla,
        "jornadas_reales": jornadas_reales,
        "lista_jornadas": list(jornadas_reales.keys()),
    }


def _inyectar_estilos():
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2.5rem;
        }
        .card-box {
            background: #171c26;
            border: 1px solid #2a3344;
            border-radius: 10px;
            padding: 14px 16px;
            margin-bottom: 12px;
        }
        .match-row {
            background: #171c26;
            border: 1px solid #263042;
            border-radius: 8px;
            padding: 10px 14px;
            margin-bottom: 8px;
        }
        .match-row-ev {
            background: #14241d;
            border: 1px solid #2f7a55;
            border-radius: 8px;
            padding: 10px 14px;
            margin-bottom: 8px;
        }
        .badge-ev {
            display: inline-block;
            background: #1f6f47;
            color: #d7ffe9;
            font-weight: 700;
            font-size: 0.78rem;
            padding: 2px 8px;
            border-radius: 999px;
            margin-left: 8px;
        }
        .badge-source {
            display: inline-block;
            background: #243047;
            color: #b8c7e0;
            font-size: 0.76rem;
            padding: 2px 8px;
            border-radius: 6px;
            margin-left: 6px;
        }
        .muted-line {
            color: #9aa8be;
            font-size: 0.85rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _init_state():
    ss = st.session_state
    if "banca_inicial" not in ss:
        ss.banca_inicial = 1000.0
        ss.banca = 1000.0
        ss.liga_activa = "PD"
        ss.modelo_activo = "Poisson"
        ss.apuestas_activas = []
        ss.historial_apuestas = []
        ss.jornada_por_liga = {}
        ss.ultimos_resultados = {}
        ss.datos_por_liga = {}
        ss.msg = "Simulador web listo."

    if ss.liga_activa not in ss.datos_por_liga:
        ss.datos_por_liga[ss.liga_activa] = _cargar_liga(ss.liga_activa, forzar_red=False)


st.set_page_config(
    page_title="Simulador de Apuestas — Ligas & Europa",
    page_icon="⚽",
    layout="wide",
)
_inyectar_estilos()
_init_state()
ss = st.session_state

# Encabezado y controles globales
st.markdown("### ⚽ Simulador Cuantitativo de Apuestas — Ligas & Europa")

c_liga, c_mod, c_banca, c_roi, c_dep, c_sync, c_rst = st.columns([2.2, 1.7, 1.4, 1.3, 1.15, 1.15, 1.15])

with c_liga:
    codigos = list(LIGAS_FD.keys())
    nueva_liga = st.selectbox(
        "Competición",
        options=codigos,
        index=codigos.index(ss.liga_activa),
        format_func=lambda k: f"{LIGAS_FD[k]['nombre']} ({k})",
    )
    if nueva_liga != ss.liga_activa:
        ss.liga_activa = nueva_liga
        if ss.liga_activa not in ss.datos_por_liga:
            ss.datos_por_liga[ss.liga_activa] = _cargar_liga(ss.liga_activa, forzar_red=False)
        st.rerun()

with c_mod:
    nuevo_mod = st.selectbox(
        "Modelo activo",
        options=MODELOS_DISPONIBLES,
        index=MODELOS_DISPONIBLES.index(ss.modelo_activo),
    )
    if nuevo_mod != ss.modelo_activo:
        ss.modelo_activo = nuevo_mod
        st.rerun()

roi = ((ss.banca - ss.banca_inicial) / max(1.0, ss.banca_inicial)) * 100.0
c_banca.metric("Banca", f"${ss.banca:,.2f}")
c_roi.metric("ROI", f"{roi:+.2f}%", delta=f"{ss.banca - ss.banca_inicial:+.2f}")

with c_dep:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    if st.button(f"+${int(DEPOSITO_RAPIDO)}", use_container_width=True):
        ss.banca = round(ss.banca + DEPOSITO_RAPIDO, 2)
        ss.banca_inicial = round(ss.banca_inicial + DEPOSITO_RAPIDO, 2)
        ss.msg = f"Depósito +${DEPOSITO_RAPIDO:.2f} aplicado."
        st.rerun()

with c_sync:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    if st.button("Sync API", use_container_width=True):
        ss.datos_por_liga[ss.liga_activa] = _cargar_liga(ss.liga_activa, forzar_red=True)
        ss.msg = f"Sincronizado {ss.liga_activa} desde API/caché."
        st.rerun()

with c_rst:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    if st.button("Reiniciar", use_container_width=True):
        ss.banca_inicial = 1000.0
        ss.banca = 1000.0
        ss.apuestas_activas = []
        ss.historial_apuestas = []
        ss.jornada_por_liga = {}
        ss.ultimos_resultados = {}
        ss.datos_por_liga[ss.liga_activa] = _cargar_liga(ss.liga_activa, forzar_red=False)
        ss.msg = "Sesión reiniciada a $1,000.00."
        st.rerun()

st.info(ss.msg)

datos_liga = ss.datos_por_liga[ss.liga_activa]
lista_j = datos_liga["lista_jornadas"]
j_guardada = ss.jornada_por_liga.get(ss.liga_activa)
idx_j = lista_j.index(j_guardada) if j_guardada in lista_j else 0
jornada_actual = lista_j[idx_j] if lista_j else 1
if lista_j:
    ss.jornada_por_liga[ss.liga_activa] = jornada_actual

encuentros = datos_liga["jornadas_reales"].get(jornada_actual, [])
partidos = _construir_partidos_jornada(
    encuentros,
    datos_liga["equipos"],
    datos_liga["momios"],
    ss.modelo_activo,
    jornada_actual,
)

# Exposición de la jornada actual
riesgo_jornada = sum(
    float(ap.get("monto", 0.0))
    for ap in ss.apuestas_activas
    if ap.get("liga") == ss.liga_activa and ap.get("jornada") == jornada_actual
)
pct_exp = (riesgo_jornada / ss.banca * 100.0) if ss.banca > 0 else 0.0
max_exp = LIMITE_EXPOSICION_JORNADA * 100.0

col_izq, col_der = st.columns([1.65, 1.05], gap="large")

partido_sel = None
with col_izq:
    tab_partidos, tab_tabla, tab_hist = st.tabs(["📋 Partidos", "🏆 Tabla", "📊 Historial"])

    with tab_partidos:
        st.markdown(f"**{LIGAS_FD[ss.liga_activa]['nombre']} — Jornada {jornada_actual}**")
        if not partidos:
            st.warning("No hay partidos próximos cargados para esta competición.")
        else:
            for p in partidos:
                mejor_p = _mejor_mercado_partido(p)
                clase_fila = "match-row-ev" if mejor_p["ventaja"] else "match-row"
                badge_html = (
                    f"<span class='badge-ev'>EV+ {mejor_p['mercado']} {mejor_p['ev_pct']:+.1f}%</span>"
                    if mejor_p["ventaja"]
                    else ""
                )
                st.markdown(
                    f"""
                    <div class='{clase_fila}'>
                        <div><strong>#{p['id']:02d} {p['local']} vs {p['visitante']}</strong>
                        <span class='badge-source'>{p['fuente_cuota']}</span>{badge_html}</div>
                        <div class='muted-line'>1: <strong>{p['cuota_1']:.2f}</strong> ·
                        X: <strong>{p['cuota_x']:.2f}</strong> ·
                        2: <strong>{p['cuota_2']:.2f}</strong> ·
                        O2.5: <strong>{p['cuota_over25']:.2f}</strong> ·
                        U2.5: <strong>{p['cuota_under25']:.2f}</strong></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            sel_idx = st.selectbox(
                "Partido seleccionado para analizar",
                options=list(range(len(partidos))),
                format_func=lambda i: f"#{partidos[i]['id']:02d} {partidos[i]['local']} vs {partidos[i]['visitante']}",
            )
            partido_sel = partidos[sel_idx]

    with tab_tabla:
        if datos_liga["tabla"]:
            st.dataframe(datos_liga["tabla"], use_container_width=True, hide_index=True)
        else:
            st.info("Sin tabla de posiciones disponible.")

    with tab_hist:
        if ss.historial_apuestas:
            ganadas = sum(1 for a in ss.historial_apuestas if a.get("estado") == "GANADA")
            total_h = len(ss.historial_apuestas)
            acc_h = (ganadas / total_h * 100.0) if total_h else 0.0
            m1, m2, m3 = st.columns(3)
            m1.metric("Resueltas", total_h)
            m2.metric("Ganadas", ganadas)
            m3.metric("Acierto", f"{acc_h:.1f}%")

            st.dataframe(ss.historial_apuestas, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar historial JSON",
                data=json.dumps(ss.historial_apuestas, indent=2, ensure_ascii=False),
                file_name=f"historial_{ss.liga_activa}_{int(time.time())}.json",
                mime="application/json",
            )
        else:
            st.info("Aún no hay apuestas resueltas en tu historial.")

with col_der:
    st.markdown("<div class='card-box'>", unsafe_allow_html=True)
    st.markdown("**🔬 Comparativa de Modelos y Ejecución**")

    if partido_sel:
        st.markdown(
            f"<div style='font-size:1.05rem;font-weight:700;margin-bottom:4px;'>"
            f"{partido_sel['local']} vs {partido_sel['visitante']}"
            f"<span class='badge-source'>{partido_sel['fuente_cuota']}</span></div>",
            unsafe_allow_html=True,
        )
        st.caption(
            f"xG ({ss.modelo_activo}): {partido_sel['xg_local']:.2f} - {partido_sel['xg_visitante']:.2f}"
        )

        filas_mod = []
        for nom_m in MODELOS_DISPONIBLES:
            m_dat = partido_sel["modelos"][nom_m]
            filas_mod.append({
                "Modelo": f"▶ {nom_m}" if nom_m == ss.modelo_activo else nom_m,
                "1": f"{m_dat['prob_1'] * 100:.1f}%",
                "X": f"{m_dat['prob_x'] * 100:.1f}%",
                "2": f"{m_dat['prob_2'] * 100:.1f}%",
                "O2.5": f"{m_dat['prob_over25'] * 100:.1f}%",
                "xG": f"{m_dat['xg_local']:.1f}-{m_dat['xg_visitante']:.1f}",
            })
        st.dataframe(filas_mod, use_container_width=True, hide_index=True)

        mercado_sel = st.selectbox("Mercado", options=MERCADOS_DISPONIBLES)
        cuota_sel, prob_sel = _get_cuota_prob(partido_sel, mercado_sel)
        ev_val = _ev_pct(partido_sel, mercado_sel)
        consenso_txt, tiene_ventaja = _consenso_y_ventaja(partido_sel, mercado_sel)
        diag = _diagnostico_mercado(partido_sel, mercado_sel)
        kelly_val = _kelly_sugerido(ss.banca, prob_sel, cuota_sel)

        st.markdown(
            f"<div class='muted-line' style='margin-bottom:8px;'>"
            f"Cuota: <strong>@{cuota_sel:.2f}</strong> · Justa: <strong>@{diag['cuota_justa']:.2f}</strong> · "
            f"Vig: <strong>{diag['overround_pct']:.1f}%</strong><br/>"
            f"EV: <strong>{ev_val:+.1f}%</strong> · <strong>{consenso_txt}</strong> · "
            f"Kelly tope: <strong>${kelly_val:.2f}</strong></div>",
            unsafe_allow_html=True,
        )

        monto_sel = st.number_input(
            "Monto ($)",
            min_value=1.0,
            max_value=max(1.0, ss.banca),
            value=min(25.0, max(1.0, ss.banca)),
            step=5.0,
        )

        b1, b2 = st.columns(2)
        with b1:
            if st.button("Apostar", type="primary", use_container_width=True):
                if ev_val < UMBRAL_EV_MINIMO:
                    ss.msg = f"EV {ev_val:+.1f}% por debajo de +{UMBRAL_EV_MINIMO:.1f}%."
                elif not tiene_ventaja:
                    ss.msg = "Sin consenso P+MC para apostar."
                elif ss.banca < monto_sel:
                    ss.msg = "Saldo insuficiente."
                else:
                    ss.banca = round(ss.banca - monto_sel, 2)
                    ss.apuestas_activas.append({
                        "liga": ss.liga_activa,
                        "jornada": jornada_actual,
                        "modelo": ss.modelo_activo,
                        "partido": f"{partido_sel['local']} vs {partido_sel['visitante']}",
                        "seleccion": mercado_sel,
                        "cuota": cuota_sel,
                        "monto": round(monto_sel, 2),
                        "retorno": round(monto_sel * cuota_sel, 2),
                        "ev_pct": round(ev_val, 2),
                    })
                    ss.msg = f"Apostado ${monto_sel:.2f} a {mercado_sel} @{cuota_sel:.2f}."
                st.rerun()

        with b2:
            if st.button("Simular Jornada", use_container_width=True):
                res_lista = []
                for p in partidos:
                    gl = gv = 0
                    for _ in range(8):
                        if random.random() < (p["xg_local"] / 8.0):
                            gl += 1
                        if random.random() < (p["xg_visitante"] / 8.0):
                            gv += 1
                    res_1x2 = "1" if gl > gv else ("2" if gv > gl else "X")
                    ganadoras = {res_1x2, "OVER25" if (gl + gv) >= 3 else "UNDER25"}
                    res_lista.append(f"{p['local']} {gl}-{gv} {p['visitante']}")

                    restantes = []
                    for ap in ss.apuestas_activas:
                        if ap["partido"] == f"{p['local']} vs {p['visitante']}":
                            gano = ap["seleccion"] in ganadoras
                            pago = ap["retorno"] if gano else 0.0
                            ss.banca = round(ss.banca + pago, 2)
                            ap["estado"] = "GANADA" if gano else "PERDIDA"
                            ap["pago"] = pago
                            ss.historial_apuestas.append(ap)
                        else:
                            restantes.append(ap)
                    ss.apuestas_activas = restantes

                ss.ultimos_resultados[ss.liga_activa] = res_lista
                if idx_j + 1 < len(lista_j):
                    ss.jornada_por_liga[ss.liga_activa] = lista_j[idx_j + 1]
                ss.msg = f"{ss.liga_activa} J{jornada_actual} simulada. Banca: ${ss.banca:.2f}"
                st.rerun()

    st.caption(f"Exposición J{jornada_actual}: ${riesgo_jornada:.2f} ({pct_exp:.1f}% / máx {max_exp:.0f}%)")
    st.markdown("</div>", unsafe_allow_html=True)

    if ss.apuestas_activas:
        st.markdown("**Apuestas activas**")
        st.dataframe(ss.apuestas_activas, use_container_width=True, hide_index=True)
    elif ss.ultimos_resultados.get(ss.liga_activa):
        st.markdown(f"**Últimos resultados ({ss.liga_activa})**")
        for r in ss.ultimos_resultados[ss.liga_activa][:6]:
            st.write(f"• {r}")
