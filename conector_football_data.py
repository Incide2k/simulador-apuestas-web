import json
import os
import time
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://api.football-data.org/v4/competitions"

LIGAS_FD = {
    "PD": {"nombre": "La Liga", "corto": "La Liga", "odds_key": "soccer_spain_la_liga"},
    "PL": {"nombre": "Premier League", "corto": "Premier", "odds_key": "soccer_epl"},
    "BL1": {"nombre": "Bundesliga", "corto": "Bundesliga", "odds_key": "soccer_germany_bundesliga"},
    "SA": {"nombre": "Serie A", "corto": "Serie A", "odds_key": "soccer_italy_serie_a"},
    "FL1": {"nombre": "Ligue 1", "corto": "Ligue 1", "odds_key": "soccer_france_ligue_one"},
    "CL": {"nombre": "Champions League", "corto": "Champions", "odds_key": "soccer_uefa_champs_league"},
    "EL": {"nombre": "Europa League", "corto": "Europa L.", "odds_key": "soccer_uefa_europa_league"},
    "ECL": {"nombre": "Conference League", "corto": "Conference", "odds_key": "soccer_uefa_europa_conference_league"},
}

RESPALDO_EUROPEO = {
    "CL": {
        "finished": [
            {"status": "FINISHED", "matchday": 1, "utcDate": "2026-09-15T19:00:00Z", "homeTeam": {"name": "Real Madrid CF"}, "awayTeam": {"name": "VfB Stuttgart"}, "score": {"fullTime": {"home": 3, "away": 1}}},
            {"status": "FINISHED", "matchday": 1, "utcDate": "2026-09-16T19:00:00Z", "homeTeam": {"name": "Paris Saint-Germain FC"}, "awayTeam": {"name": "Girona FC"}, "score": {"fullTime": {"home": 1, "away": 0}}},
            {"status": "FINISHED", "matchday": 2, "utcDate": "2026-10-01T19:00:00Z", "homeTeam": {"name": "FC Barcelona"}, "awayTeam": {"name": "BSC Young Boys"}, "score": {"fullTime": {"home": 5, "away": 0}}},
            {"status": "FINISHED", "matchday": 2, "utcDate": "2026-10-02T19:00:00Z", "homeTeam": {"name": "Arsenal FC"}, "awayTeam": {"name": "Paris Saint-Germain FC"}, "score": {"fullTime": {"home": 2, "away": 0}}},
            {"status": "FINISHED", "matchday": 3, "utcDate": "2026-10-22T19:00:00Z", "homeTeam": {"name": "FC Bayern München"}, "awayTeam": {"name": "FC Barcelona"}, "score": {"fullTime": {"home": 4, "away": 1}}},
            {"status": "FINISHED", "matchday": 3, "utcDate": "2026-10-23T19:00:00Z", "homeTeam": {"name": "Liverpool FC"}, "awayTeam": {"name": "RB Leipzig"}, "score": {"fullTime": {"home": 1, "away": 0}}},
        ],
        "upcoming": [
            {"matchday": 4, "utcDate": "2026-11-24T20:00:00Z", "homeTeam": {"name": "FC Barcelona"}, "awayTeam": {"name": "FC Bayern München"}},
            {"matchday": 4, "utcDate": "2026-11-24T20:00:00Z", "homeTeam": {"name": "Real Madrid CF"}, "awayTeam": {"name": "Liverpool FC"}},
            {"matchday": 4, "utcDate": "2026-11-25T20:00:00Z", "homeTeam": {"name": "Arsenal FC"}, "awayTeam": {"name": "VfB Stuttgart"}},
            {"matchday": 4, "utcDate": "2026-11-25T20:00:00Z", "homeTeam": {"name": "Paris Saint-Germain FC"}, "awayTeam": {"name": "RB Leipzig"}},
        ],
    },
    "EL": {
        "finished": [
            {"status": "FINISHED", "matchday": 1, "utcDate": "2026-09-25T19:00:00Z", "homeTeam": {"name": "Athletic Club"}, "awayTeam": {"name": "AZ Alkmaar"}, "score": {"fullTime": {"home": 2, "away": 0}}},
            {"status": "FINISHED", "matchday": 1, "utcDate": "2026-09-25T19:00:00Z", "homeTeam": {"name": "AS Roma"}, "awayTeam": {"name": "Athletic Club"}, "score": {"fullTime": {"home": 1, "away": 1}}},
            {"status": "FINISHED", "matchday": 2, "utcDate": "2026-10-24T19:00:00Z", "homeTeam": {"name": "Tottenham Hotspur FC"}, "awayTeam": {"name": "AZ Alkmaar"}, "score": {"fullTime": {"home": 1, "away": 0}}},
            {"status": "FINISHED", "matchday": 2, "utcDate": "2026-10-24T19:00:00Z", "homeTeam": {"name": "FC Porto"}, "awayTeam": {"name": "AS Roma"}, "score": {"fullTime": {"home": 2, "away": 1}}},
        ],
        "upcoming": [
            {"matchday": 3, "utcDate": "2026-11-26T17:45:00Z", "homeTeam": {"name": "Athletic Club"}, "awayTeam": {"name": "Tottenham Hotspur FC"}},
            {"matchday": 3, "utcDate": "2026-11-26T20:00:00Z", "homeTeam": {"name": "AS Roma"}, "awayTeam": {"name": "FC Porto"}},
            {"matchday": 3, "utcDate": "2026-11-26T20:00:00Z", "homeTeam": {"name": "AZ Alkmaar"}, "awayTeam": {"name": "Real Sociedad de Fútbol"}},
        ],
    },
    "ECL": {
        "finished": [
            {"status": "FINISHED", "matchday": 1, "utcDate": "2026-10-03T19:00:00Z", "homeTeam": {"name": "Real Betis Balompié"}, "awayTeam": {"name": "Legia Warszawa"}, "score": {"fullTime": {"home": 1, "away": 0}}},
            {"status": "FINISHED", "matchday": 1, "utcDate": "2026-10-03T19:00:00Z", "homeTeam": {"name": "ACF Fiorentina"}, "awayTeam": {"name": "The New Saints"}, "score": {"fullTime": {"home": 2, "away": 0}}},
            {"status": "FINISHED", "matchday": 2, "utcDate": "2026-10-24T19:00:00Z", "homeTeam": {"name": "Chelsea FC"}, "awayTeam": {"name": "Real Betis Balompié"}, "score": {"fullTime": {"home": 4, "away": 1}}},
            {"status": "FINISHED", "matchday": 2, "utcDate": "2026-10-24T19:00:00Z", "homeTeam": {"name": "Legia Warszawa"}, "awayTeam": {"name": "ACF Fiorentina"}, "score": {"fullTime": {"home": 0, "away": 2}}},
        ],
        "upcoming": [
            {"matchday": 3, "utcDate": "2026-11-26T20:00:00Z", "homeTeam": {"name": "Real Betis Balompié"}, "awayTeam": {"name": "ACF Fiorentina"}},
            {"matchday": 3, "utcDate": "2026-11-26T20:00:00Z", "homeTeam": {"name": "Chelsea FC"}, "awayTeam": {"name": "Legia Warszawa"}},
        ],
    },
}


