"""pattern_study.py

Tests the candle and trend claims in the CEO's "Historical Market Data and Trends" report (2026-10-20) on REAL daily candles of crypto, forex and
stocks before Sultrix is taught anything: do Three White Soldiers / Three Black Crows, engulfing candles, hammers and shooting stars and the Dow
trend state (higher highs + higher lows) predict the next 1, 3 and 5 days better than the market's own average?

Method (kept strict on purpose, because with ~100 tests some always look good by chance):
  - events are thinned to one per instrument per 5 days, so overlapping windows do not count twice;
  - the edge is the pattern's average forward return MINUS the average forward return of ALL days of the same instruments;
  - an edge only counts when |t| >= T_MIN (3.5, a Bonferroni-style level for ~100 tests) AND it has the same sign in both halves of history;
  - the Sakata claim "a market falls under its own weight" is tested as the skew of daily returns and the size of the average up day vs down day.
Record-only: it produces lessons (concept ref_candle_patterns, one per market) and changes no order. Pure functions; never raise.
"""
import math
import statistics

PATTERNS = ("soldiers", "crows", "engulf_bull", "engulf_bear", "hammer", "shooting_star", "dow_up", "dow_down",
            "triple_top", "triple_bottom", "gaps_up3", "gaps_down3", "fib50_up", "fib50_down", "breakout_hivol", "breakout_lovol")
# What the CEO's candle report (2026-10-20) claims each added pattern does next: +1 price rises, -1 price falls. Used only to say whether a measured edge
# agrees with the claim; the strict test below decides whether there is an edge at all.
CLAIMED = {"triple_top": -1, "triple_bottom": 1, "gaps_up3": -1, "gaps_down3": 1, "fib50_up": 1, "fib50_down": -1, "breakout_hivol": 1}
HORIZONS = (1, 3, 5)
THIN_DAYS = 5
T_MIN = 3.5
SOURCE = "ceo_reports_20261020+history"


def _ok(r):
    try:
        return all(float(r[k]) > 0 for k in ("o", "h", "l", "c"))
    except (KeyError, TypeError, ValueError):
        return False


def _body(r):
    return abs(r["c"] - r["o"])


def _rng(r):
    return r["h"] - r["l"]


def detect(rows, i):
    """Set of pattern names that complete at index i (rows are daily candles with o/h/l/c). Needs 20 candles of history."""
    if i < 20:
        return set()
    r, p = rows[i], rows[i - 1]
    out = set()
    up = lambda x: x["c"] > x["o"]
    dn = lambda x: x["c"] < x["o"]
    strong = lambda x: _rng(x) > 0 and _body(x) >= 0.5 * _rng(x)
    a, b = rows[i - 2], rows[i - 1]
    if all(up(x) and strong(x) for x in (a, b, r)) and a["c"] < b["c"] < r["c"]:
        out.add("soldiers")
    if all(dn(x) and strong(x) for x in (a, b, r)) and a["c"] > b["c"] > r["c"]:
        out.add("crows")
    if dn(p) and up(r) and r["o"] <= p["c"] and r["c"] >= p["o"] and _body(r) > _body(p):
        out.add("engulf_bull")
    if up(p) and dn(r) and r["o"] >= p["c"] and r["c"] <= p["o"] and _body(r) > _body(p):
        out.add("engulf_bear")
    prior = r["c"] / rows[i - 5]["c"] - 1
    body = max(_body(r), 1e-12)
    lower, upper = min(r["o"], r["c"]) - r["l"], r["h"] - max(r["o"], r["c"])
    if prior < -0.03 and lower >= 2 * body and upper <= 0.5 * body:
        out.add("hammer")
    if prior > 0.03 and upper >= 2 * body and lower <= 0.5 * body:
        out.add("shooting_star")
    last, before = rows[i - 9:i + 1], rows[i - 19:i - 9]
    hh = max(x["h"] for x in last) > max(x["h"] for x in before)
    hl = min(x["l"] for x in last) > min(x["l"] for x in before)
    lh = max(x["h"] for x in last) < max(x["h"] for x in before)
    ll = min(x["l"] for x in last) < min(x["l"] for x in before)
    if hh and hl:
        out.add("dow_up")
    if lh and ll:
        out.add("dow_down")
    return out | detect_extra(rows, i)


