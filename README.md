# Sultrix Audit Toolkit

Read-only tools that check a Sultrix trading database against independent evidence. They never place orders and never write to the database.

| Tool | Question it answers |
|---|---|
| `truth_check.py` | Does the database result match the broker's own books (balance minus deposits)? |
| `performance_report.py` | Honest ROI, win rate, profit factor, drawdown, forced sales, with caveats |
| `exit_study.py` | Would a trailing exit have beaten the grid exit on real closed lots? |
| `pattern_study.py` | Do candle and trend patterns carry an edge on real data, under a strict test? |
| `market_parity.py` | Do crypto, forex and stocks each have comparable agents, memory and lessons? |

```
python sultrix_audit/truth_check.py --db bot_state.db
python sultrix_audit/market_parity.py --db bot_state.db
python -m pytest tests
```

Python 3.10+, standard library only (`truth_check` also uses `MetaTrader5` when present). The demo account runs on test money; nothing here is financial advice.

## Licence

Apache License 2.0 (see `LICENSE` and `NOTICE`). This covers only the audit toolkit in this branch. The Sultrix trading application is a separate commercial product and is not included.
