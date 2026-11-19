import json
import math
import os
from dataclasses import dataclass

from conector_football_data import calcular_ratings_desde_partidos
from modelos_sim import evaluar_todos_los_modelos

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_CACHE_FD = os.path.join(BASE_DIR, "cache_laliga_fd.json")


@dataclass
class EquipoRating:
    nombre: str
    ataque: float
    defensa: float
    ataque_local: float
    defensa_local: float
    ataque_visitante: float
    defensa_visitante: float
    forma: float


def _resultado_real(match: dict) -> tuple[str, str] | None:
    if match.get("status") != "FINISHED":
        return None
    loc = (match.get("homeTeam") or {}).get("name")
    vis = (match.get("awayTeam") or {}).get("name")
    ft = ((match.get("score") or {}).get("fullTime")) or {}
    gl = ft.get("home")
    gv = ft.get("away")
    if not loc or not vis or gl is None or gv is None:
        return None

    res_1x2 = "1" if gl > gv else ("2" if gv > gl else "X")
    res_ou = "OVER25" if (gl + gv) >= 3 else "UNDER25"
    return res_1x2, res_ou


def ejecutar_backtest(min_partidos_previos: int = 40, umbral_ev: float = 2.5, stake: float = 25.0):
    if not os.path.exists(RUTA_CACHE_FD):
        print("No se encontró cache_laliga_fd.json. Sincroniza primero con football-data.org.")
        return

    with open(RUTA_CACHE_FD, "r", encoding="utf-8") as f:
        data = json.load(f)

    finished = [
        m for m in (data.get("finished") or [])
        if _resultado_real(m) is not None
    ]
    finished.sort(key=lambda m: (m.get("matchday") or 0, m.get("utcDate", "")))

    if len(finished) <= min_partidos_previos:
        print(f"Pocos partidos finalizados ({len(finished)}). Baja min_partidos_previos para probar.")
        return

    modelos_nombres = ["Poisson", "Monte Carlo", "Elo-Forma"]
    metricas = {
        nombre: {
            "n": 0,
            "aciertos_1x2": 0,
            "brier_1x2": 0.0,
            "logloss_1x2": 0.0,
            "apuestas": 0,
            "ganadas": 0,
            "invertido": 0.0,
            "retorno": 0.0,
        }
        for nombre in modelos_nombres
    }

    for idx in range(min_partidos_previos, len(finished)):
        previos = finished[:idx]
        actual = finished[idx]

        ratings_dict = calcular_ratings_desde_partidos(previos, factor_decaimiento=0.94)
        loc_nom = actual["homeTeam"]["name"]
        vis_nom = actual["awayTeam"]["name"]

        if loc_nom not in ratings_dict or vis_nom not in ratings_dict:
            continue

        rl = ratings_dict[loc_nom]
        rv = ratings_dict[vis_nom]
        loc_eq = EquipoRating(
            loc_nom, rl["ataque"], rl["defensa"],
            rl["ataque_local"], rl["defensa_local"],
            rl["ataque_visitante"], rl["defensa_visitante"],
            rl["forma"],
        )
        vis_eq = EquipoRating(
            vis_nom, rv["ataque"], rv["defensa"],
            rv["ataque_local"], rv["defensa_local"],
            rv["ataque_visitante"], rv["defensa_visitante"],
            rv["forma"],
        )

        res_1x2, _ = _resultado_real(actual)
        y_vec = [
            1.0 if res_1x2 == "1" else 0.0,
            1.0 if res_1x2 == "X" else 0.0,
            1.0 if res_1x2 == "2" else 0.0,
        ]

        evaluaciones = evaluar_todos_los_modelos(loc_eq, vis_eq, margen=0.06)

        for nom in modelos_nombres:
            ev_mod = evaluaciones[nom]
            probs = [ev_mod["prob_1"], ev_mod["prob_x"], ev_mod["prob_2"]]
            # Cuota justa de referencia (1 / prob) para evaluar edge frente a línea limpia
            cuotas_justas = [1.0 / max(0.03, p) for p in probs]
            claves = ["1", "X", "2"]

            m = metricas[nom]
            m["n"] += 1

            idx_max = probs.index(max(probs))
            if claves[idx_max] == res_1x2:
                m["aciertos_1x2"] += 1

            m["brier_1x2"] += sum((p - y) ** 2 for p, y in zip(probs, y_vec))
            p_real = max(1e-6, min(1.0 - 1e-6, probs[claves.index(res_1x2)]))
            m["logloss_1x2"] += -math.log(p_real)

            # Simulación selectiva sobre selecciones con EV >= umbral_ev contra cuota con margen 0.05
            for p, c_justa, k_sel in zip(probs, cuotas_justas, claves):
                cuota_mercado_sim = round(c_justa * 0.95, 2)
                ev_pct = ((p * cuota_mercado_sim) - 1.0) * 100.0
                if ev_pct >= umbral_ev:
                    m["apuestas"] += 1
                    m["invertido"] += stake
                    if k_sel == res_1x2:
                        m["ganadas"] += 1
                        m["retorno"] += stake * cuota_mercado_sim

    print("=" * 84)
    print(f"BACKTESTING INTEGRAL | Desde #{min_partidos_previos + 1} (Total: {len(finished)})")
    print("=" * 84)
    print(f"{'MODELO':12s} | {'N':>4s} | {'ACC 1X2':>7s} | {'BRIER':>7s} | {'LOGLOSS':>7s} | {'APU':>4s} | {'ROI%':>7s}")
    print("-" * 84)

    for nom in modelos_nombres:
        m = metricas[nom]
        if m["n"] == 0:
            continue
        acc = (m["aciertos_1x2"] / m["n"]) * 100.0
        brier = m["brier_1x2"] / m["n"]
        logloss = m["logloss_1x2"] / m["n"]
        roi = (((m["retorno"] - m["invertido"]) / m["invertido"]) * 100.0) if m["invertido"] > 0 else 0.0
        print(
            f"{nom:12s} | {m['n']:4d} | {acc:6.1f}% | {brier:7.4f} | {logloss:7.4f} | {m['apuestas']:4d} | {roi:+6.2f}%"
        )

    print("=" * 84)


if __name__ == "__main__":
    ejecutar_backtest()