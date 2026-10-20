# Sultrix

**The Trading OS for crypto, forex and stocks.** Separate AI agent teams for each market, a risk dashboard, alerts, and a phone app (PWA). Hands-free, 24/7.

[Website](https://sultrixtrade.com) · [30-second product tour](https://sultrixtrade.com/#demo) · [Download](https://sultrixtrade.com/download)

> Demo footage uses a demo account with test money. Trading carries risk of loss. Nothing here is financial advice or a prediction of future performance.

## What it is

| | |
|---|---|
| **Markets** | Crypto (CCXT exchanges), forex and metals (MetaTrader 5), US stocks (Alpaca, beta) |
| **Instruments** | 66 (30 crypto coins plus 36 forex, metals, oil and index instruments) |
| **Agents** | 40+ AI agents: market scanning, signal selection, risk guard, execution, a council that can veto trades, memory and lessons per market |
| **Strategy** | Automated grid trading with risk limits and a kill switch |
| **Alerts** | Telegram and email, plus a mobile PWA |
| **Platforms** | Windows (macOS and Linux in beta) |
| **Plans** | 30-day free trial, then plans from $5 per 30 days at [sultrixtrade.com](https://sultrixtrade.com) |

The Sultrix application is a commercial product and is not in this repository.

## What is open source here: the Sultrix Audit Toolkit

Read-only tools that check a Sultrix database against independent evidence, so results can be verified instead of trusted. They never place orders and never write to the database.

| Tool | Question it answers |
|---|---|
| [`truth_check.py`](sultrix_audit/truth_check.py) | Does the database result match the broker's own books (balance minus deposits)? |
| [`performance_report.py`](sultrix_audit/performance_report.py) | Honest ROI, win rate, profit factor, drawdown, forced sales, with caveats |
| [`exit_study.py`](sultrix_audit/exit_study.py) | Would a trailing exit have beaten the grid exit on real closed lots? |
| [`pattern_study.py`](sultrix_audit/pattern_study.py) | Do candle and trend patterns carry an edge on real data, under a strict test? |
| [`market_parity.py`](sultrix_audit/market_parity.py) | Do crypto, forex and stocks each have comparable agents, memory and lessons? |

```
python sultrix_audit/truth_check.py --db bot_state.db
python sultrix_audit/market_parity.py --db bot_state.db
python -m pytest tests
```

Python 3.10 or newer, standard library only (`truth_check` also uses `MetaTrader5` when it is installed). More in [`sultrix_audit/README.md`](sultrix_audit/README.md).

## Licence

The audit toolkit is licensed under the Apache License 2.0 (see [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE)). The Sultrix trading application is a separate commercial product.
