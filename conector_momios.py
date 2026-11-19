import json
import os
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_CACHE_LEGACY = os.path.join(BASE_DIR, "cache_momios_laliga.json")


def _ruta_cache_odds(sport_key: str) -> str:
    safe_key = (sport_key or "soccer_spain_la_liga").replace("/", "_")
    nuevo = os.path.join(BASE_DIR, f"cache_odds_{safe_key}.json")
    if safe_key == "soccer_spain_la_liga" and not os.path.exists(nuevo) and os.path.exists(RUTA_CACHE_LEGACY):
        return RUTA_CACHE_LEGACY
    return nuevo


def _normalizar_nombre(nombre: str) -> str:
    txt = unicodedata.normalize("NFKD", nombre or "").encode("ascii", "ignore").decode("ascii").lower()
    for token in [
        "club atletico de ", "club atletico ", "atletico ", "atl. ",
        "real sociedad de futbol", "real sociedad", "real betis balompie", "real betis",
        "rayo vallecano de madrid", "rayo vallecano", "rcd espanyol de barcelona", "rcd espanyol",
        "rc deportivo la coruna", "deportivo la coruna", "rc celta de vigo", "celta de vigo",
        "real valladolid cf", "real racing club", "racing de santander", "ca osasuna",
        " fc", " cf", " ud", " cd", " sd", " afc", " sc", " as", " ac",
    ]:
        txt = txt.replace(token, " ")
    return " ".join(txt.split())


def _cargar_cache_odds(sport_key: str, max_edad_seg: int = 21600) -> dict | None:
    ruta = _ruta_cache_odds(sport_key)
    if not os.path.exists(ruta):
        return None
    if (time.time() - os.path.getmtime(ruta)) > max_edad_seg:
        return None
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _guardar_cache_odds(data: dict, sport_key: str) -> None:
    safe_key = (sport_key or "soccer_spain_la_liga").replace("/", "_")
    ruta = os.path.join(BASE_DIR, f"cache_odds_{safe_key}.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _parsear_eventos_odds(eventos: list[dict]) -> dict[tuple[str, str], dict]:
    mapa: dict[tuple[str, str], dict] = {}
    for ev in eventos or []:
        home_raw = ev.get("home_team") or ""
        away_raw = ev.get("away_team") or ""
        kl = _normalizar_nombre(home_raw)
        kv = _normalizar_nombre(away_raw)
        if not kl or not kv:
            continue

        bookmakers = ev.get("bookmakers") or []
        if not bookmakers:
            continue

        preferidos = ["pinnacle", "betfair", "bet365", "williamhill", "unibet", "marathonbet"]
        bookmakers_ord = sorted(
            bookmakers,
            key=lambda b: preferidos.index(b.get("key", "")) if b.get("key", "") in preferidos else 999,
        )

        elegido = None
        for bk in bookmakers_ord:
            mercados = {m.get("key"): m for m in (bk.get("markets") or [])}
            if "h2h" in mercados:
                elegido = (bk.get("title") or bk.get("key") or "Mercado", mercados)
                break
        if not elegido:
            continue

        bk_nombre, mercados = elegido
        h2h = mercados.get("h2h") or {}
        totals = mercados.get("totals") or {}

        c1 = cx = c2 = None
        for out in h2h.get("outcomes") or []:
            nom = _normalizar_nombre(out.get("name") or "")
            precio = out.get("price")
            if not precio:
                continue
            if nom == kl or (kl and kl in nom):
                c1 = float(precio)
            elif nom == kv or (kv and kv in nom):
                c2 = float(precio)
            elif "draw" in nom or "empate" in nom or nom == "x":
                cx = float(precio)

        co = cu = None
        for out in totals.get("outcomes") or []:
            punto = out.get("point")
            if punto is not None and abs(float(punto) - 2.5) > 0.05:
                continue
            etiqueta = (out.get("name") or "").lower()
            precio = out.get("price")
            if not precio:
                continue
            if "over" in etiqueta:
                co = float(precio)
            elif "under" in etiqueta:
                cu = float(precio)

        mapa[(kl, kv)] = {
            "bookmaker": bk_nombre,
            "cuota_1": c1,
            "cuota_x": cx,
            "cuota_2": c2,
            "cuota_over25": co,
            "cuota_under25": cu,
        }

    return mapa


def sincronizar_momios_laliga(
    api_key: str | None = None,
    forzar: bool = False,
    sport_key: str = "soccer_spain_la_liga",
) -> dict[tuple[str, str], dict]:
    sk = (sport_key or "soccer_spain_la_liga").strip()
    if not forzar:
        cache = _cargar_cache_odds(sk)
        if cache:
            return _parsear_eventos_odds(cache.get("events") or [])

    token = (api_key or os.environ.get("ODDS_API_KEY", "")).strip()
    if not token or token == "TU_TOKEN_DE_THE_ODDS_API":
        cache_vieja = _cargar_cache_odds(sk, max_edad_seg=10**9)
        return _parsear_eventos_odds((cache_vieja or {}).get("events") or [])

    query = urllib.parse.urlencode({
        "apiKey": token,
        "regions": "eu,uk",
        "markets": "h2h,totals",
        "oddsFormat": "decimal",
    })
    url = f"https://api.the-odds-api.com/v4/sports/{sk}/odds/?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "BetSimMultiLeague/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            eventos = json.loads(resp.read().decode("utf-8"))
        if isinstance(eventos, list):
            _guardar_cache_odds({"actualizado_en": int(time.time()), "events": eventos}, sk)
            return _parsear_eventos_odds(eventos)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[The Odds API] Error en {sk}: {exc}")

    cache_fallback = _cargar_cache_odds(sk, max_edad_seg=10**9)
    return _parsear_eventos_odds((cache_fallback or {}).get("events") or [])


def buscar_momio_partido(
    momios_mercado: dict[tuple[str, str], dict],
    local_nombre: str,
    visitante_nombre: str,
) -> dict | None:
    if not momios_mercado:
        return None
    kl = _normalizar_nombre(local_nombre)
    kv = _normalizar_nombre(visitante_nombre)
    if (kl, kv) in momios_mercado:
        return momios_mercado[(kl, kv)]

    for (ml, mv), datos in momios_mercado.items():
        if (kl and (kl in ml or ml in kl)) and (kv and (kv in mv or mv in kv)):
            return datos
    return None