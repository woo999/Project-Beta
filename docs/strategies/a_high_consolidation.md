# Strategy State — A 高檔整理・長期強股

> Conversation scope: only this strategy. Cross-strategy capital allocation belongs in WOO MASTER.
> Orientation document only. Executable source of truth: `scripts/update_strategy_alerts.py`.
> Rule version: `WOO_STRATEGY_V1`
> Locked: 2026-10-04
> Next formal review: 2026-10-11
> Last state refresh: 2026-10-09

## Identity

- Grade: A
- Side: LONG
- `holding_days`: 20
- Entry: next trading-session OPEN after signal
- Exit in current simulator/LAB convention: CLOSE on trading-date index `signal_date + 20`

## Exact signal logic

This strategy uses the group-state engine.

Raw high-consolidation fallback condition:

- `background = r60 <= 8 and ret60 > 0`
- `r20 <= 8`

But the actual label `高檔整理` is assigned only after higher-priority state labels have failed. Therefore the executable `state_map` label is the source of truth.

Signal trigger:

- today's group label == `高檔整理`
- previous trading session's group label != `高檔整理`

Stock selection:

- choose the member with the strongest 60-day return in that group

Important: 高檔整理 describes the **group state**. It does not mean the individual chosen stock itself must visually be in a textbook consolidation.

## One-year historical simulation snapshot

Raw all-signal test, 2025-10-09 to 2026-10-08, NT$500,000 per signal:

- Completed: 152
- Wins / losses: 99 / 53
- Win rate: 65.13%
- Average return: +11.8795%
- Median return: +7.2487%
- Gross P&L: +NT$9,028,383.69
- Peak concurrent positions: 22
- Peak nominal capital: NT$11.0m
- Peak date: 2026-04-13

Research-only same-stock no-reentry experiment:

- 78 selected trades
- 55 wins / 23 losses
- Win rate: 70.51%
- Average: +14.6711%
- Median: +9.16%
- Gross P&L at 500k: about +NT$5.722m
- Peak concurrent: 12
- Peak nominal capital: NT$6.0m

This deduplicated experiment is not the official raw backtest output.

## Forward LAB snapshot as of 2026-10-08

Current LAB signals:
- 3441 聯一光 — OPEN
- 1303 南亞 — OPEN

Completed forward sample: 0.

## Known research observations

- Large right-tail winners materially contribute, but the raw result was not dependent on only one or two winners.
- Tail losses can also be very large because the current historical test has no stop-loss.
- 面板 was a negative group in the raw research breakdown: 0 wins in 7 raw samples. This is a review hypothesis, not a rule change.
- A previous NT$2m / 4-slot research simulation produced about +NT$2.829m gross, but that result is sample-specific and must not be treated as proof that four slots are optimal.

## Research rules

Focus this conversation on:
- 20-day holding tail risk
- mark-to-market drawdown
- MFE / MAE
- winner concentration
- same-stock repeats
- capital slots
- group-level anomalies
- regime sensitivity

Do not:
- add a stop-loss solely because historical tail losses look ugly
- exclude 面板 before formal validation
- optimize slot count from one historical path
- confuse raw signal P&L with capital-constrained portfolio P&L
