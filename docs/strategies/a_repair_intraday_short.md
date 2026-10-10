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

## Execution eligibility audit and user decisions — 2026-10-09

Audit: `docs/data/a_repair_intraday_short_eligibility_audit.json`.
Base raw-backtest commit: `be1643fc010bbe17a20557fb0aac9e72ec9f8f01`.
Scope: entry-day exchange eligibility for cash sell-first day trading, not margin/borrowed-stock shorting.

- 113 historical signals across 86 entry days were checked against dated TWSE/TPEx lists.
- 97 confirmed exchange-eligible (listed, sell-first suspension flag blank).
- 16 confirmed ineligible: 11 supported by official dated evidence and 5 subsequently confirmed by WOO.
- No pending entries remain. WOO confirmed 德宏 on 2026-05-25 and 2026-05-29 could not cash-day-trade (specific regulatory cause unspecified); WOO confirmed 訊達 on 2026-07-06, 2026-07-08 and 2026-09-07 was in disposal. Preserve user confirmation separately from official evidence.
- The 11 independently verified exceptional records include dated official evidence; the other 5 explicitly cite user confirmation. Disposal dates are checked for stock itself, not its warrants or convertible bonds.
- Confirmed restrictions remove that entry-day execution only; raw signals and historical LAB remain intact.
- Exchange eligibility does not establish the user's broker inventory, quota, or opening-fill feasibility.

User-confirmed execution decisions:
- Skip signals whose entry day is inside a confirmed disposal period or sell-first suspension.
- Do not short when opening downside to the daily lower limit is insufficient ("沒肉"). Room thresholds of 1%, 2%, 3% remain research candidates, not a locked selected value.
- **Superseding earlier conversation assumption:** redistribute the NT$5m daily pool equally across surviving original strategy signals after eligibility/room filtering. Do not leave skipped allocations idle when another original signal survives; do not select a replacement stock outside original signals. If none survive, no execution that day.
- Stop-loss/profit-target changes are not accepted yet. First correct eligibility and allocation, then recalculate the executable baseline and reassess risk.

Earlier conversation numbers after filters used idle skipped allocations and provisional eligibility exclusions. They are not results of the latest confirmed model and must not be quoted as its performance.
The official `WOO_STRATEGY_V1` raw backtest and forward LAB have not been rewritten; this audit is an additional execution layer.

## Corrected execution research — 2026-10-09

Result: `docs/data/a_repair_intraday_short_execution_research.json`.
Window: 2025-10-09 through 2026-10-08. NTD 5m pool, divided equally AFTER filters.
Returns calculated from exact entry/exit prices, so tiny rounding differences from old conversation numbers are expected.

| Scenario | Trades | Entry days | Gross P&L NTD | Max cumulative close P&L drawdown NTD |
|---|---:|---:|---:|---:|
| Raw signals | 113 | 86 | 4,402,119.29 | 1,218,665.12 |
| Eligibility filter only | 97 | 80 | 4,878,579.44 | 700,175.47 |
| Eligibility + estimated room >= 1%, 2%, or 3% | 96 | 79 | 5,353,579.44 | 298,346.21 |

The room-filtered scenarios are identical: only 3324 雙鴻 on 2026-06-08 is removed (estimated room 0.1%). Threshold selection remains unresolved.
Room-filtered wins/losses/flats: 67/23/6; win rate 69.79% including flats.
Max drawdown: 2026-05-27 peak through 2026-06-02 trough.
Worst remaining day: 2026-06-01 雙鴻, gross -NTD 276,497.70.
Next risk review should start with that trade and other remaining large-loss executions.

These are in-sample gross simulations, exclude all execution costs and broker feasibility, and do not measure intraday portfolio drawdown. Prior idle-allocation results are superseded for the current user model. No hard stop-loss or profit target has been adopted.

## Intraday profit giveback candidates — 2026-10-09

Candidate data: `docs/data/a_repair_intraday_short_giveback_candidates.json`.
Reviewed the 96 eligibility/room-filtered executions. Descriptive screen: MFE >= 2% and close return <= 25% of MFE. Found 9 candidates: 6 close losses and 3 small close gains.
Largest peak-to-close giveback candidates: 2026-04-27 加百裕 (MFE +2.907%, close -2.6163%) and 2026-04-09 群創 (MFE +3.0189%, close -1.6981%).
These daily OHLC observations identify profit giveback, but cannot confirm that the opening short was near the intraday high or that the path was a clean selloff followed by a V reversal. Next inspect minute candles, low timing, rebound timing and executable exit prices. MFE is hindsight, not an assumed achievable fill. The screening thresholds are not adopted profit-taking rules.

