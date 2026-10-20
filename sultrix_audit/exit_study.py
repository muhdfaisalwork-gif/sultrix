"""exit_study.py

Record-only study for ALL THREE markets: "what would a trailing exit have earned on our real winning lots instead of the fixed take-profit?"
(CEO, 2026-10-20: "we sell and then it goes up"). Nothing here places an order or changes a setting.

For every closed winning lot (entry price/time, exit price/time, profit) the study keeps the entry and the take-profit level exactly as they
were, but lets the lot run after the take-profit is reached and sells when the price falls `trail` below the highest price since then
(or after `max_hold_days`, or at the last price). Fills are strictly PESSIMISTIC: within a candle the low is assumed to come before the high,
and a candle that opens through the stop fills at its open. Losing lots keep their real result (a trailing exit only changes winners).
The hypothetical profit is the real profit scaled by (hypothetical move / real move) from the entry, so it needs no contract sizes.

Lot sources: crypto and stocks are rebuilt from the `fills` table (first-in-first-out per symbol); forex from the broker's own deal history
(opening + closing deal of each position, read-only). Candles: Binance 1h (crypto), Yahoo 1h (stocks), MT5 H1 (forex).
Run:  python exit_study.py [--db path\\bot_state.db] [--out file.md]
"""
import json
import sqlite3
import sys
import time
import urllib.request
from datetime import datetime, timezone

TRAILS = (0.01, 0.02, 0.04)
REL_TRAILS = (0.25, 0.5, 1.0)
MAX_HOLD_DAYS = 7.0
MARKETS = ("crypto", "forex", "stocks")


def _ts(iso):
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()


def lots_from_fills(rows):
    """rows: [(ts_iso, symbol, side, price, amount, pnl)] in time order -> closed lots [{symbol, entry_ts, entry, exit_ts, exit, pnl, long}].
    Each sell closes the oldest unsold buy of that symbol (first in, first out). Sells with no buy before them are skipped."""
    open_buys, lots = {}, []
    for ts, sym, side, price, amount, pnl in rows:
        try:
            price = float(price)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        if side == "buy":
            open_buys.setdefault(sym, []).append((_ts(ts), price))
        elif side == "sell" and pnl:
            q = open_buys.get(sym)
            if q:
                e_ts, e_px = q.pop(0)
                lots.append({"symbol": sym, "entry_ts": e_ts, "entry": e_px, "exit_ts": _ts(ts), "exit": price, "pnl": float(pnl), "long": True})
    return lots


def lots_from_deals(deals, is_in, is_out, is_buy):
    """Broker deals (objects with position_id, time, price, profit, type, entry) -> closed lots. The callables tell an opening deal, a closing
    deal and a buy deal apart, so this works with the MetaTrader5 constants or with test doubles."""
    opens, lots = {}, []
    for d in sorted(deals, key=lambda x: x.time):
        if is_in(d):
            opens[d.position_id] = d
        elif is_out(d) and d.position_id in opens:
            o = opens.pop(d.position_id)
            lots.append({"symbol": d.symbol, "entry_ts": float(o.time), "entry": float(o.price), "exit_ts": float(d.time), "exit": float(d.price),
                         "pnl": float(d.profit), "long": bool(is_buy(o))})
    return lots


