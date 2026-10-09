#!/usr/bin/env python3
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median

import update_strategy_alerts as strat

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
GROUPS_PATH = DATA / "groups.json"
DAILY_PATH = DATA / "daily_rankings.json"
OUT = DATA / "backtest_woo_strategies_v1.json"

POSITION_SIZE_NTD = 500_000
GRADE_ORDER = {"SSS": 0, "SS": 1, "A": 2, "B": 3, "C": 4}

# Preserve the historical universe for additions made after the strategy lock.
MEMBER_ADDED = {
    "6209": "2026-10-07",  # 今國光 added to 光學
    "4903": "2026-10-08",  # 聯光通 added to 矽光
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def groups_for_date(groups, date):
    out = deepcopy(groups)
    for g in out.get("groups", []):
        members = []
        for m in g.get("members", []):
            added = MEMBER_ADDED.get(m["code"])
            if added and date < added:
                continue
            members.append(m)
        g["members"] = members
        g["symbols"] = [m["code"] for m in members]
    return out


def build_activation_events(groups, hist, idx, dates):
    events = []
    for date in dates:
        gd = groups_for_date(groups, date)
        ranked_groups = []
        for g in gd.get("groups", []):
            members = []
            for m in g.get("members", []):
                r = strat.rowat(hist, idx, m["code"], date)
                p = r.get("pct") if r else None
                if isinstance(p, (int, float)):
                    members.append({"code": m["code"], "name": m["name"], "pct": p})
            if not members:
                continue
            avg_pct = sum(x["pct"] for x in members) / len(members)
            up_count = sum(x["pct"] > 0 for x in members)
            ranked_groups.append({
                "name": g["name"],
                "avg_pct": avg_pct,
                "up_count": up_count,
                "priced_members": len(members),
                "members": members,
            })

        ranked_groups.sort(key=lambda x: x["avg_pct"], reverse=True)
        for rank, gr in enumerate(ranked_groups, 1):
            gr["rank"] = rank
            up_ratio = gr["up_count"] / gr["priced_members"] if gr["priced_members"] else 0
            if rank > 3 or gr["avg_pct"] < 2 or up_ratio < 0.60:
                continue
            members = sorted(gr["members"], key=lambda x: x["pct"], reverse=True)
            events.append({"date": date, "group": gr["name"], "ranked": members})
    return events


def prior_group_h5(group, eby, hist, idx, dates, didx, current_date, lookback=120):
    ci = didx.get(current_date)
    vals = []
    if ci is None:
        return None
    for ev in eby.get(group["name"], []):
        ei = didx.get(ev["date"])
        if ei is None or ei >= ci or ci - ei > lookback:
            continue
        if ei + 5 >= ci or ei + 5 >= len(dates):
            continue
        target = dates[ei + 5]
        vals2 = []
        for m in group.get("members", []):
            a = strat.rowat(hist, idx, m["code"], ev["date"])
            b = strat.rowat(hist, idx, m["code"], target)
            if a and b and isinstance(a.get("close"), (int, float)) and a["close"] > 0 and isinstance(b.get("close"), (int, float)):
                vals2.append((b["close"] / a["close"] - 1) * 100)
        if vals2:
            vals.append(sum(vals2) / len(vals2))
    if len(vals) < 5:
        return None
    return {
        "n": len(vals),
        "avg": sum(vals) / len(vals),
        "win_rate": sum(v > 0 for v in vals) / len(vals) * 100,
    }


def generate_alerts_for_date(groups, hist, idx, dates, didx, date, events, eby):
    di = didx.get(date)
    if di is None or di == 0:
        return []
    prev = dates[di - 1]
    gd = groups_for_date(groups, date)
    pgd = groups_for_date(groups, prev)
    cur_states = strat.state_map(gd, hist, idx, date)
    prev_states = strat.state_map(pgd, hist, idx, prev)
    current_events = {(e["group"], e["date"]): e for e in events}
    alerts = []

    # SS: 發動續強・真領漲
    for g in gd.get("groups", []):
        ev = current_events.get((g["name"], date))
        if not ev:
            continue
        gf = prior_group_h5(g, eby, hist, idx, dates, didx, date, 120)
        if not gf or gf["avg"] <= 0 or gf["win_rate"] < 60:
            continue
        for x in ev["ranked"][:2]:
            dna = strat.prior_stock_dna(g["name"], x["code"], eby, didx, date, 120)
            if dna and dna["top1_rate"] >= 40:
                strat.add(
                    alerts, "SS", "發動續強・真領漲", "LONG", g["name"], x, 10,
                    f"120日發動後5日勝率 {gf['win_rate']:.0f}%（n={gf['n']}）｜歷史第一率 {dna['top1_rate']:.0f}%（n={dna['samples']}）｜本次發動前2"
                )

    # SS: 新轉強・當日落後補漲
    for g in gd.get("groups", []):
        now = cur_states.get(g["name"], {})
        old = prev_states.get(g["name"], {})
        if now.get("label") == "新轉強" and old.get("label") != "新轉強":
            stock = strat.weakest_day_member(g, hist, idx, date)
            if stock:
                strat.add(alerts, "SS", "新轉強・當日落後補漲", "LONG", g["name"], stock, 5,
                          "族群今日首次進入新轉強｜選當日族群內漲幅最弱股")

    # A: 中期弱短期強・落後補漲
    for g in gd.get("groups", []):
        st = cur_states.get(g["name"], {})
        if isinstance(st.get("r20"), int) and isinstance(st.get("r5"), int) and st["r20"] >= 12 and st["r5"] <= 5:
            stock = strat.strongest_member(g, hist, idx, date, 20, reverse=False)
            if stock:
                strat.add(alerts, "A", "中期弱短期強・落後補漲", "LONG", g["name"], stock, 10,
                          f"20日排名 #{st['r20']}｜5日排名 #{st['r5']}｜選20日最弱股")

    # A: 高檔整理・長期強股
    for g in gd.get("groups", []):
        now = cur_states.get(g["name"], {})
        old = prev_states.get(g["name"], {})
        if now.get("label") == "高檔整理" and old.get("label") != "高檔整理":
            stock = strat.strongest_member(g, hist, idx, date, 60, reverse=True)
            if stock:
                strat.add(alerts, "A", "高檔整理・長期強股", "LONG", g["name"], stock, 20,
                          "族群今日進入高檔整理｜選60日最強股")

    # A: 修復中・弱股隔日當沖空
    for g in gd.get("groups", []):
        now = cur_states.get(g["name"], {})
        old = prev_states.get(g["name"], {})
        if now.get("label") == "修復中" and old.get("label") != "修復中":
            stock = strat.strongest_member(g, hist, idx, date, 20, reverse=False)
            if stock:
                strat.add(alerts, "A", "修復中・弱股隔日當沖空", "SHORT", g["name"], stock, 1,
                          "族群今日進入修復中｜選20日最弱股｜下一交易日開盤放空、同日收盤回補（當沖）")

    uniq = {}
    for a in alerts:
        uniq[(a["strategy"], a["code"])] = a
    alerts = list(uniq.values())
    alerts.sort(key=lambda a: (GRADE_ORDER.get(a["grade"], 9), a["strategy"], a["group"], a["code"]))
    return alerts


def simulate(hist, idx, dates, didx, signal_date, alert):
    si = didx.get(signal_date)
    if si is None:
        return None
    entry_i = si + 1
    holding = int(alert.get("holding_days") or 1)
    exit_i = si + holding
    if entry_i >= len(dates) or exit_i >= len(dates):
        return None

    code = alert["code"]
    entry_date = dates[entry_i]
    exit_date = dates[exit_i]
    entry_row = strat.rowat(hist, idx, code, entry_date)
    exit_row = strat.rowat(hist, idx, code, exit_date)
    if not entry_row or not exit_row:
        return None
    entry = entry_row.get("open")
    exit_price = exit_row.get("close")
    if not isinstance(entry, (int, float)) or entry <= 0 or not isinstance(exit_price, (int, float)) or exit_price <= 0:
        return None

    holding_rows = []
    for di in range(entry_i, exit_i + 1):
        row = strat.rowat(hist, idx, code, dates[di])
        if row:
            holding_rows.append(row)

    highs = [r.get("high") for r in holding_rows if isinstance(r.get("high"), (int, float))]
    lows = [r.get("low") for r in holding_rows if isinstance(r.get("low"), (int, float))]

    if alert["side"] == "SHORT":
        ret = (entry - exit_price) / entry * 100
        mfe = (entry - min(lows)) / entry * 100 if lows else None
        mae = (entry - max(highs)) / entry * 100 if highs else None
    else:
        ret = (exit_price / entry - 1) * 100
        mfe = (max(highs) / entry - 1) * 100 if highs else None
        mae = (min(lows) / entry - 1) * 100 if lows else None

    return {
        "signal_date": signal_date,
        "entry_date": entry_date,
        "exit_date": exit_date,
        "entry_price": round(entry, 4),
        "exit_price": round(exit_price, 4),
        "return_pct": round(ret, 4),
        "mfe_pct": round(mfe, 4) if isinstance(mfe, (int, float)) else None,
        "mae_pct": round(mae, 4) if isinstance(mae, (int, float)) else None,
        "gross_pnl_ntd_at_500k": round(POSITION_SIZE_NTD * ret / 100, 2),
        **alert,
    }


def stats(rows):
    done = [x for x in rows if isinstance(x.get("return_pct"), (int, float))]
    vals = [x["return_pct"] for x in done]
    wins = sum(v > 0 for v in vals)
    losses = sum(v < 0 for v in vals)
    flats = sum(v == 0 for v in vals)

    peak_count = 0
    peak_date = None
    for d in sorted({z for x in done for z in (x["entry_date"], x["exit_date"])}):
        active = [x for x in done if x["entry_date"] <= d <= x["exit_date"]]
        if len(active) > peak_count:
            peak_count = len(active)
            peak_date = d

    return {
        "completed_trades": len(done),
        "wins": wins,
        "losses": losses,
        "flats": flats,
        "win_rate_pct": round(wins / len(done) * 100, 2) if done else None,
        "avg_return_pct": round(mean(vals), 4) if vals else None,
        "median_return_pct": round(median(vals), 4) if vals else None,
        "gross_pnl_ntd_at_500k": round(sum(x["gross_pnl_ntd_at_500k"] for x in done), 2),
        "peak_concurrent_positions": peak_count,
        "peak_capital_ntd_at_500k": peak_count * POSITION_SIZE_NTD,
        "peak_date": peak_date,
    }


def combined_execution(trades):
    # Actual-use approximation:
    # 1) same stock on the same signal day: keep the highest grade/priority signal only
    # 2) while a stock is already held, ignore later signals for that stock
    by_day_code = {}
    for t in trades:
        key = (t["signal_date"], t["code"])
        cur = by_day_code.get(key)
        rank = (GRADE_ORDER.get(t["grade"], 9), t["strategy"])
        if cur is None or rank < (GRADE_ORDER.get(cur["grade"], 9), cur["strategy"]):
            by_day_code[key] = t

    candidates = sorted(by_day_code.values(), key=lambda x: (x["entry_date"], GRADE_ORDER.get(x["grade"], 9), x["strategy"], x["code"]))
    selected = []
    active_until = {}
    for t in candidates:
        if active_until.get(t["code"]) and t["entry_date"] <= active_until[t["code"]]:
            continue
        selected.append(t)
        active_until[t["code"]] = t["exit_date"]
    return selected


def main():
    groups = read(GROUPS_PATH)
    hist, idx, dates, didx = strat.load_histories(groups)
    if not dates:
        write(OUT, {"error": "no history"})
        return

    latest = dates[-1]
    # Last complete one-calendar-year window ending at latest available market date.
    y, m, d = map(int, latest.split("-"))
    try:
        start = f"{y-1:04d}-{m:02d}-{d+1:02d}"
        datetime.strptime(start, "%Y-%m-%d")
    except ValueError:
        # Safe fallback for month-end/leap edge cases.
        from datetime import date as dtdate, timedelta
        end_dt = dtdate(y, m, d)
        start = (end_dt.replace(year=y-1) + timedelta(days=1)).isoformat()

    events = build_activation_events(groups, hist, idx, dates)
    eby = {}
    for ev in events:
        eby.setdefault(ev["group"], []).append(ev)

    generated = []
    open_or_unscored = []
    for date in dates:
        if date < start or date > latest:
            continue
        alerts = generate_alerts_for_date(groups, hist, idx, dates, didx, date, events, eby)
        for a in alerts:
            rec = simulate(hist, idx, dates, didx, date, a)
            if rec:
                generated.append(rec)
            else:
                open_or_unscored.append({"signal_date": date, **a})

    strategy_names = [
        "發動續強・真領漲",
        "新轉強・當日落後補漲",
        "中期弱短期強・落後補漲",
        "高檔整理・長期強股",
        "修復中・弱股隔日當沖空",
    ]
    per_strategy = []
    for name in strategy_names:
        rows = [x for x in generated if x["strategy"] == name]
        per_strategy.append({"strategy": name, **stats(rows)})

    combined = combined_execution(generated)

    write(OUT, {
        "version": "WOO_5_STRATEGY_BACKTEST_V1",
        "rule_version": "WOO_STRATEGY_V1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_start": dates[0],
        "data_end": latest,
        "test_start": start,
        "test_end": latest,
        "position_size_ntd": POSITION_SIZE_NTD,
        "cost_model": "GROSS_NO_FEES_TAX_SLIPPAGE",
        "historical_universe_notes": [
            "6209 今國光 is excluded before 2026-10-07.",
            "4903 聯光通 is excluded before 2026-10-08.",
            "Other group membership is treated as currently defined because earlier membership-change history is not versioned."
        ],
        "strategy_stats": per_strategy,
        "combined_execution_rule": "same stock/same day keeps highest grade; while already held, later signals for that stock are skipped",
        "combined_stats": stats(combined),
        "completed_signal_count": len(generated),
        "open_or_unscored_count": len(open_or_unscored),
        "trades": generated,
        "combined_trades": combined,
        "open_or_unscored": open_or_unscored,
    })


if __name__ == "__main__":
    main()
