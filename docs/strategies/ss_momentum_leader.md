# Strategy State — SS 發動續強・真領漲

> Conversation scope: only this strategy. Cross-strategy capital allocation belongs in WOO MASTER.
> Orientation document only. The executable source of truth is `scripts/update_strategy_alerts.py`; LAB truth is `docs/data/strategy_lab.json`; historical test truth is `docs/data/backtest_woo_strategies_v1.json`.
> Rule version: `WOO_STRATEGY_V1`
> Locked: 2026-10-04
> Next formal review: 2026-10-11
> Last state refresh: 2026-10-09

## Identity

- Grade: SS
- Side: LONG
- `holding_days`: 10
- Entry: next trading-session OPEN after the signal date
- Exit in current simulator/LAB convention: CLOSE on trading-date index `signal_date + 10`
- Historical signals keep their original rule version and grade.

## Exact signal logic

A group first needs a same-day activation event:

- group daily rank <= 3
- group average daily percentage change >= +2%
- advancing-member ratio >= 60%

Then validate prior group behavior over the prior 120 trading sessions:

- look only at earlier activation events
- each prior activation is evaluated on its 5-trading-day group follow-through
- at least 5 usable prior activation samples are required
- average 5-day follow-through must be > 0%
- 5-day win rate must be >= 60%

Then validate each stock candidate over earlier activation events in the same 120-session lookback:

- at least 5 usable observations for that stock
- historical rate of being #1 within the group activation ranking must be >= 40%

Current-day stock selection:

- take the current activation's top 2 stocks by same-day percentage change
- only stocks passing the historical top1-rate filter become alerts

This is an activation/event strategy. Do not replace it with group-state labels such as 結構完整 or 新轉強.

## One-year historical simulation snapshot

Test window: 2025-10-09 to 2026-10-08.
Standard position size: NT$500,000 per signal.
Cost model: GROSS_NO_FEES_TAX_SLIPPAGE.

- Completed: 72
- Wins / losses / flats: 41 / 31 / 0
- Win rate: 56.94%
- Average return: +2.0701%
- Median return: +1.8092%
- Gross P&L at 500k/signal: +NT$745,246.24
- Peak concurrent positions: 9
- Peak nominal capital at 500k/signal: NT$4.5m
- Peak date: 2026-04-29

These are simulated historical fills using daily OHLC, not actual user trades.

## Forward LAB snapshot as of 2026-10-08

- Total signals: 3
- Completed: 0
- Current known entries/signals include:
  - 3441 聯一光 — signal 2026-10-05, OPEN
  - 6174 安碁 — signal 2026-10-07, OPEN
  - 6174 安碁 — newer signal 2026-10-08, WAIT_ENTRY

No completed forward sample yet. Do not infer live win rate.

## Research rules

Focus this conversation on:
- activation quality
- historical activation sample sufficiency
- MFE / MAE
- 10-day holding behavior
- overlap/repeat signals
- liquidity and execution
- regime sensitivity
- forward LAB results

Do not:
- merge this strategy with other strategies because they hit the same stock
- rewrite old signal grades after a rule change
- optimize from one winner or loser
- confuse system LAB signals with the user's real positions