def simulate(lot, candles, trail, max_hold_days=MAX_HOLD_DAYS, relative=False):
    """Hypothetical profit of one lot with a trailing exit. candles: [(ts, open, high, low, close)] in time order. A losing lot is returned unchanged.
    relative=True makes `trail` a fraction of the lot's own gain (0.5 = give back at most half of the take-profit move from the best price), so the
    stop is never wider than the room the take-profit gave."""
    if lot["pnl"] <= 0:
        return lot["pnl"]
    sign = 1.0 if lot["long"] else -1.0
    real_move = sign * (lot["exit"] - lot["entry"])
    if real_move <= 0:
        return lot["pnl"]
    if relative:
        trail = trail * real_move / lot["entry"]
    end = lot["exit_ts"] + max_hold_days * 86400
    bars = [c for c in candles if lot["exit_ts"] - 3600 < c[0] <= end]
    if not bars:
        return lot["pnl"]
    # the trailing stop follows the best price since the take-profit level was reached (long: highest high, short: lowest low)
    best = lot["exit"]
    out = None
    for ts, o, h, l, c in bars:
        stop = best * (1 - trail) if lot["long"] else best * (1 + trail)
        if lot["long"]:
            if o <= stop:
                out = o
                break
            if l <= stop:
                out = stop
                break
            best = max(best, h)
        else:
            if o >= stop:
                out = o
                break
            if h >= stop:
                out = stop
                break
            best = min(best, l)
    if out is None:
        out = bars[-1][4]
    # never claim less than the stop's own level protects, and never more than the best price seen (a fill cannot beat the extreme)
    hyp_move = sign * (out - lot["entry"])
    return lot["pnl"] * (hyp_move / real_move)


def compare(lots, candles_by_symbol, trails=TRAILS, rel_trails=REL_TRAILS):
    """Per trail: real net of all lots vs hypothetical net; counts of winners helped / hurt. Absolute trails (percent of price) and gain-relative ones."""
    out = {"lots": len(lots), "real_net": round(sum(l["pnl"] for l in lots), 4), "winners": sum(1 for l in lots if l["pnl"] > 0), "trails": {}}
    for t, relative in [(x, False) for x in trails] + [(x, True) for x in rel_trails]:
        hyp = helped = hurt = 0
        total = 0.0
        for l in lots:
            h = simulate(l, candles_by_symbol.get(l["symbol"], []), t, relative=relative)
            total += h
            if l["pnl"] > 0:
                d = h - l["pnl"]
                helped += d > 1e-12
                hurt += d < -1e-12
        out["trails"][(f"{int(t * 100)}% of the gain" if relative else f"{int(t * 100)}% of price")] = {"hypothetical_net": round(total, 4), "difference": round(total - out["real_net"], 4), "winners_helped": helped, "winners_hurt": hurt}
    return out


# ── candles (network; every function returns [] on any failure) ───────────────────────────────────────────────────────

