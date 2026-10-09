# Strategy State — A 修復中・弱股隔日當沖空

> Conversation scope: only this strategy. This is currently the main low-capital/high-turnover strategy being studied for capital accumulation.
> Orientation document only. Executable source of truth: `scripts/update_strategy_alerts.py`. Historical test truth: `docs/data/backtest_woo_strategies_v1.json`.
> Rule version: `WOO_STRATEGY_V1`
> Locked: 2026-10-04
> Next formal review: 2026-10-11
> Last state refresh: 2026-10-09

## Identity

- Grade: A
- Side: SHORT
- `holding_days`: 1
- Entry: next trading-session OPEN after signal
- Exit: same trading-session CLOSE
- No overnight holding in the current strategy definition

## Exact signal logic

This strategy uses the group-state engine.

Underlying `repairing` condition:

- `r20 >= 11`
- `r10 < r20`
- `r5 <= r10`
- `ret10 > 0`
- `ret5 > 0`

The actual label is determined by state-map priority. The executable condition is therefore:

- today's group label == `修復中`
- previous trading session's group label != `修復中`

Stock selection:

- choose the member with the weakest 20-day return in that group

This is a **first-entry state-transition** signal, not a signal every day the group remains 修復中.

## One-year historical simulation snapshot

Test window: 2025-10-09 to 2026-10-08.
Standard official comparison size: NT$500,000 per signal.
Cost model: GROSS_NO_FEES_TAX_SLIPPAGE.

- Completed: 113
- Wins / losses / flats: 79 / 28 / 6
- Win rate: 69.91%
- Average return: +1.0748%
- Median return: +0.9840%
- Gross P&L at 500k/signal: +NT$607,254.38
- Raw peak same-day signal count / generic concurrent count: 3
- Generic nominal exposure at 500k each on that peak: NT$1.5m

Because this is intraday, do not describe the generic concurrency number as overnight capital locked.

## Forward LAB snapshot as of 2026-10-08

Completed:
1. 2359 所羅門 — +2.6820%
2. 3363 上詮 — +2.6393%
3. 3450 聯鈞 — +1.1364%

Forward snapshot:
- Completed: 3
- Wins: 3
- Losses: 0
- Win rate: 100%
- Average gross return: +2.1526%

The sample is only 3 trades. It is not proof of the historical win rate.

## MAE risk study — 113 historical trades

MAE is measured from entry open to the worst intraday adverse price for a short position.

Overall absolute MAE:
- Average: 1.7189%
- Median: 1.0811%
- 75th percentile: 2.2305%
- 90th percentile: 4.2552%
- 95th percentile: 5.3339%
- Worst: 10.0000%

Winning trades, n=79:
- Average MAE: 0.9756%
- Median MAE: 0.7663%
- 90th percentile: 2.2762%
- 95th percentile: 3.4091%
- Worst winning MAE: 4.8%

Losing trades, n=28:
- Average MAE: 3.7390%
- Median MAE: 2.8946%
- 90th percentile: 7.5613%
- 95th percentile: 8.2363%
- Worst: 10.0%

Threshold observations:
- MAE >= 2%: 33 trades = 11 wins / 20 losses / 2 flats
- MAE >= 3%: 21 trades = 5 wins / 14 losses / 2 flats
- MAE >= 4%: 12 trades = 2 wins / 9 losses / 1 flat
- MAE >= 5%: 8 trades = 0 wins / 8 losses

Important: the >=5% observation is only 8 historical samples. It is a research clue, **not yet a stop-loss rule**.

## NT$5m daily capital-pool research simulation

User's intended capital model:

- total intraday short pool per signal day = NT$5,000,000
- if 1 signal: allocate 5m
- if 2 signals: allocate 2.5m each
- if 3 signals: allocate about 1.667m each
- equal allocation among that day's valid signals

Historical result over the same one-year sample:

- 113 signals across 86 signal-entry days
- max signals on one day: 3
- multi-signal days: 22
- gross P&L: +NT$4,402,119.17
- average gross P&L per signal day: about +NT$51,187
- best day: 2026-07-07, about +NT$442,625
- worst day: 2026-06-08, about -NT$475,000

This is a research simulation, not the official 500k-per-signal backtest. It excludes fees, transaction tax, slippage, borrow/short availability, liquidity limits and market impact.

## Scale / risk interpretation

At larger size, do not assume linear scalability. Study:
- intraday liquidity / ADV
- spread and slippage
- short-sale availability and broker constraints
- price-limit risk
- multiple simultaneous signals
- maximum consecutive losing days
- maximum drawdown on the daily capital pool
- realistic costs

Current research priority is to understand risk before changing signal logic.

## Research rules

Focus this conversation on:
- MAE first
- MFE second
- losing streaks
- daily capital-pool drawdown
- realistic execution capacity
- regime split
- forward LAB

Do not:
- turn MAE >=5% into a hard stop before formal testing
- treat 3/3 forward wins as validation
- call NT$5m a per-stock size when the user's current model is NT$5m total per signal day
- mix overnight capital requirements from long strategies into this intraday strategy
