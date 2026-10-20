"""tests/test_pattern_study_extra_20261020.py

The CEO's candle document (2026-10-20) adds claims on top of the first report: Sakata San Zan / San Sen (three mountains / rivers = triple top / bottom),
San Ku (three gaps), Fibonacci 50% retracement, and "volume contracts in a channel and expands on the breakout". The coder draft for these detectors
was rejected by the PM (it compared a price with an index so it never fired, returned on the first match, ignored the breakout price and counted today's
candle in the volume average), so each of those points is pinned here, plus: no look-ahead, and a lesson that says which tests were too rare to judge
and whether an edge agrees with the report.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

sys.path.insert(0, str(Path(__file__).parent.parent / "sultrix_audit"))
import pattern_study as ps


def bar(c, wick=0.2, v=None):
    r = {"o": c, "h": c + wick, "l": c - wick, "c": c}
    if v is not None:
        r["v"] = v
    return r


def line(closes, **kw):
    return [bar(c, **kw) for c in closes]


def test_triple_top_needs_three_equal_peaks_and_a_close_below_the_valleys():
    closes = [90.0] * 50 + [90.0]
    for k in (20, 30, 40):
        closes[k] = 100.0
    closes[50] = 85.0
    rows = line(closes)

    assert "triple_top" in ps.detect_extra(rows, 50)
    assert "triple_top" not in ps.detect_extra(rows[:50] + [bar(95.0)], 50)               # close still above the valleys: not confirmed
    two = list(closes)
    two[20] = 90.0
    assert "triple_top" not in ps.detect_extra(line(two), 50)                               # only two peaks


def test_triple_bottom_is_the_mirror_image():
    closes = [100.0] * 51
    for k in (20, 30, 40):
        closes[k] = 90.0
    closes[50] = 105.0

    assert "triple_bottom" in ps.detect_extra(line(closes), 50) and "triple_top" not in ps.detect_extra(line(closes), 50)


def gapped(n_gaps, direction=1):
    rows, level = line([100.0] * 44), 100.0
    for g in range(n_gaps):
        prev = rows[-1]
        o = prev["h"] + 1.0 if direction > 0 else prev["l"] - 1.0
        c = o + 0.3 * direction
        rows.append({"o": o, "h": max(o, c) + 0.1, "l": min(o, c) - 0.1, "c": c})
        if g < n_gaps - 1:
            rows += [bar(c)] * 3
    return rows


def test_three_gaps_in_the_same_direction_inside_fifteen_candles():
    up, down = gapped(3, 1), gapped(3, -1)

    assert "gaps_up3" in ps.detect_extra(up, len(up) - 1) and "gaps_down3" not in ps.detect_extra(up, len(up) - 1)
    assert "gaps_down3" in ps.detect_extra(down, len(down) - 1)
    two = gapped(2, 1) + [bar(0.0)] * 0
    assert "gaps_up3" not in ps.detect_extra(two + [bar(two[-1]["c"])] * 8, len(two) + 7)    # two gaps, then no gap on the last candle


def test_fibonacci_half_retracement_up_and_down():
    up = line([100.0] * 35 + [102.0 + 2 * k for k in range(10)] + [118.0, 116.0, 114.0, 112.0, 110.0])
    down = line([100.0] * 35 + [98.0 - 2 * k for k in range(10)] + [82.0, 84.0, 86.0, 88.0, 90.0])

    assert "fib50_up" in ps.detect_extra(up, len(up) - 1) and "fib50_down" not in ps.detect_extra(up, len(up) - 1)
    assert "fib50_down" in ps.detect_extra(down, len(down) - 1) and "fib50_up" not in ps.detect_extra(down, len(down) - 1)
    shallow = line([100.0] * 35 + [102.0 + 2 * k for k in range(10)] + [118.0, 117.0, 116.0, 115.0, 114.0])
    assert "fib50_up" not in ps.detect_extra(shallow, len(shallow) - 1)                      # only a 25% pullback


def breakout(v_last, v_base=1000.0, with_v=True):
    rows = line([100.0] * 49, v=v_base if with_v else None)
    last = bar(104.0, v=v_last if with_v else None)
    rows.append(last)
    return rows


def test_breakout_is_split_by_volume_and_the_average_excludes_today():
    assert "breakout_hivol" in ps.detect_extra(breakout(2000.0), 49) and "breakout_lovol" not in ps.detect_extra(breakout(2000.0), 49)
    assert "breakout_lovol" in ps.detect_extra(breakout(500.0), 49) and "breakout_hivol" not in ps.detect_extra(breakout(500.0), 49)
    assert not {"breakout_hivol", "breakout_lovol"} & ps.detect_extra(breakout(0.0, with_v=False), 49)      # forex has no volume
    assert not {"breakout_hivol", "breakout_lovol"} & ps.detect_extra(breakout(900.0, v_base=0.0), 49)        # zero average: no verdict
    flat = line([100.0] * 49, v=1000.0) + [bar(100.0, v=5000.0)]
    assert not {"breakout_hivol", "breakout_lovol"} & ps.detect_extra(flat, 49)                              # big volume but no price breakout


def test_nothing_after_i_is_ever_used():
    closes = [90.0] * 51
    for k in (20, 30, 40):
        closes[k] = 100.0
    closes[50] = 85.0
    rows = line(closes)
    rnd = random.Random(3)
    future = [bar(rnd.uniform(50, 150), v=rnd.uniform(1, 9)) for _ in range(30)]

    assert ps.detect_extra(rows, 50) == ps.detect_extra(rows + future, 50)


def test_short_history_and_missing_keys_give_nothing():
    assert ps.detect_extra(line([100.0] * 30), 29) == set()
    assert ps.detect(line([100.0] * 30), 29) == set()


def walk(seed, n=900):
    rnd = random.Random(seed)
    price, rows = 100.0, []
    for _ in range(n):
        o = price
        price *= 1 + rnd.gauss(0, 0.01)
        rows.append({"o": o, "h": max(o, price) * 1.002, "l": min(o, price) * 0.998, "c": price, "v": 1000 * (1 + rnd.random())})
    return rows


def test_the_lesson_lists_tests_too_rare_to_judge():
    series = {f"S{k}": walk(k) for k in range(6)}

    les = ps.lesson("stocks", series)[0]

    assert isinstance(les["evidence"]["untestable"], list) and les["evidence"]["untestable"]          # gaps are essentially absent in a continuous walk
    assert all(p in les["text"] for p in les["evidence"]["untestable"]) and "Too rare to judge" in les["text"]
    assert "50% retracement" in les["text"] or "agrees" in les["text"]


def test_an_edge_is_labelled_with_whether_it_agrees_with_the_report(monkeypatch):
    series = {f"S{k}": walk(10 + k) for k in range(6)}

    monkeypatch.setattr(ps, "real_edges", lambda res: [("triple_top", 3, 0.02, 5.0)])
    opposite = ps.lesson("crypto", series)[0]["text"]
    monkeypatch.setattr(ps, "real_edges", lambda res: [("triple_top", 3, -0.02, -5.0)])
    agree = ps.lesson("crypto", series)[0]["text"]

    assert "OPPOSITE to the report" in opposite and "agrees with the report" in agree


def test_data_limits_lesson_states_what_the_candles_can_and_cannot_show():
    flat_no_volume = {"EURUSD": [{"o": 1.0, "h": 1.001, "l": 0.999, "c": 1.0, "v": 0.0} for _ in range(300)]}
    series = {f"S{k}": walk(20 + k) for k in range(6)}

    fx = ps.limits_lesson("forex", flat_no_volume)[0]
    st = ps.limits_lesson("stocks", series)[0]

    assert fx["concept"] == "ref_data_limits" and "cannot be used on forex" in fx["text"] and fx["evidence"]["no_volume_share"] == 1.0
    assert "closes overnight" in st["text"] and st["evidence"]["no_volume_share"] == 0.0 and st["confidence"] == "high"
    assert ps.limits_lesson("crypto", {"A": walk(1, 50)}) == [] and ps.limits_lessons(None) == []
    assert {l["market"] for l in ps.limits_lessons({"crypto": series, "forex": flat_no_volume, "stocks": {}})} == {"crypto", "forex"}
