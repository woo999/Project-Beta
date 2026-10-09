# WOO FLOW / LAB — PROJECT STATE

> Purpose: single source of truth for continuing the WOO FLOW / WOO LAB project across new ChatGPT conversations.
> Before making strategy, backtest, LAB, data-pipeline, or UI changes, read this file first and then verify the live repo files it references.
> Last manually refreshed: 2026-10-09
> Repo: `woo999/Project-Beta`
> Site: https://woo999.github.io/Project-Beta/

---

## 1. Project principles

- WOO FLOW = sector/stock structure engine and market data layer.
- WOO ALERT = rules-based signal generator.
- WOO LAB = forward validation of generated signals.
- System signals are **not the same thing as the user's actual trades**.
- Actual trades are only treated as real trades when the user explicitly says they entered.
- Different strategies may trigger the same stock independently; do not silently merge historical signals.
- Historical signals permanently retain the rule version and grade they had when generated.
- Later strategy-rule changes must not rewrite old LAB signals.
- Do not optimize locked strategy rules from one new example. Review only on the scheduled review date unless the user explicitly overrides.

---

## 2. Current locked strategy version

- Rule version: `WOO_STRATEGY_V1`
- Locked at: `2026-10-04`
- Next formal review: `2026-10-11`
- Cost model used by LAB/backtests: `GROSS_NO_FEES_TAX_SLIPPAGE`

Authoritative files:
- `scripts/update_strategy_alerts.py`
- `scripts/update_strategy_lab.py`
- `docs/data/strategy_alerts.json`
- `docs/data/strategy_lab.json`

---

## 3. Current five strategies

### 3.1 SS — 發動續強・真領漲
- Side: LONG
- Holding: 10 trading days
- Trigger:
  - group activation day = group rank <= 3
  - group average daily return >= 2%
  - up ratio >= 60%
  - prior 120-session group activation follow-through must have positive average and >= 60% 5-day win rate
  - candidate stock must have historical top1 rate >= 40%
  - current activation selects top 2 daily performers
- Entry: next trading-session open
- Exit: close on the 10th trading session from signal logic

### 3.2 SS — 新轉強・當日落後補漲
- Side: LONG
- Holding: 5 trading days
- Trigger: group enters `新轉強` today and was not `新轉強` yesterday
- Stock selection: weakest daily performer inside that group
- Entry: next open
- Exit: 5th-session close

### 3.3 A — 中期弱短期強・落後補漲
- Side: LONG
- Holding: 10 trading days
- Trigger:
  - 20-day group rank >= 12
  - 5-day group rank <= 5
- Stock selection: weakest 20-day member in the group
- Entry: next open
- Exit: 10th-session close

### 3.4 A — 高檔整理・長期強股
- Side: LONG
- Holding: 20 trading days
- Trigger: group enters `高檔整理` today and was not `高檔整理` yesterday
- Stock selection: strongest 60-day member in the group
- Entry: next open
- Exit: 20th-session close
- Important interpretation: `高檔整理` is the **group state**, not necessarily a description of the individual stock.

### 3.5 A — 修復中・弱股隔日當沖空
- Side: SHORT
- Holding: 1 day / intraday
- Trigger: group enters `修復中` today and was not `修復中` yesterday
- Stock selection: weakest 20-day member in the group
- Entry: next trading-session open
- Exit: same-day close
- This is currently the main low-capital / high-turnover strategy being studied for capital accumulation.

---

## 4. Group-state definitions

Using group ranks and average returns over 60/20/10/5 sessions:

- `background = r60 <= 8 and ret60 > 0`
- `core = r20 <= 5 and ret20 > 0`
- `confirm = r10 <= 6 and ret10 > 0`
- `near_ok = r5 <= 8`
- `improving = r20 <= 10 and r10 < r20 and r5 <= r10 and ret20 > 0`
- `repairing = r20 >= 11 and r10 < r20 and r5 <= r10 and ret10 > 0 and ret5 > 0`
- `lost = (background or r20 <= 8) and ((r5-r20) >= 6 or (r5 >= 12 and ret5 < 0))`
- `weakening = background and r20 >= 10 and r10 >= 9 and r5 >= 9 and ret20 <= 0`
- `weak = (not background) and r20 >= 12 and r10 >= 10 and r5 >= 10 and ret20 <= 0`

Priority:
1. 結構完整
2. 新轉強
3. 轉強中
4. 修復中
5. 失速
6. 轉弱
7. 弱勢
8. 高檔整理
9. 觀察

---

## 5. Latest market-data status

As last verified:
- latest market date: `2026-10-08`
- tracked stocks: `81`
- successes: `81`
- failures: `0`
- earliest retained history: `2024-11-07`
- backfill window setting: `700 days`

Authoritative status file:
- `docs/data/market_status.json`

Data source in current pipeline:
- FinMind `TaiwanStockPrice`

---

## 6. Current forward LAB snapshot

As of market date `2026-10-08`:

Summary:
- signals: 8
- waiting entry: 1
- open: 4
- completed: 3

