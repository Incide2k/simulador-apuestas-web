import math
import random


def _poisson_pmf(k: int, lam: float) -> float:
    return (math.exp(-lam) * (lam ** k)) / math.factorial(k)


def _atk_local(loc) -> float:
    return getattr(loc, "ataque_local", loc.ataque)


def _def_local(loc) -> float:
    return getattr(loc, "defensa_local", loc.defensa)


def _atk_vis(vis) -> float:
    return getattr(vis, "ataque_visitante", vis.ataque)


def _def_vis(vis) -> float:
    return getattr(vis, "defensa_visitante", vis.defensa)


def _ajuste_dixon_coles(gl: int, gv: int, xg_l: float, xg_v: float, rho: float = -0.06) -> float:
    """Ajuste ligero para marcadores bajos (0-0, 1-0, 0-1, 1-1)."""
    if gl == 0 and gv == 0:
        return max(0.5, 1.0 - (xg_l * xg_v * rho))
    if gl == 0 and gv == 1:
        return max(0.5, 1.0 + (xg_l * rho))
    if gl == 1 and gv == 0:
        return max(0.5, 1.0 + (xg_v * rho))
    if gl == 1 and gv == 1:
        return max(0.5, 1.0 - rho)
    return 1.0


def _normalizar_1x2_over(p1: float, px: float, p2: float, p_over: float, margen: float = 0.06) -> dict:
    total = max(1e-9, p1 + px + p2)
    prob_1 = p1 / total
    prob_x = px / total
    prob_2 = p2 / total
    prob_over25 = max(0.03, min(0.95, p_over))
    prob_under25 = max(0.05, 1.0 - prob_over25)

    factor = 1.0 - margen

    def a_cuota(p: float) -> float:
        p_seg = max(0.03, min(0.92, p))
        return round(max(1.08, factor / p_seg), 2)

    return {
        "prob_1": prob_1,
        "prob_x": prob_x,
        "prob_2": prob_2,
        "prob_over25": prob_over25,
        "prob_under25": prob_under25,
        "cuota_1": a_cuota(prob_1),
        "cuota_x": a_cuota(prob_x),
        "cuota_2": a_cuota(prob_2),
        "cuota_over25": a_cuota(prob_over25),
        "cuota_under25": a_cuota(prob_under25),
    }


def modelo_poisson(loc, vis, margen: float = 0.06) -> dict:
    xg_loc = max(0.35, _atk_local(loc) * _def_vis(vis) * loc.forma * 1.12 * 1.05)
    xg_vis = max(0.25, _atk_vis(vis) * _def_local(loc) * vis.forma * 1.00)

    max_g = 7
    p1 = px = p2 = p_over = 0.0
    for gl in range(max_g + 1):
        pl = _poisson_pmf(gl, xg_loc)
        for gv in range(max_g + 1):
            pv = _poisson_pmf(gv, xg_vis)
            tau = _ajuste_dixon_coles(gl, gv, xg_loc, xg_vis, rho=-0.06)
            pc = pl * pv * tau
            if gl > gv:
                p1 += pc
            elif gl == gv:
                px += pc
            else:
                p2 += pc
            if gl + gv >= 3:
                p_over += pc

    base = _normalizar_1x2_over(p1, px, p2, p_over, margen=margen)
    return {
        "modelo": "Poisson",
        "xg_local": round(xg_loc, 2),
        "xg_visitante": round(xg_vis, 2),
        **base,
    }


def modelo_monte_carlo(loc, vis, simulaciones: int = 2500, margen: float = 0.06) -> dict:
    base_xg_loc = max(0.35, _atk_local(loc) * _def_vis(vis) * loc.forma * 1.13 * 1.05)
    base_xg_vis = max(0.25, _atk_vis(vis) * _def_local(loc) * vis.forma * 1.00)

    w1 = wx = w2 = over_cnt = 0
    for _ in range(simulaciones):
        factor_dia_l = random.gauss(1.0, 0.08)
        factor_dia_v = random.gauss(1.0, 0.08)
        lam_l = max(0.20, base_xg_loc * max(0.65, factor_dia_l))
        lam_v = max(0.15, base_xg_vis * max(0.65, factor_dia_v))

        gl = gv = 0
        for _ in range(10):
            if random.random() < (lam_l / 10.0):
                gl += 1
            if random.random() < (lam_v / 10.0):
                gv += 1

        if gl > gv:
            w1 += 1
        elif gv > gl:
            w2 += 1
        else:
            wx += 1

        if gl + gv >= 3:
            over_cnt += 1

    base = _normalizar_1x2_over(
        w1 / simulaciones,
        wx / simulaciones,
        w2 / simulaciones,
        over_cnt / simulaciones,
        margen=margen,
    )
    return {
        "modelo": "Monte Carlo",
        "xg_local": round(base_xg_loc, 2),
        "xg_visitante": round(base_xg_vis, 2),
        **base,
    }