## User exit constraint and sector / stop comparison — 2026-10-10

WOO confirmed on 2026-10-09 that the working strategy exits only at same-day close, accepting losses. On 2026-10-10 WOO selected 11 high-MAE examples and requested sector context and a comparative "break above high" stop experiment. This authorizes research, not adoption of a stop or a changed production rule.

Research: `docs/data/a_repair_intraday_short_sector_stop_research.json`.
Same 96 eligible/room-filtered trades. 10 of the 11 selected examples had all tracked group members open higher. Group closing strength is descriptive hindsight, never an opening filter.

| Experiment | Trades | Win rate incl flats | Gross P&L NTD | Max cumulative daily P&L drawdown NTD |
|---|---:|---:|---:|---:|
| Baseline close exit | 96 | 69.79% | 5,353,579 | 298,346 |
| Skip all-positive group opening with mean gap >=1% | 65 | 72.31% | 3,588,176 | 304,362 |
| Skip open >= yesterday high +1 tick | 78 | 70.51% | 3,938,167 | 304,362 |
| Yesterday high +1 tick stop, skip already crossed at open | 78 | 56.41% | 2,414,871 | 378,268 |
| Prior 20-session high +1 tick stop | 96 | 69.79% | 5,380,285 | 276,498 |

The first group filter removes 20 winners, 10 losers and 1 flat. Yesterday-high stop hits 23 of the 78 entered trades, including 11 original winners. Prior20-high stop hits only 2 trades: 長榮 on 2026-06-02 improves from -2.6667% to -0.2222%, while 邁達特 that day worsens from -1.3684% to -2.2105%. Its slight total improvement is not robust evidence.

Use equal NTD5m allocation after skips. All stop simulations assume perfect exact barrier fills, exclude costs/slippage; fixed percentage comparisons also use theoretical unticked barriers. Group-opening diagnostics assume completed opening prints while retaining open fills and are optimistic, not executable pre-open rules. User's "high" was not precisely defined; yesterday/5/20-session highs are explicit research definitions, not a claim about intraday prior-high stops. No strategy/LAB signal or actual trade record was changed.

## Sector influence clarification and leader-limit event entry — 2026-10-10

WOO clarified that the question was sector influence, not an opening sector filter. Peer-excluded open-to-close comovement across the 96 executions: Pearson 0.71545; 67/90 nonflat trades same direction. This is contemporaneous association, not causal influence or a leading signal. For the 11 selected high-MAE cases, 9/10 nonflat cases moved with other group stocks.

WOO then authorized testing: wait until a same-group leader touches upper limit, market-short the original weak-stock candidate, cover same-day close. Research operational definition: first OTHER group member to touch limit (not hindsight closing leader), next target tick after 1 second, also 5/10-second sensitivity; no entry after continuous session ends. 12 of the 96 signals across 11 dates have a peer-limit touch in daily data; remaining 84 have no candidate trigger under this definition.

Research branch: `research/short-leader-limit-entry-20261010`.
- `docs/data/a_repair_intraday_short_leader_limit_candidates.json`
- `scripts/research_short_leader_limit_entry.py`
- `docs/data/a_repair_intraday_short_leader_limit_entry_result.json`
- manual workflow `.github/workflows/research-short-leader-limit.yml`

Actual GitHub Actions run 38017939402 successfully executed the access probe with the project's existing FINMIND_TOKEN but provider rejected historical tick access: HISTORICAL_TICK_ACCESS_LEVEL_REQUIRED. Local unauthenticated tick/KBar probes were also rejected. Result is BLOCKED_DATA_PERMISSION, performance summaries null, NOT zero profit. Need historical tick-capable access or externally supplied timestamped intraday data. No true trigger-entry return or MAE has been computed.

Candidate-pool event simulation reserves original known opening-qualified pool shares; nontriggered shares remain idle, avoiding hindsight allocation based on future trigger counts. This is an experimental convention, not a revision of WOO's confirmed post-filter opening-pool allocation. No production strategy or LAB signal changed.