Completed `修復中・弱股隔日當沖空` signals:
1. 2359 所羅門
   - signal 2026-10-02
   - entry 2026-10-05 open 130.5
   - exit 2026-10-05 close 127.0
   - gross return +2.6820%
2. 3363 上詮
   - signal 2026-10-02
   - entry 2026-10-05 open 682
   - exit 2026-10-05 close 664
   - gross return +2.6393%
3. 3450 聯鈞
   - signal 2026-10-07
   - entry 2026-10-08 open 528
   - exit 2026-10-08 close 522
   - gross return +1.1364%

Forward LAB stats for this strategy so far:
- completed: 3
- wins: 3
- losses: 0
- win rate: 100%
- avg gross return: +2.1526%

Do **not** treat 3/3 as proof. Forward sample is still extremely small.

Other open LAB signals include:
- 3441 聯一光 — SS 發動續強・真領漲
- 3441 聯一光 — A 高檔整理・長期強股
- 1303 南亞 — A 高檔整理・長期強股
- 6174 安碁 — SS 發動續強・真領漲
- 6174 安碁 also has a newer waiting-entry SS signal dated 2026-10-08

Authoritative file:
- `docs/data/strategy_lab.json`

---

## 7. One-year locked-strategy backtest

File:
- `docs/data/backtest_woo_strategies_v1.json`
- script: `scripts/backtest_woo_strategies_v1.py`

Test window:
- 2025-10-09 to 2026-10-08
- entry/exit prices use real historical daily OHLC data
- trades are simulated, not actual user fills
- standard comparison size = NT$500,000 per signal
- no fees, tax, slippage, borrowing cost, or execution-impact model

### Per-strategy results

| Strategy | Trades | Win rate | Avg return | Gross P&L at 500k/signal |
|---|---:|---:|---:|---:|
| 發動續強・真領漲 | 72 | 56.94% | +2.0701% | +NT$745,246 |
| 新轉強・當日落後補漲 | 43 | 69.77% | +4.1813% | +NT$898,979 |
| 中期弱短期強・落後補漲 | 113 | 63.72% | +6.3554% | +NT$3,590,782 |
| 高檔整理・長期強股 | 152 | 65.13% | +11.8795% | +NT$9,028,384 |
| 修復中・弱股隔日當沖空 | 113 | 69.91% | +1.0748% | +NT$607,254 |

All raw strategy signals:
- completed signals: 493
- wins: 321
- losses: 165
- flats: 7
- win rate: ~65.11%
- if every signal is independently funded at NT$500k: gross P&L ~NT$14.87m
- peak raw simultaneous position count: 34
- peak raw nominal capital at 500k each: ~NT$17.0m
- excluding the one intraday short active on that peak day, overnight capital was ~NT$16.5m

Combined execution rule currently used in the backtest:
- same stock / same day: keep highest grade
- while stock is already held: later signals on the same stock are skipped

Combined result:
- completed trades: 285
- wins/losses/flats: 195 / 84 / 6
- win rate: 68.42%
- avg return: +5.891%
- gross P&L at 500k/trade: +NT$8.395m
- peak concurrent positions: 19
- peak capital: NT$9.5m

---

## 8. High-grade strategy deep dive — 高檔整理・長期強股

Raw:
- 152 trades
- 99 wins / 53 losses
- win rate 65.13%
- avg +11.8795%
- median +7.2487%
- gross +NT$9.028m at 500k each

More realistic same-stock no-reentry while held:
- 78 trades
- 55 wins / 23 losses
- win rate 70.51%
- avg +14.6711%
- median +9.16%
- gross +NT$5.722m
- peak concurrent positions: 12
- peak nominal capital at 500k each: NT$6.0m

Winner concentration:
- top 1 winner ≈ 6.9% of total profit
- top 5 ≈ 30.1%
- remove top 5 winners: still ≈ +NT$4.0m
- remove top 10 winners: still ≈ +NT$2.7m

Known concern:
- tail losses can be large because there is no stop-loss in this backtest
- raw worst examples included losses around -30% to -50%
- do not add a stop-loss just because these look ugly; compare expectancy first

Group anomaly worth reviewing on 2026-10-11:
- 面板 group was negative in the raw high-grade backtest and had 0 wins in 7 raw samples
- investigate whether this is structural or sample noise before changing rules

---

## 9. NT$2m capital experiment for 高檔整理・長期強股

Simulation assumptions:
- total capital fixed at NT$2m
- 500k per slot
- max 4 concurrent positions
- same stock cannot re-enter while already held
- when full, later signals are skipped

Result:
- 40 trades
- 27 wins / 13 losses
- win rate 67.5%
- avg return +14.14%
- gross simulated profit ≈ NT$2.829m
- rough gross return on 2m capital ≈ +141%

Other tested slot sizes over the same sample:
- 500k × 4 slots → ~NT$2.83m
- 400k × 5 slots → ~NT$2.53m
- ~333k × 6 slots → ~NT$2.48m
- 250k × 8 slots → ~NT$2.34m
- 200k × 10 slots → ~NT$2.14m