def modelo_elo_forma(loc, vis, margen: float = 0.06) -> dict:
    fuerza_l = (_atk_local(loc) / max(0.5, _def_vis(vis))) * (loc.forma ** 1.6) * 1.08
    fuerza_v = (_atk_vis(vis) / max(0.5, _def_local(loc))) * (vis.forma ** 1.6) * 1.00

    dif = math.log(max(0.2, fuerza_l / max(0.2, fuerza_v)))
    win_l_sin_emp = 1.0 / (1.0 + math.exp(-1.55 * dif))

    equilibrio = 1.0 - min(1.0, abs(win_l_sin_emp - 0.5) * 2.0)
    prob_x = 0.19 + 0.11 * equilibrio
    restante = max(0.05, 1.0 - prob_x)

    prob_1 = restante * win_l_sin_emp
    prob_2 = restante * (1.0 - win_l_sin_emp)

    xg_loc = max(0.35, _atk_local(loc) * _def_vis(vis) * loc.forma * 1.12 * 1.05)
    xg_vis = max(0.25, _atk_vis(vis) * _def_local(loc) * vis.forma * 1.00)
    xg_total = xg_loc + xg_vis
    prob_over25 = max(0.10, min(0.88, 1.0 - _normalizar_over_aprox(xg_total)))

    base = _normalizar_1x2_over(prob_1, prob_x, prob_2, prob_over25, margen=margen)
    return {
        "modelo": "Elo-Forma",
        "xg_local": round(xg_loc, 2),
        "xg_visitante": round(xg_vis, 2),
        **base,
    }


def _normalizar_over_aprox(xg_total: float) -> float:
    lam = max(0.4, xg_total)
    return _poisson_pmf(0, lam) + _poisson_pmf(1, lam) + _poisson_pmf(2, lam)


def evaluar_todos_los_modelos(loc, vis, margen: float = 0.06) -> dict[str, dict]:
    p_res = modelo_poisson(loc, vis, margen=margen)
    mc_res = modelo_monte_carlo(loc, vis, simulaciones=2000, margen=margen)
    elo_res = modelo_elo_forma(loc, vis, margen=margen)
    return {
        "Poisson": p_res,
        "Monte Carlo": mc_res,
        "Elo-Forma": elo_res,
    }


def construir_tabla_posiciones(partidos_finalizados: list[dict]) -> list[dict]:
    tabla = {}

    def aseg(nom: str):
        if nom not in tabla:
            tabla[nom] = {
                "equipo": nom,
                "pj": 0,
                "pg": 0,
                "pe": 0,
                "pp": 0,
                "gf": 0,
                "gc": 0,
                "dg": 0,
                "pts": 0,
            }

    for m in partidos_finalizados or []:
        if m.get("status") != "FINISHED":
            continue
        loc = (m.get("homeTeam") or {}).get("name")
        vis = (m.get("awayTeam") or {}).get("name")
        ft = ((m.get("score") or {}).get("fullTime")) or {}
        gl = ft.get("home")
        gv = ft.get("away")
        if not loc or not vis or gl is None or gv is None:
            continue

        aseg(loc)
        aseg(vis)

        tabla[loc]["pj"] += 1
        tabla[vis]["pj"] += 1
        tabla[loc]["gf"] += gl
        tabla[loc]["gc"] += gv
        tabla[vis]["gf"] += gv
        tabla[vis]["gc"] += gl

        if gl > gv:
            tabla[loc]["pg"] += 1
            tabla[loc]["pts"] += 3
            tabla[vis]["pp"] += 1
        elif gv > gl:
            tabla[vis]["pg"] += 1
            tabla[vis]["pts"] += 3
            tabla[loc]["pp"] += 1
        else:
            tabla[loc]["pe"] += 1
            tabla[vis]["pe"] += 1
            tabla[loc]["pts"] += 1
            tabla[vis]["pts"] += 1

    for fila in tabla.values():
        fila["dg"] = fila["gf"] - fila["gc"]

    return sorted(
        tabla.values(),
        key=lambda x: (x["pts"], x["dg"], x["gf"]),
        reverse=True,
    )