def ruta_cache_fd(codigo_liga: str = "PD") -> str:
    cod = (codigo_liga or "PD").strip().upper()
    if cod == "PD":
        legacy = os.path.join(BASE_DIR, "cache_laliga_fd.json")
        nuevo = os.path.join(BASE_DIR, "cache_fd_PD.json")
        return nuevo if os.path.exists(nuevo) else legacy
    return os.path.join(BASE_DIR, f"cache_fd_{cod}.json")


def _peticion_fd(url: str, api_key: str) -> dict | None:
    headers = {
        "X-Auth-Token": api_key.strip(),
        "User-Agent": "BetSimMultiLeague/1.0",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detalle = ""
        try:
            detalle = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            pass
        print(f"[Football-Data] HTTP {exc.code} en {url}: {detalle}")
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[Football-Data] Error de red en {url}: {exc}")
        return None


def cargar_cache_fd(codigo_liga: str = "PD", max_edad_seg: int = 21600) -> dict | None:
    ruta = ruta_cache_fd(codigo_liga)
    if not os.path.exists(ruta):
        return None
    if (time.time() - os.path.getmtime(ruta)) > max_edad_seg:
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def guardar_cache_fd(data: dict, codigo_liga: str = "PD") -> None:
    cod = (codigo_liga or "PD").strip().upper()
    ruta = os.path.join(BASE_DIR, f"cache_fd_{cod}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def sincronizar_laliga(
    api_key: str | None = None,
    forzar: bool = False,
    codigo_liga: str = "PD",
) -> dict | None:
    cod = (codigo_liga or "PD").strip().upper()
    if not forzar:
        cache = cargar_cache_fd(cod)
        if cache:
            return cache

    token = (api_key or os.environ.get("LALIGA_API_KEY", "")).strip()
    finalizados = None
    proximos_unicos = []

    if token and token != "TU_TOKEN_DE_FOOTBALL_DATA":
        base_comp = f"{BASE_URL}/{cod}/matches"
        finalizados = _peticion_fd(f"{base_comp}?status=FINISHED", token)
        timed = _peticion_fd(f"{base_comp}?status=TIMED", token)
        scheduled = _peticion_fd(f"{base_comp}?status=SCHEDULED", token)

        proximos_lista = []
        for bloque in (timed, scheduled):
            if bloque and isinstance(bloque.get("matches"), list):
                proximos_lista.extend(bloque["matches"])

        vistos_ids = set()
        for m in proximos_lista:
            mid = m.get("id")
            if mid is not None and mid in vistos_ids:
                continue
            if mid is not None:
                vistos_ids.add(mid)
            proximos_unicos.append(m)

    fin_lista = (finalizados or {}).get("matches") if finalizados else None
    if fin_lista or proximos_unicos:
        paquete = {
            "liga": cod,
            "fuente": "football-data.org",
            "actualizado_en": int(time.time()),
            "finished": fin_lista or [],
            "upcoming": proximos_unicos,
        }
        guardar_cache_fd(paquete, cod)
        return paquete

    cache_previa = cargar_cache_fd(cod, max_edad_seg=10**9)
    if cache_previa:
        return cache_previa

    if cod in RESPALDO_EUROPEO:
        paquete = {
            "liga": cod,
            "fuente": "respaldo_europeo",
            "actualizado_en": int(time.time()),
            "finished": RESPALDO_EUROPEO[cod]["finished"],
            "upcoming": RESPALDO_EUROPEO[cod]["upcoming"],
        }
        guardar_cache_fd(paquete, cod)
        return paquete

    return None


def calcular_ratings_desde_partidos(
    partidos_finalizados: list[dict],
    factor_decaimiento: float = 0.94,
) -> dict[str, dict]:
    validos = []
    for m in partidos_finalizados or []:
        if m.get("status") != "FINISHED":
            continue
        loc = (m.get("homeTeam") or {}).get("name")
        vis = (m.get("awayTeam") or {}).get("name")
        ft = ((m.get("score") or {}).get("fullTime")) or {}
        gl = ft.get("home")
        gv = ft.get("away")
        if loc and vis and gl is not None and gv is not None:
            validos.append((m, loc, vis, int(gl), int(gv)))

    validos.sort(key=lambda item: (item[0].get("matchday") or 0, item[0].get("utcDate", "")))
    total_partidos = len(validos)
    if total_partidos == 0:
        return {}

    stats = {}

    def aseg_equipo(nombre: str):
        if nombre not in stats:
            stats[nombre] = {
                "w_gf": 0.0, "w_gc": 0.0, "w_pj": 0.0,
                "w_gf_h": 0.0, "w_gc_h": 0.0, "w_pj_h": 0.0,
                "w_gf_a": 0.0, "w_gc_a": 0.0, "w_pj_a": 0.0,
                "pj_real": 0,
                "recientes_pesados": [],
            }

    for idx, (_, loc, vis, gl, gv) in enumerate(validos):
        distancia = max(0, (total_partidos - 1) - idx)
        peso = max(0.15, factor_decaimiento ** distancia)

        aseg_equipo(loc)
        aseg_equipo(vis)

        stats[loc]["w_gf"] += gl * peso
        stats[loc]["w_gc"] += gv * peso
        stats[loc]["w_pj"] += peso
        stats[loc]["w_gf_h"] += gl * peso
        stats[loc]["w_gc_h"] += gv * peso
        stats[loc]["w_pj_h"] += peso
        stats[loc]["pj_real"] += 1

        stats[vis]["w_gf"] += gv * peso
        stats[vis]["w_gc"] += gl * peso
        stats[vis]["w_pj"] += peso
        stats[vis]["w_gf_a"] += gv * peso
        stats[vis]["w_gc_a"] += gl * peso
        stats[vis]["w_pj_a"] += peso
        stats[vis]["pj_real"] += 1

        if gl > gv:
            pts_l, pts_v = 3.0, 0.0
        elif gv > gl:
            pts_l, pts_v = 0.0, 3.0
        else:
            pts_l, pts_v = 1.0, 1.0

        stats[loc]["recientes_pesados"].append((pts_l, peso))
        stats[vis]["recientes_pesados"].append((pts_v, peso))

    equipos_con_pj = [d for d in stats.values() if d["w_pj"] > 0]
    if not equipos_con_pj:
        return {}

    prom_gol_liga = sum(d["w_gf"] for d in equipos_con_pj) / sum(d["w_pj"] for d in equipos_con_pj)
    prom_gol_liga = max(0.6, prom_gol_liga)

    ratings = {}
    for nombre, d in stats.items():
        w_pj = max(1e-6, d["w_pj"])
        ataque = max(0.65, min(2.35, (d["w_gf"] / w_pj) / prom_gol_liga))
        defensa = max(0.65, min(1.45, (d["w_gc"] / w_pj) / prom_gol_liga))

        if d["w_pj_h"] > 1e-6:
            atk_h_raw = max(0.60, min(2.50, (d["w_gf_h"] / d["w_pj_h"]) / prom_gol_liga))
            def_h_raw = max(0.60, min(1.55, (d["w_gc_h"] / d["w_pj_h"]) / prom_gol_liga))
            ataque_local = 0.70 * atk_h_raw + 0.30 * ataque
            defensa_local = 0.70 * def_h_raw + 0.30 * defensa
        else:
            ataque_local = ataque
            defensa_local = defensa

        if d["w_pj_a"] > 1e-6:
            atk_a_raw = max(0.60, min(2.50, (d["w_gf_a"] / d["w_pj_a"]) / prom_gol_liga))
            def_a_raw = max(0.60, min(1.55, (d["w_gc_a"] / d["w_pj_a"]) / prom_gol_liga))
            ataque_visitante = 0.70 * atk_a_raw + 0.30 * ataque
            defensa_visitante = 0.70 * def_a_raw + 0.30 * defensa
        else:
            ataque_visitante = ataque
            defensa_visitante = defensa

        ultimos_5 = d["recientes_pesados"][-5:]
        if ultimos_5:
            suma_pesos = sum(p for _, p in ultimos_5)
            prom_pts = sum(pts * p for pts, p in ultimos_5) / max(1e-6, suma_pesos)
            forma = max(0.86, min(1.14, 0.85 + 0.15 * (prom_pts / 1.5)))
        else:
            forma = 1.0

        ratings[nombre] = {
            "ataque": round(ataque, 3),
            "defensa": round(defensa, 3),
            "ataque_local": round(ataque_local, 3),
            "defensa_local": round(defensa_local, 3),
            "ataque_visitante": round(ataque_visitante, 3),
            "defensa_visitante": round(defensa_visitante, 3),
            "forma": round(forma, 3),
            "pj": d["pj_real"],
        }

    return ratings


def extraer_jornadas_proximas(partidos_proximos: list[dict]) -> dict[int, list[dict]]:
    ordenados = sorted(partidos_proximos, key=lambda m: (m.get("matchday") or 999, m.get("utcDate", "")))
    jornadas: dict[int, list[dict]] = {}

    for m in ordenados:
        loc = (m.get("homeTeam") or {}).get("name")
        vis = (m.get("awayTeam") or {}).get("name")
        if not loc or not vis:
            continue
        md = m.get("matchday")
        if not isinstance(md, int):
            md = 1
        fecha = (m.get("utcDate") or "")[:16].replace("T", " ")
        jornadas.setdefault(md, []).append({
            "local": loc,
            "visitante": vis,
            "fecha": fecha,
            "matchday": md,
        })

    return dict(sorted(jornadas.items(), key=lambda item: item[0]))