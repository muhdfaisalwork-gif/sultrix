"""performance_report.py

An honest performance report for crypto, forex and stocks, built ONLY from what the database recorded (every closed trade in `fills`, the open
positions Shadow publishes as shadow_<market>_unrealized, and the capital behind each market). Read-only: it opens the database read-only
and changes nothing. Run:  python performance_report.py [--db path\\bot_state.db] [--out report.md]

It never annualises a short period, never adds a return that was not measured, shows forced sales and open positions separately, and ends
with the caveats an investor needs. It is a record of what happened with TEST money, not a promise of what will.
"""
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

MARKETS = ("crypto", "forex", "stocks")
CAPITAL_KEY = {"crypto": "budget_usdt", "stocks": "stocks_budget_usdt", "forex": "forex_equity"}
CAVEATS = (
    "All results are TEST money (exchange testnet, MT5 demo, Alpaca paper): fills on a test venue are not guaranteed on a live one.",
    "The period is short. Returns are cumulative over the days shown and are NOT annualised: a short period cannot be extrapolated.",
    "Capital is the market's CURRENT budget (forex: the demo account equity); a budget that changed during the period flatters or understates earlier days.",
    "Open positions are marked at the last price; they are not realized and can move either way. The 'equity result' adds them to the closed trades.",
    "Forced sales (restart or halt liquidations) are shown separately because they are not strategy decisions.",
    "Nothing here predicts future returns. A grid strategy earns small amounts often and can lose more in rare large moves.",
)


def _market_of(symbol):
    s = str(symbol)
    if "/" in s:
        return "crypto"
    try:
        from sultrix_predictor import market_of
        return market_of(s)
    except Exception:
        return "forex"


def _setting(con, key, default="0"):
    try:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row and row[0] not in (None, "") else default
    except Exception:
        return default


def _num(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _max_drawdown(daily_pnl):
    """Largest peak-to-trough fall of the cumulative closed result, in money. daily_pnl: list of (day, pnl) in date order."""
    cum = peak = worst = 0.0
    for _, p in daily_pnl:
        cum += p
        peak = max(peak, cum)
        worst = max(worst, peak - cum)
    return worst


def market_stats(rows, now=None):
    """rows: [(ts_iso, pnl, kind)] closed trades of ONE market. Returns the statistics dict (no capital yet)."""
    now = now or datetime.now(timezone.utc)
    trades = [(ts, p, k) for ts, p, k in rows if p]
    strat = [p for _, p, k in trades if k != "liquidation"]
    forced = [p for _, p, k in trades if k == "liquidation"]
    wins, losses = [p for p in strat if p > 0], [p for p in strat if p < 0]
    by_day = {}
    for ts, p, _ in trades:
        by_day[ts[:10]] = by_day.get(ts[:10], 0.0) + p
    days = sorted(by_day.items())
    cut = lambda n: (now - timedelta(days=n)).isoformat()
    net = sum(p for _, p, _ in trades)
    return {
        "trades": len(strat), "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(strat), 4) if strat else None,
        "avg_win": round(sum(wins) / len(wins), 4) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 4) if losses else None,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 3) if losses else None,
        "expectancy": round(sum(strat) / len(strat), 4) if strat else None,
        "strategy_net": round(sum(strat), 4), "forced_sales": len(forced), "forced_net": round(sum(forced), 4),
        "realized_net": round(net, 4),
        "net_7d": round(sum(p for ts, p, _ in trades if ts >= cut(7)), 4), "net_30d": round(sum(p for ts, p, _ in trades if ts >= cut(30)), 4),
        "days_active": len(days), "profitable_days": sum(1 for _, v in days if v > 0),
        "best_day": max(days, key=lambda d: d[1]) if days else None, "worst_day": min(days, key=lambda d: d[1]) if days else None,
        "max_drawdown": round(_max_drawdown(days), 4), "first_day": days[0][0] if days else None, "last_day": days[-1][0] if days else None,
    }


