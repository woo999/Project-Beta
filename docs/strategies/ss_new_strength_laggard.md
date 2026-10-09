# Strategy State — SS 新轉強・當日落後補漲

> Conversation scope: only this strategy. Cross-strategy capital allocation belongs in WOO MASTER.
> Orientation document only. Executable source of truth: `scripts/update_strategy_alerts.py`.
> Rule version: `WOO_STRATEGY_V1`
> Locked: 2026-10-04
> Next formal review: 2026-10-11
> Last state refresh: 2026-10-09

## Identity

- Grade: SS
- Side: LONG
- `holding_days`: 5
- Entry: next trading-session OPEN after signal
- Exit in current simulator/LAB convention: CLOSE on trading-date index `signal_date + 5`

## Exact signal logic

This strategy uses the group-state engine.

A group is labeled `新轉強` when the state-map priority logic lands on 新轉強. Its raw condition is:

- `background = false`
- `core = r20 <= 5 and ret20 > 0`
- `confirm = r10 <= 6 and ret10 > 0`
- `near_ok = r5 <= 8`

Signal trigger:

- today's group label == `新轉強`
- previous trading session's group label != `新轉強`

Stock selection:

- choose the member with the weakest same-day percentage change inside that group

This is a **state-transition** signal, not a signal every day the group remains 新轉強.

## One-year historical simulation snapshot

Test window: 2025-10-09 to 2026-10-08.
Standard position size: NT$500,000 per signal.
Cost model: GROSS_NO_FEES_TAX_SLIPPAGE.

- Completed: 43
- Wins / losses / flats: 30 / 13 / 0
- Win rate: 69.77%
- Average return: +4.1813%
- Median return: +2.9412%
- Gross P&L at 500k/signal: +NT$898,979.06
- Peak concurrent positions: 7
- Peak nominal capital: NT$3.5m
- Peak date: 2026-08-12

## Forward LAB snapshot as of 2026-10-08

No current LAB signals for this strategy in the present forward sample.

## Research rules

Focus this conversation on:
- quality of the 新轉強 transition
- whether the weakest same-day member genuinely catches laggard catch-up
- 5-day MFE / MAE
- repeat-transition frequency
- sector/regime dependence
- liquidity and execution
- forward LAB accumulation

Do not:
- treat every day labeled 新轉強 as a fresh signal
- replace the weakest same-day member rule with weakest 20-day member
- mix this with the A 中期弱短期強 strategy
- change locked logic before formal review unless the user explicitly overrides
