"""tests/test_pattern_study_20261020.py

The CEO shared a report on candles, trends and graphs (2026-10-20) to "teach" the bots. Candle folklore is only worth teaching when the data
agrees, so the pattern study measures each claim on real candles with a strict test. Pinned here: the detectors find the textbook shapes, events
are thinned, the edge is measured against the average day, pure noise passes nothing, a planted real edge IS found, and a lesson per market
carries the numbers.
"""
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

sys.path.insert(0, str(Path(__file__).parent.parent / "sultrix_audit"))
import pattern_study as ps


def candle(o, c, wick=0.2):
    hi, lo = max(o, c) + wick, min(o, c) - wick
    return {"o": o, "h": hi, "l": lo, "c": c}


def flat(n, price=100.0):
    return [candle(price, price + (0.1 if k % 2 else -0.1), 0.3) for k in range(n)]


def test_three_white_soldiers_and_three_black_crows_are_detected():
    up = flat(25) + [candle(100, 103, 0.3), candle(103, 106, 0.3), candle(106, 109, 0.3)]
    down = flat(25) + [candle(100, 97, 0.3), candle(97, 94, 0.3), candle(94, 91, 0.3)]

    assert "soldiers" in ps.detect(up, len(up) - 1) and "crows" not in ps.detect(up, len(up) - 1)
    assert "crows" in ps.detect(down, len(down) - 1)


def test_engulfing_hammer_and_shooting_star():
    base = flat(25)
    bull = base + [candle(100, 98, 0.1), candle(97.5, 100.5, 0.1)]
    bear = base + [candle(100, 102, 0.1), candle(102.5, 99.5, 0.1)]
    hammer = base + [candle(100, 96, 0.1), candle(96, 93.5, 0.1), candle(93.5, 93.8, 0.1)]
    hammer[-1] = {"o": 93.6, "h": 93.85, "l": 90.0, "c": 93.8}                      # small body, long lower wick after a fall
    star = base + [candle(100, 104, 0.1), candle(104, 107, 0.1), {"o": 107.0, "h": 111.0, "l": 106.9, "c": 107.2}]

    assert "engulf_bull" in ps.detect(bull, len(bull) - 1) and "engulf_bear" in ps.detect(bear, len(bear) - 1)
    assert "hammer" in ps.detect(hammer, len(hammer) - 1) and "shooting_star" in ps.detect(star, len(star) - 1)


def test_dow_up_needs_higher_highs_and_higher_lows():
    rows = [candle(100 + k * 0.5, 100.4 + k * 0.5, 0.2) for k in range(40)]

    assert "dow_up" in ps.detect(rows, 39) and "dow_down" not in ps.detect(rows, 39)
    assert ps.detect(rows, 10) == set()                                              # fewer than 20 candles of history


def random_walk(seed, n=900, drift=0.0):
    rnd = random.Random(seed)
    price, rows = 100.0, []
    for _ in range(n):
        o = price
        price *= 1 + rnd.gauss(drift, 0.01)
        hi, lo = max(o, price) * (1 + abs(rnd.gauss(0, 0.002))), min(o, price) * (1 - abs(rnd.gauss(0, 0.002)))
        rows.append({"o": o, "h": hi, "l": lo, "c": price})
    return rows


def test_pure_noise_passes_no_pattern_under_the_strict_test():
    series = {f"S{k}": random_walk(k) for k in range(8)}

    res = ps.evaluate(series)

    assert ps.real_edges(res) == [] and all(v["n"] >= 0 for d in res.values() for v in d.values())


def test_events_are_thinned_to_one_per_five_days_per_instrument():
    rows = flat(25) + [candle(100 + 3 * k, 103 + 3 * k, 0.3) for k in range(12)] + flat(10, 140)

    ev, _ = ps.events({"X": rows})

    idx = [e[1] for e in ev["soldiers"]]
    assert all(b - a >= ps.THIN_DAYS for a, b in zip(idx, idx[1:]))


def test_a_planted_real_edge_is_found():
    rnd = random.Random(7)
    series = {}
    for s in range(10):
        price, rows = 100.0, []
        for i in range(1200):
            o = price
            ret = rnd.gauss(0, 0.01)
            if len(rows) >= 3 and all(r["c"] > r["o"] for r in rows[-3:]) and rows[-3]["c"] < rows[-2]["c"] < rows[-1]["c"]:
                ret += 0.02                                                          # after three rising candles the next day jumps: a planted edge
            price *= 1 + ret
            rows.append({"o": o, "h": max(o, price) * 1.001, "l": min(o, price) * 0.999, "c": price})
        series[f"P{s}"] = rows

    res = ps.evaluate(series)

    edges = {(p, h) for p, h, e, t in ps.real_edges(res)}
    assert ("soldiers", 1) in edges or ("dow_up", 1) in edges


def test_the_lesson_carries_the_numbers_and_says_none_when_none_pass():
    series = {f"S{k}": random_walk(100 + k) for k in range(6)}

    lessons = ps.all_lessons({"crypto": series, "forex": {}, "stocks": series})

    assert {l["market"] for l in lessons} == {"crypto", "stocks"} and all(l["concept"] == "ref_candle_patterns" for l in lessons)
    text = lessons[0]["text"]
    assert "NONE of" in text and "t=" in text and "skew" in text
    assert lessons[0]["evidence"]["passed"] == [] and lessons[0]["evidence"]["tested"] > 0


def test_missing_or_garbage_data_gives_no_lessons_and_no_error():
    assert ps.all_lessons({}) == [] and ps.all_lessons(None) == []
    assert ps.lesson("crypto", {"A": [{"o": "x"}, None, {}]}) == []
    assert ps.asymmetry({"A": []}) is None