Do **not** hard-code “4 slots is optimal”; this can easily be sample-specific.

---

## 10. Intraday-short capital-accumulation idea

Current focus:
- `修復中・弱股隔日當沖空`
- historical one-year backtest:
  - 113 completed trades
  - 79 wins / 28 losses / 6 flats
  - win rate 69.91%
  - avg +1.0748%
  - median +0.984%
  - 500k per trade gross ≈ +NT$607k

Important interpretation:
- because it is intraday, it does not lock capital overnight
- but it still consumes same-day order / risk / shorting capacity
- scale is **not** assumed to remain linear at large size due to liquidity, slippage, short availability, execution impact, price limits and borrowing/stock-loan mechanics
- this strategy performed positively even during a strong Taiwan-equity year, which makes its cross-regime behavior worth deeper study
- next useful research: regime split, maximum losing streak, same-day simultaneous signals, liquidity/ADV capacity, realistic fees/tax/slippage and short availability

Do not equate backtest profitability with live scalability.

---

## 11. Historical-universe caveat

Backtest has explicit historical exclusions:
- 6209 今國光 excluded before 2026-10-07
- 4903 聯光通 excluded before 2026-10-08

But earlier group membership history is not fully versioned.
Therefore:
- old constituent lists may contain survivorship / membership hindsight
- forward LAB remains the cleanest validation layer

Current known group updates:
- 光學 includes 6209 今國光
- 矽光 includes 4903 聯光通

---

## 12. Current data workflow

Workflow:
- `.github/workflows/market-data.yml`

Sequence:
1. update market data
2. update monthly trade snapshots
3. run M1 walk-forward backtest
4. update WOO ALERT
5. run locked WOO 5-strategy backtest
6. update WOO LAB
7. commit refreshed data

Important:
- GitHub cron was removed because scheduled Actions timing was unreliable
- updates are triggered by push / workflow dispatch
- external wake mechanism uses `.github/woo-flow-wake.txt`
- `FINMIND_TOKEN` is stored as a GitHub secret

Current update automation:
- title: `WOO Flow 15:00 Update`
- Taiwan weekdays at 15:00
- checks `market_status.json`
- if stale, touches the wake file to trigger the workflow
- on 2026-10-08 the automation ran and market data reached 2026-10-08

When checking status, always verify BOTH:
1. automation run state
2. GitHub Actions + `market_status.json`

Never infer success from only one side.

---

## 13. Known implementation issue

`scripts/update_strategy_lab.py` currently updates `record["current"]` even for COMPLETED signals before checking completion.

Effect:
- official `exit`, `gross_return_pct`, and `result` remain correct
- but `current` on completed records may later show a newer market close and become semantically misleading

This is a data-cleanliness issue, not currently a completed-P&L calculation error.
Fix has not yet been implemented as of this state file.

---

## 14. Separate legacy / experimental backtest

`M1_WALK_FORWARD_V1` / 一個月結構轉強策略 is **not** one of the current five locked WOO strategies.

Files:
- `scripts/backtest_monthly_v1.py`
- `docs/data/backtest_monthly_v1.json`

Do not mix M1 results with WOO_STRATEGY_V1 results.

---

## 15. Review discipline

For the formal 2026-10-11 review:

Check:
- forward LAB mechanics/data correctness
- whether signals were generated before outcomes
- sample count by strategy
- regime behavior
- group-specific anomalies
- slippage / fee / tax sensitivity
- same-stock overlap and capital contention
- intraday-short capacity and losing streak
- high-grade strategy tail losses
- historical constituent bias

Do NOT:
- rewrite historical grades
- migrate old signals to new rules
- optimize because of one trade
- claim proof from tiny forward samples

Preferred evidence threshold for stronger confidence:
- at least ~3 months forward validation
- ideally 20–30+ completed trades per strategy before first serious acceptance
- 40–50+ and multiple market regimes for stronger confidence

---

## 16. How to resume this project in a new ChatGPT conversation

At the start of a new WOO FLOW / LAB conversation:

1. Read `docs/PROJECT_STATE.md`.
2. Verify current:
   - `docs/data/market_status.json`
   - `docs/data/strategy_alerts.json`
   - `docs/data/strategy_lab.json`
   - `docs/data/backtest_woo_strategies_v1.json`
3. If strategy logic matters, inspect:
   - `scripts/update_strategy_alerts.py`
   - `scripts/update_strategy_lab.py`
4. Treat this file as orientation, not a substitute for live repo verification.
5. Update this file after any major rule, architecture, workflow, backtest, or LAB-policy change.

---

## 17. Immediate next research queue

1. Continue forward LAB without changing locked rules before review.
2. Deep-dive `修復中・弱股隔日當沖空`:
   - market-regime split
   - maximum consecutive losses
   - daily signal concurrency
   - realistic costs
   - liquidity / position-size capacity
3. Review `高檔整理・長期強股`:
   - tail-risk profile
   - group-level behavior, especially 面板
   - mark-to-market drawdown, not only realized drawdown
4. Keep actual user trades separate from system signals.
5. On 2026-10-11, perform health review before any strategy modification.
