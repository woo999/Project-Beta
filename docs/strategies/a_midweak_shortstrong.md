# Strategy State — A 中期弱短期強・落後補漲

> Conversation scope: only this strategy. Cross-strategy capital allocation belongs in WOO MASTER.
> Orientation document only. Executable source of truth: `scripts/update_strategy_alerts.py`.
> Rule version: `WOO_STRATEGY_V1`
> Locked: 2026-10-04
> Next formal review: 2026-10-11
> Last state refresh: 2026-10-09

## Identity

- Grade: A
- Side: LONG
- `holding_days`: 10
- Entry: next trading-session OPEN after signal
- Exit in current simulator/LAB convention: CLOSE on trading-date index `signal_date + 10`

## Exact signal logic

This strategy directly checks group rankings; it does **not** require a state transition.

Trigger:

- 20-day group rank `r20 >= 12`
- 5-day group rank `r5 <= 5`

Stock selection:

- choose the member with the weakest 20-day return in that group

Important:

- because this is a direct daily condition, it may generate again on later days while the condition continues to hold
- do not silently convert it into a first-entry-only state transition

## One-year historical simulation snapshot

Test window: 2025-10-09 to 2026-10-08.
Standard position size: NT$500,000 per signal.
Cost model: GROSS_NO_FEES_TAX_SLIPPAGE.

- Completed: 113
- Wins / losses / flats: 72 / 40 / 1
- Win rate: 63.72%
- Average return: +6.3554%
- Median return: +2.8302%
- Gross P&L at 500k/signal: +NT$3,590,782.49
- Peak concurrent positions: 15
- Peak nominal capital: NT$7.5m
- Peak date: 2025-12-22

## Forward LAB snapshot as of 2026-10-08

No current LAB signals for this strategy in the present forward sample.

## Research rules

Focus this conversation on:
- repeated daily signals and same-stock overlap
- 20d-weak / 5d-strong regime quality
- 10-day MFE / MAE
- capital contention
- group-specific performance
- market-regime sensitivity
- forward validation

Do not:
- mislabel it as 新轉強
- force a one-time state-transition rule
- change the selected stock from weakest 20-day member without an explicit reviewed rule change
- mix raw all-signal results with portfolio-capital-constrained results