def _pivots(rows, i, key, sign, span=45, w=3):
    """Indices of confirmed pivots in rows[i-span..i-w]: strictly higher (sign=1) or lower (sign=-1) than the w candles either side, at least 5 candles
    apart. Strict, so a flat stretch of equal highs is not a pivot. Uses nothing after i."""
    out = []
    for j in range(max(w, i - span), i - w + 1):
        if all(sign * (rows[j][key] - rows[k][key]) > 0 for k in range(j - w, j + w + 1) if k != j) and (not out or j - out[-1] >= 5):
            out.append(j)
    return out


def _arg(rows, key, pick, lo, hi):
    return pick(range(max(0, lo), hi + 1), key=lambda k: rows[k][key])


def detect_extra(rows, i):
    """Patterns from the report's Sakata / Dow / Fibonacci / volume claims. Needs 45 candles of history; uses rows[0..i] only; returns every match."""
    if i < 45:
        return set()
    out = set()
    c = rows[i]["c"]
    ph, pl = _pivots(rows, i, "h", 1)[-3:], _pivots(rows, i, "l", -1)[-3:]
    if len(ph) == 3:
        mean = sum(rows[j]["h"] for j in ph) / 3
        if all(abs(rows[j]["h"] / mean - 1) <= 0.03 for j in ph) and c < min(rows[k]["l"] for k in range(ph[0], ph[2] + 1)):
            out.add("triple_top")
    if len(pl) == 3:
        mean = sum(rows[j]["l"] for j in pl) / 3
        if all(abs(rows[j]["l"] / mean - 1) <= 0.03 for j in pl) and c > max(rows[k]["h"] for k in range(pl[0], pl[2] + 1)):
            out.add("triple_bottom")
    ups = [rows[k]["l"] > rows[k - 1]["h"] for k in range(i - 14, i + 1)]
    downs = [rows[k]["h"] < rows[k - 1]["l"] for k in range(i - 14, i + 1)]
    if ups[-1] and sum(ups) >= 3:
        out.add("gaps_up3")
    if downs[-1] and sum(downs) >= 3:
        out.add("gaps_down3")
    hi = _arg(rows, "h", max, i - 20, i - 2)
    lo = _arg(rows, "l", min, i - 40, hi)
    swing = rows[hi]["h"] - rows[lo]["l"]
    if swing > 0 and swing / rows[lo]["l"] >= 0.10 and 0.45 <= (rows[hi]["h"] - c) / swing <= 0.55:
        out.add("fib50_up")
    lo = _arg(rows, "l", min, i - 20, i - 2)
    hi = _arg(rows, "h", max, i - 40, lo)
    swing = rows[hi]["h"] - rows[lo]["l"]
    if swing > 0 and swing / rows[hi]["h"] >= 0.10 and 0.45 <= (c - rows[lo]["l"]) / swing <= 0.55:
        out.add("fib50_down")
    try:
        vols = [float(rows[k]["v"]) for k in range(i - 20, i)]
        v, mean = float(rows[i]["v"]), sum(vols) / len(vols)
    except (KeyError, TypeError, ValueError):
        return out
    if mean > 0 and c > max(rows[k]["h"] for k in range(i - 10, i)):
        if v >= 1.5 * mean:
            out.add("breakout_hivol")
        elif v < mean:
            out.add("breakout_lovol")
    return out


def _fwd(rows, i, h):
    return rows[i + h]["c"] / rows[i]["c"] - 1


def events(series):
    """series: {symbol: rows}. Returns ({pattern: [(symbol, i, half)]}, base) where base[h] = list of all-day forward returns and half is 0/1 (first/second half of history)."""
    ev = {p: [] for p in PATTERNS}
    base = {h: [] for h in HORIZONS}
    for sym, raw in (series or {}).items():
        rows = [r for r in raw if _ok(r)]
        n = len(rows)
        if n < 60:
            continue
        last_at = {p: -10 ** 9 for p in PATTERNS}
        for i in range(20, n - max(HORIZONS)):
            for h in HORIZONS:
                base[h].append(_fwd(rows, i, h))
            for p in detect(rows, i):
                if i - last_at[p] >= THIN_DAYS:
                    last_at[p] = i
                    ev[p].append((sym, i, 0 if i < n / 2 else 1, [_fwd(rows, i, h) for h in HORIZONS]))
    return ev, base


