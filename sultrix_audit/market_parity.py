"""market_parity.py

Sultrix is three markets with three agent teams. This read-only report puts the learning machinery side by side per market so a thin team is
visible at once (CEO, 2026-10-20: "forex and stocks have their own agents just like crypto"): closed trades, council decisions and vetoes, experience
memory (and how many carry a regime), lessons, market-history lessons and how often they were recalled, team memory items and LLM calls.
A market whose count is under a quarter of the best market's, on a measure where the others have data, is flagged THIN.
Run:  python market_parity.py --db <bot_state.db> [--data <data dir>]     Never raises; missing sources show as 0.
"""
import collections
import glob
import json
import os
import re
import sqlite3
import sys

MARKETS = ("crypto", "forex", "stocks")
_STOCKS = re.compile(r"\b(AAPL|MSFT|NVDA|AMZN|GOOGL|META|TSLA|AVGO|AMD|SPY|QQQ|JPM|XOM|UNH)\b")
_FOREX = re.compile(r"\b(EURUSD|USDJPY|GBPUSD|USDCHF|AUDUSD|USDCAD|NZDUSD|EURJPY|CHFJPY|AUDCAD|AUDNZD|XAGUSD|XAUUSD)\b|forex", re.I)
STOCK_SYMBOLS = {"AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD", "SPY", "QQQ", "JPM", "XOM", "UNH"}


def market_of_symbol(symbol):
    s = str(symbol or "")
    if "/" in s:
        return "crypto"
    return "stocks" if s in STOCK_SYMBOLS else "forex"


def market_of_text(text):
    t = str(text or "")
    if "/USDT" in t or "crypto" in t.lower():
        return "crypto"
    if _STOCKS.search(t) or "stocks" in t.lower():
        return "stocks"
    if _FOREX.search(t):
        return "forex"
    return "general"


def _ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)


def collect(db_path, data_dir=None):
    """{measure: {market: count}} for every measure; markets with nothing show 0."""
    data_dir = data_dir or os.path.join(os.path.dirname(db_path), "data")
    out = {k: {m: 0 for m in MARKETS} for k in ("trades", "council_decisions", "council_vetoes", "experience", "experience_with_regime", "lessons",
                                                  "knowledge_lessons", "knowledge_recalls", "team_memory", "llm_calls")}
    try:
        con = _ro(db_path)
        try:
            for sym, n in con.execute("SELECT symbol, COUNT(*) FROM fills WHERE side = 'sell' AND pnl IS NOT NULL AND pnl <> 0 GROUP BY symbol"):
                out["trades"][market_of_symbol(sym)] += n
            for aid, content, conc in con.execute("SELECT agent_id, content, concepts FROM agent_lessons"):
                m = market_of_text(f"{content} {conc}")
                if m in out["lessons"]:
                    out["lessons"][m] += 1
            for m, n, rec in con.execute("SELECT market, COUNT(*), COALESCE(SUM(resurface_count), 0) FROM market_knowledge GROUP BY market"):
                if m in out["knowledge_lessons"]:
                    out["knowledge_lessons"][m], out["knowledge_recalls"][m] = n, int(rec)
            try:
                for (sym,) in con.execute("SELECT symbol FROM llm_advisory_log"):
                    out["llm_calls"][market_of_symbol(sym)] += 1
            except Exception:
                pass
        finally:
            con.close()
    except Exception:
        pass
    try:
        rows = json.load(open(os.path.join(data_dir, "decision_journal.json"), encoding="utf-8"))
        rows = rows if isinstance(rows, list) else next(iter(rows.values()))
        for r in rows:
            m = r.get("market") or market_of_symbol(r.get("symbol"))
            if m in out["council_decisions"]:
                out["council_decisions"][m] += 1
                if str(r.get("verdict", "")).lower().startswith(("veto", "block", "reject")):
                    out["council_vetoes"][m] += 1
    except Exception:
        pass
    try:
        ex = _ro(os.path.join(data_dir, "experience.db"))
        try:
            for m, n, tagged in ex.execute("SELECT market, COUNT(*), SUM(regime IS NOT NULL AND regime <> '') FROM trades GROUP BY market"):
                if m in out["experience"]:
                    out["experience"][m], out["experience_with_regime"][m] = n, int(tagged or 0)
        finally:
            ex.close()
    except Exception:
        pass
    for m in MARKETS:
        try:
            d = json.load(open(os.path.join(data_dir, "memory", f"{m}_memory.json"), encoding="utf-8"))
            out["team_memory"][m] = len(d.get("observations", d.get("obs", []))) if isinstance(d, dict) else len(d)
        except Exception:
            pass
    return out


def thin(report):
    """[(measure, market)] where a market has under a quarter of the best market's count while the best has at least 40."""
    flags = []
    for k, per in report.items():
        top = max(per.values())
        if top < 40:
            continue
        flags += [(k, m) for m, v in per.items() if v < top / 4.0]
    return flags


def render(report):
    labels = {"trades": "closed trades", "council_decisions": "council decisions", "council_vetoes": "council vetoes", "experience": "experience memory",
              "experience_with_regime": "  of which carry a regime", "lessons": "lessons", "knowledge_lessons": "market-history lessons",
              "knowledge_recalls": "  times recalled", "team_memory": "team memory items", "llm_calls": "LLM advisory calls"}
    flags = set(thin(report))
    L = [f"{'':<28}" + "".join(f"{m:>10}" for m in MARKETS)]
    for k, lab in labels.items():
        L.append(f"{lab:<28}" + "".join(f"{report[k][m]:>9}{'*' if (k, m) in flags else ' '}" for m in MARKETS))
    if flags:
        L.append("* THIN: under a quarter of the best market on this measure")
    return "\n".join(L)


def main(argv):
    db = argv[argv.index("--db") + 1] if "--db" in argv else None
    data = argv[argv.index("--data") + 1] if "--data" in argv else None
    if not db:
        print(__doc__)
        return 2
    print(render(collect(db, data)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