def build(db_path, now=None):
    """The full report as a dict. Opens the database read-only."""
    now = now or datetime.now(timezone.utc)
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        by = {m: [] for m in MARKETS}
        for ts, sym, pnl, kind in con.execute("SELECT ts, symbol, pnl, kind FROM fills WHERE side = 'sell' AND pnl IS NOT NULL"):
            by.setdefault(_market_of(sym), []).append((ts, _num(pnl), kind or ""))
        out = {"generated": now.isoformat(timespec="seconds"), "markets": {}, "caveats": list(CAVEATS)}
        for m in MARKETS:
            st = market_stats(by.get(m, []), now)
            open_pnl = _num(_setting(con, f"shadow_{m}_unrealized"))
            capital = _num(_setting(con, CAPITAL_KEY[m]))
            equity = st["realized_net"] + open_pnl
            st.update({"open_pnl": round(open_pnl, 4), "equity_result": round(equity, 4), "capital": round(capital, 2),
                       "roi_pct": round(equity / capital * 100, 3) if capital > 0 else None,
                       "max_drawdown_pct": round(st["max_drawdown"] / capital * 100, 3) if capital > 0 else None})
            out["markets"][m] = st
        tot = lambda k: round(sum(out["markets"][m][k] for m in MARKETS), 4)
        out["total"] = {"realized_net": tot("realized_net"), "open_pnl": tot("open_pnl"), "equity_result": tot("equity_result"), "forced_net": tot("forced_net")}
        return out
    finally:
        con.close()


def _f(x, d=2, sign=True):
    return "n/a" if x is None else (f"{x:+.{d}f}" if sign else f"{x:.{d}f}")


def render(report):
    L = [f"# Sultrix performance report (test money)", "", f"Generated {report['generated']}. Source: the bot database (closed trades + published open positions).", ""]
    L += ["| Market | Capital | Closed trades | Win rate | Avg win | Avg loss | Profit factor | Realized | Open | Equity result | Return on capital | Max drawdown |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in MARKETS:
        s = report["markets"][m]
        wr = "n/a" if s["win_rate"] is None else f"{s['win_rate'] * 100:.1f}%"
        L.append(f"| {m} | {s['capital']:,.0f} | {s['trades']} | {wr} | {_f(s['avg_win'], 3)} | {_f(s['avg_loss'], 3)} | {_f(s['profit_factor'], 2, False)} | "
                 f"{_f(s['realized_net'])} | {_f(s['open_pnl'])} | {_f(s['equity_result'])} | {_f(s['roi_pct'], 2)}% | {_f(s['max_drawdown'], 2, False)} ({_f(s['max_drawdown_pct'], 2, False)}%) |")
    t = report["total"]
    L += ["", f"**Total:** realized {_f(t['realized_net'])}, open {_f(t['open_pnl'])}, equity result {_f(t['equity_result'])}; forced sales (not strategy) {_f(t['forced_net'])}.", ""]
    for m in MARKETS:
        s = report["markets"][m]
        if s["days_active"]:
            L.append(f"- **{m}**: {s['days_active']} active days ({s['first_day']} to {s['last_day']}), {s['profitable_days']} profitable; best day {s['best_day'][0]} {_f(s['best_day'][1])}, "
                     f"worst day {s['worst_day'][0]} {_f(s['worst_day'][1])}; last 7 days {_f(s['net_7d'])}, last 30 days {_f(s['net_30d'])}; expectancy per trade {_f(s['expectancy'], 3)}; "
                     f"{s['forced_sales']} forced sales {_f(s['forced_net'])}.")
    L += ["", "## Read this before quoting any number", ""] + [f"- {c}" for c in report["caveats"]]
    return "\n".join(L) + "\n"


def main(argv):
    db, out = None, None
    args = list(argv[1:])
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
        print(f"written: {out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