def evaluate(series):
    """{pattern: {h: {n, mean, base, edge, t, hit, base_hit, stable}}} for one market."""
    ev, base = events(series)
    out = {}
    for p, lst in ev.items():
        out[p] = {}
        for k, h in enumerate(HORIZONS):
            xs = [e[3][k] for e in lst]
            if len(xs) < 30:
                out[p][h] = {"n": len(xs), "edge": None, "t": None, "stable": False}
                continue
            b = statistics.fmean(base[h])
            m = statistics.fmean(xs)
            sd = statistics.pstdev(xs) or 1e-12
            t = (m - b) / (sd / math.sqrt(len(xs)))
            halves = [[e[3][k] for e in lst if e[2] == hh] for hh in (0, 1)]
            sign = lambda v: (v > b) - (v < b)
            stable = all(len(x) >= 10 for x in halves) and sign(statistics.fmean(halves[0])) == sign(statistics.fmean(halves[1])) != 0
            out[p][h] = {"n": len(xs), "mean": m, "base": b, "edge": m - b, "t": t, "hit": sum(1 for x in xs if x > 0) / len(xs),
                         "base_hit": sum(1 for x in base[h] if x > 0) / len(base[h]), "stable": stable}
    return out


def asymmetry(series):
    """The Sakata 'a market falls under its own weight' claim: skew of daily returns and average up day / average down day."""
    rs = []
    for raw in (series or {}).values():
        rows = [r for r in raw if _ok(r)]
        rs += [b["c"] / a["c"] - 1 for a, b in zip(rows, rows[1:])]
    if len(rs) < 100:
        return None
    m, sd = statistics.fmean(rs), statistics.pstdev(rs) or 1e-12
    ups, downs = [x for x in rs if x > 0], [-x for x in rs if x < 0]
    return {"skew": sum(((x - m) / sd) ** 3 for x in rs) / len(rs), "up_down_ratio": statistics.fmean(ups) / statistics.fmean(downs), "days": len(rs)}


def real_edges(result):
    """[(pattern, h, edge, t)] that pass the strict test: |t| >= T_MIN, same sign in both halves."""
    return [(p, h, v["edge"], v["t"]) for p, d in result.items() for h, v in d.items() if v.get("edge") is not None and abs(v["t"]) >= T_MIN and v["stable"]]


