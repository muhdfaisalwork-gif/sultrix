"""truth_check.py

Compares what Sultrix BELIEVES it earned with what the broker's own books say. Added 2026-10-20 after the MT5 account (started with a 50,000
deposit) showed -147 while the database said -54: every monitor, the council, the lessons and the evolution engine read the same `fills` table,
so a table that is missing deals fools all of them, and nothing compared it with an independent source.

Forex: the MT5 balance minus the deposits is the realized result according to the broker; the database total must match it to within a few
dollars (swap/commission). A bigger gap is reported as MISMATCH with the size of the hole. Read-only; it places and changes nothing.
Run:  python truth_check.py --db <bot_state.db>        (prints one line per market it can check)
Crypto and stocks need their exchange/broker account inside the running bot and are listed as NOT CHECKED here (next build).
"""
import sqlite3
import sys

TOLERANCE = 2.0


def forex_broker_result(mt5):
    """Realized result according to the broker = balance - net deposits. None when the terminal cannot be read."""
    try:
        ai = mt5.account_info()
        if ai is None:
            return None
        from datetime import datetime, timedelta, timezone
        deals = mt5.history_deals_get(datetime(2020, 1, 1, tzinfo=timezone.utc), datetime.now(timezone.utc) + timedelta(days=1)) or []
        deposits = sum(float(d.profit) for d in deals if d.type == mt5.DEAL_TYPE_BALANCE)
        return {"balance": float(ai.balance), "equity": float(ai.equity), "deposits": deposits, "realized": float(ai.balance) - deposits}
    except Exception:
        return None


def judge(broker_realized, db_realized, tolerance=TOLERANCE):
    """('OK'|'MISMATCH'|'NOT CHECKED', gap) where gap = database minus broker."""
    if broker_realized is None or db_realized is None:
        return "NOT CHECKED", None
    gap = db_realized - broker_realized
    return ("OK" if abs(gap) <= tolerance else "MISMATCH"), round(gap, 2)


def db_forex_realized(db_path):
    try:
        from sultrix_predictor import market_of
    except Exception:
        market_of = lambda s: "crypto" if "/" in str(s) else "forex"
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    try:
        return sum(float(p or 0) for s, p in con.execute("SELECT symbol, pnl FROM fills WHERE side = 'sell'") if market_of(s) == "forex")
    finally:
        con.close()


def run(db_path):
    lines, ok = [], True
    try:
        import MetaTrader5 as mt5
        inited = mt5.initialize()
    except Exception:
        mt5, inited = None, False
    try:
        broker = forex_broker_result(mt5) if inited else None
    finally:
        if inited:
            mt5.shutdown()
    status, gap = judge(broker["realized"] if broker else None, db_forex_realized(db_path))
    if status == "NOT CHECKED":
        lines.append("forex: NOT CHECKED (MT5 terminal not readable from this process)")
    else:
        lines.append(f"forex: {status}  broker realized {broker['realized']:+.2f} (balance {broker['balance']:.2f} - deposits {broker['deposits']:.2f})  "
                     f"database {db_forex_realized(db_path):+.2f}  gap {gap:+.2f}")
        ok = ok and status == "OK"
    lines.append("crypto: NOT CHECKED (needs the exchange account inside the running bot)")
    lines.append("stocks: NOT CHECKED (needs the Alpaca account inside the running bot)")
    return lines, ok


def main(argv):
    db = argv[argv.index("--db") + 1] if "--db" in argv else None
    if not db:
        print(__doc__)
        return 2
    lines, ok = run(db)
    print("TRUTH CHECK (database versus the broker's own books)")
    for l in lines:
        print(" -", l)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