def _get(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def candles_binance(symbol, start_ts, end_ts):
    try:
        sym, rows, t = symbol.replace("/", ""), [], int(start_ts * 1000)
        while t < end_ts * 1000 and len(rows) < 6000:
            k = _get(f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1h&startTime={t}&limit=1000")
            if not k:
                break
            rows += [(x[0] / 1000.0, float(x[1]), float(x[2]), float(x[3]), float(x[4])) for x in k]
            t = int(k[-1][0]) + 3600000
            if len(k) < 1000:
                break
        return rows
    except Exception:
        return []


def candles_yahoo(symbol, start_ts, end_ts):
    try:
        d = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1h&period1={int(start_ts)}&period2={int(end_ts)}")["chart"]["result"][0]
        q = d["indicators"]["quote"][0]
        return [(t, q["open"][i], q["high"][i], q["low"][i], q["close"][i]) for i, t in enumerate(d["timestamp"]) if None not in (q["open"][i], q["high"][i], q["low"][i], q["close"][i])]
    except Exception:
        return []


def forex_from_mt5(frm, to, magic=None):
    """(lots, candles_by_symbol) from the running MT5 terminal's own history. ([], {}) when MT5 is unavailable. Read-only."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return [], {}
        try:
            deals = [d for d in (mt5.history_deals_get(frm, to) or []) if (magic is None or d.magic == magic)]
            lots = lots_from_deals(deals, lambda d: d.entry == mt5.DEAL_ENTRY_IN, lambda d: d.entry == mt5.DEAL_ENTRY_OUT, lambda d: d.type == mt5.DEAL_TYPE_BUY)
            candles = {}
            for s in {l["symbol"] for l in lots}:
                try:
                    mt5.symbol_select(s, True)
                    lo = min(l["entry_ts"] for l in lots if l["symbol"] == s)
                    bars = mt5.copy_rates_range(s, mt5.TIMEFRAME_H1, datetime.fromtimestamp(lo, timezone.utc), datetime.fromtimestamp(time.time(), timezone.utc))
                    candles[s] = [(float(b["time"]), float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])) for b in (bars if bars is not None else [])]
                except Exception:
                    candles[s] = []
            return lots, candles
        finally:
            mt5.shutdown()
    except Exception:
        return [], {}


def build(db_path, trails=TRAILS):
    """The study for all three markets as a dict (network + read-only DB/MT5)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        rows = con.execute("SELECT ts, symbol, side, price, amount, pnl FROM fills ORDER BY ts").fetchall()
    finally:
        con.close()
    try:
        from sultrix_predictor import market_of
    except Exception:
        market_of = lambda s: "crypto" if "/" in str(s) else "stocks"
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "markets": {}, "method": __doc__.split("\n\n")[1].strip()}
    for m in ("crypto", "stocks"):
        lots = lots_from_fills([r for r in rows if market_of(r[1]) == m])
        cb = {}
        for s in {l["symbol"] for l in lots}:
            lo = min(l["exit_ts"] for l in lots if l["symbol"] == s)
            hi = max(l["exit_ts"] for l in lots if l["symbol"] == s) + MAX_HOLD_DAYS * 86400
            cb[s] = candles_binance(s, lo, min(hi, time.time())) if m == "crypto" else candles_yahoo(s, lo, min(hi, time.time()))
        out["markets"][m] = compare(lots, cb, trails)
    first = min((_ts(r[0]) for r in rows if market_of(r[1]) == "forex"), default=time.time() - 30 * 86400)
    flots, fcandles = forex_from_mt5(datetime.fromtimestamp(first - 86400, timezone.utc), datetime.fromtimestamp(time.time() + 3600, timezone.utc))
    out["markets"]["forex"] = compare(flots, fcandles, trails) if flots else {"lots": 0, "note": "MT5 history not available from this process"}
    return out


def render(study):
    L = ["# Trailing-exit shadow study (record-only, test money)", "", f"Generated {study['generated']}.", "", study["method"], ""]
    keys = next((list(s["trails"]) for s in study["markets"].values() if s.get("lots")), [])
    L += ["| Market | Closed lots | Winners | Real net | " + " | ".join(f"Trail {k}: net (vs real) helped/hurt" for k in keys) + " |",
          "|---|---|---|---|" + "---|" * len(keys)]
    for m in MARKETS:
        s = study["markets"].get(m, {})
        if not s.get("lots"):
            L.append(f"| {m} | 0 | - | - | " + " | ".join("n/a" for _ in keys) + " |")
            continue
        cells = [f"{v['hypothetical_net']:+.2f} ({v['difference']:+.2f}) {v['winners_helped']}/{v['winners_hurt']}" for v in s["trails"].values()]
        L.append(f"| {m} | {s['lots']} | {s['winners']} | {s['real_net']:+.2f} | " + " | ".join(cells) + " |")
    L += ["", "Reading it: a positive difference means letting winners run with that trailing stop would have beaten the fixed take-profit on these real lots.",
          "Caveats: short history; fills are pessimistic but still modelled; the trailing stop was never live. This is evidence to decide on, not a change.", ""]
    return "\n".join(L)


def main(argv):
    db, out, args = None, None, list(argv[1:])
    while args:
        a = args.pop(0)
        if a == "--db" and args:
            db = args.pop(0)
        elif a == "--out" and args:
            out = args.pop(0)
    if not db:
        try:
            import db_writer
            db = str(db_writer.DB_PATH)
        except Exception:
            print(__doc__)
            return 2
    text = render(build(db))
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print("written:", out)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