def lesson(market, series):
    """One lesson per market with the measured numbers; confidence from the amount of data. [] when there is too little."""
    res = evaluate(series)
    tested = [(p, h, v) for p, d in res.items() for h, v in d.items() if v.get("edge") is not None]
    if not tested:
        return []
    edges = real_edges(res)
    best = max(tested, key=lambda x: abs(x[2]["t"]))
    asym = asymmetry(series)
    n_ev = sum(v["n"] for _, _, v in tested if v["n"]) // len(HORIZONS)
    untestable = sorted(p for p, d in res.items() if all(v.get("edge") is None for v in d.values()))
    if edges:
        def agree(p, e):
            return "" if p not in CLAIMED else " agrees with the report" if (e > 0) == (CLAIMED[p] > 0) else " is OPPOSITE to the report's claim"
        txt = "; ".join(f"{p} {h}d: {e * 100:+.2f}% vs the average day (t={t:+.1f}){agree(p, e)}" for p, h, e, t in sorted(edges, key=lambda x: -abs(x[3]))[:3])
        verdict = f"{market}: {len(edges)} of {len(tested)} candle/trend tests passed the strict test ({txt}); treat them as weak, small, and re-check them every quarter."
    else:
        verdict = (f"{market}: NONE of {len(tested)} candle and trend tests (soldiers/crows, engulfing, hammer, shooting star, Dow higher-highs/lower-lows, triple tops/bottoms, "
                   f"three gaps, 50% retracement, volume-confirmed breakouts; over 1, 3 and 5 days) "
                   f"beat the average day under a strict test (needs |t| >= {T_MIN} and the same sign in both halves of history); the closest was {best[0]} {best[1]}d at "
                   f"{best[2]['edge'] * 100:+.2f}% (t={best[2]['t']:+.1f}). Do not trade these patterns on their own; they are context, not signals.")
    if untestable:
        verdict += f" Too rare to judge here (under 30 events): {', '.join(untestable)}."
    if edges:
        verdict += " The instruments move together, so the real significance is lower than the t-values say; this is a lead to watch in shadow mode, not proof."
    if asym:
        verdict += (f" Falls versus rises: skew {asym['skew']:+.2f}, the average up day is {asym['up_down_ratio']:.2f}x the average down day "
                    f"({'down days are larger' if asym['up_down_ratio'] < 0.97 else 'up days are larger' if asym['up_down_ratio'] > 1.03 else 'roughly symmetric'}).")
    return [{"market": market, "concept": "ref_candle_patterns", "text": verdict, "source": SOURCE,
             "confidence": "high" if n_ev >= 400 and len(series) >= 5 else "medium" if n_ev >= 100 else "low",
             "evidence": {"tested": len(tested), "untestable": untestable, "passed": [{"pattern": p, "horizon": h, "edge": e, "t": t} for p, h, e, t in edges],
                          "closest": {"pattern": best[0], "horizon": best[1], "edge": best[2]["edge"], "t": best[2]["t"]}, "asymmetry": asym,
                          "t_min": T_MIN, "instruments": len(series)}}]


def all_lessons(series_by_market):
    out = []
    for m in ("crypto", "forex", "stocks"):
        try:
            out += lesson(m, (series_by_market or {}).get(m) or {})
        except Exception:
            pass
    return out


def limits_lesson(market, series):
    """What the candle data of a market can and cannot show, measured on the same candles (the report's market-structure claims, with numbers):
    volume present or not, how close the open is to the previous close, how often a candle gaps. [] when there is too little data."""
    gaps, strict, no_vol, n = [], 0, 0, 0
    for raw in (series or {}).values():
        rows = [r for r in raw if _ok(r)]
        for a, b in zip(rows, rows[1:]):
            prev = a.get("rc") or a["c"]
            n += 1
            gaps.append(abs(b["o"] / prev - 1) * 1e4)
            strict += b["l"] > a["h"] or b["h"] < a["l"]
            try:
                no_vol += not float(b.get("v") or 0) > 0
            except (TypeError, ValueError):
                no_vol += 1
    if n < 200:
        return []
    med, sg, nv = statistics.median(gaps), strict / n, no_vol / n
    if market == "forex":
        tail = (f"volume is missing in {nv:.0%} of candles (there is no central exchange volume), so volume-confirmed rules cannot be used on forex; "
                f"{sg:.1%} of daily candles gap, which the report says happens at weekend opens.")
    elif market == "stocks":
        tail = (f"the market closes overnight, so the open sits a median {med:.0f} bps from the previous close and {sg:.1%} of days gap completely; "
                f"volume is real (missing in {nv:.1%}).")
    else:
        tail = (f"it trades 24/7, so the open sits a median {med:.1f} bps from the previous close and only {sg:.1%} of candles gap; volume is real (missing in {nv:.1%}). "
                f"The report says funding rate, open interest and forced liquidations are separate feeds that candles do not show.")
    return [{"market": market, "concept": "ref_data_limits", "text": f"{market} candle data ({n} daily candles, {len(series)} instruments): {tail}",
             "source": SOURCE, "confidence": "high" if len(series) >= 5 else "medium",
             "evidence": {"candles": n, "median_open_gap_bps": med, "strict_gap_share": sg, "no_volume_share": nv, "instruments": len(series)}}]


def limits_lessons(series_by_market):
    out = []
    for m in ("crypto", "forex", "stocks"):
        try:
            out += limits_lesson(m, (series_by_market or {}).get(m) or {})
        except Exception:
            pass
    return out
