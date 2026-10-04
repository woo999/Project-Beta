#!/usr/bin/env python3
import json
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
HISTORY = DATA / "history"
GROUPS_PATH = DATA / "groups.json"
OUT_PATH = DATA / "backtest_monthly_v1.json"

PERIODS = (5, 10, 20, 60)
ELIGIBLE_STATES = {"結構完整", "新轉強"}

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

def load_histories(groups):
    out = {}
    names = {}
    for g in groups.get("groups", []):
        for m in g.get("members", []):
            code = m["code"]
            names[code] = m["name"]
            p = HISTORY / f"{code}.json"
            if p.exists():
                rows = read(p).get("rows", [])
                rows = [r for r in rows if isinstance(r.get("close"), (int, float)) and r.get("close") > 0 and r.get("date")]
                rows.sort(key=lambda r: r["date"])
                out[code] = rows
    return out, names

def build_maps(histories):
    row_index = {}
    all_dates = set()
    for code, rows in histories.items():
        row_index[code] = {r["date"]: i for i, r in enumerate(rows)}
        all_dates.update(r["date"] for r in rows)
    return row_index, sorted(all_dates)

def stock_return_at(histories, row_index, code, date, sessions):
    rows = histories.get(code)
    idx = row_index.get(code, {}).get(date)
    if rows is None or idx is None or idx < sessions:
        return None
    prev = rows[idx - sessions]["close"]
    now = rows[idx]["close"]
    if not prev:
        return None
    return (now / prev - 1) * 100

def stock_row_at(histories, row_index, code, date):
    idx = row_index.get(code, {}).get(date)
    if idx is None:
        return None
    return histories[code][idx]

def group_rank_maps(groups, histories, row_index, date):
    maps = {}
    for period in PERIODS:
        rows = []
        for g in groups.get("groups", []):
            vals = []
            for m in g.get("members", []):
                v = stock_return_at(histories, row_index, m["code"], date, period)
                if isinstance(v, (int, float)):
                    vals.append(v)
            if vals:
                rows.append({"name": g["name"], "ret": sum(vals) / len(vals)})
        rows.sort(key=lambda x: x["ret"], reverse=True)
        maps[period] = {x["name"]: {"rank": i + 1, "ret": x["ret"]} for i, x in enumerate(rows)}
    return maps

def one_month_states(groups, maps):
    out = {}
    for g in groups.get("groups", []):
        name = g["name"]
        d = {p: maps.get(p, {}).get(name) for p in PERIODS}
        if not all(d[p] for p in PERIODS):
            out[name] = {"label": "資料不足"}
            continue

        r60, r20, r10, r5 = d[60]["rank"], d[20]["rank"], d[10]["rank"], d[5]["rank"]
        ret60, ret20, ret10, ret5 = d[60]["ret"], d[20]["ret"], d[10]["ret"], d[5]["ret"]

        background = r60 <= 8 and ret60 > 0
        core = r20 <= 5 and ret20 > 0
        confirm = r10 <= 6 and ret10 > 0
        near_ok = r5 <= 8
        improving = r20 <= 10 and r10 < r20 and r5 <= r10 and ret20 > 0
        repairing = r20 >= 11 and r10 < r20 and r5 <= r10 and ret10 > 0 and ret5 > 0
        lost = (background or r20 <= 8) and ((r5 - r20) >= 6 or (r5 >= 12 and ret5 < 0))
        weakening = background and r20 >= 10 and r10 >= 9 and r5 >= 9 and ret20 <= 0
        weak = (not background) and r20 >= 12 and r10 >= 10 and r5 >= 10 and ret20 <= 0

        label = "觀察"
        if background and core and confirm and near_ok:
            label = "結構完整"
        elif (not background) and core and confirm and near_ok:
            label = "新轉強"
        elif improving:
            label = "轉強中"
        elif repairing:
            label = "修復中"
        elif lost:
            label = "失速"
        elif weakening:
            label = "轉弱"
        elif weak:
            label = "弱勢"
        elif background and r20 <= 8:
            label = "高檔整理"

        out[name] = {
            "label": label,
            "rank_60": r60, "rank_20": r20, "rank_10": r10, "rank_5": r5,
            "ret_60": round(ret60, 4), "ret_20": round(ret20, 4),
            "ret_10": round(ret10, 4), "ret_5": round(ret5, 4),
        }
    return out

def choose_stock(group, histories, row_index, date):
    candidates = []
    for m in group.get("members", []):
        code = m["code"]
        r20 = stock_return_at(histories, row_index, code, date, 20)
        r60 = stock_return_at(histories, row_index, code, date, 60)
        row = stock_row_at(histories, row_index, code, date)
        pct = row.get("pct") if row else None
        if not all(isinstance(x, (int, float)) for x in (r20, r60, pct)):
            continue
        # Locked before reading forward outcome:
        # positive 20d + positive 60d + avoid chase/breakdown day (-3% to +5%)
        if r20 > 0 and r60 > 0 and -3 <= pct <= 5:
            candidates.append({
                "code": code, "name": m["name"],
                "ret_20": r20, "ret_60": r60,
                "signal_day_pct": pct, "signal_close": row["close"],
            })
    candidates.sort(key=lambda x: x["ret_20"], reverse=True)
    return candidates[0] if candidates else None

def simulate_trade(histories, row_index, code, signal_date):
    rows = histories.get(code, [])
    signal_i = row_index.get(code, {}).get(signal_date)
    if signal_i is None:
        return None
    entry_i = signal_i + 1
    exit_i = entry_i + 19
    if entry_i >= len(rows) or exit_i >= len(rows):
        return None

    entry_row = rows[entry_i]
    entry = entry_row.get("open")
    if not isinstance(entry, (int, float)) or entry <= 0:
        return None

    stop_price = entry * 0.93
    mfe = None
    mae = None
    stop_exit = None

    for i in range(entry_i, exit_i + 1):
        r = rows[i]
        high, low, opn = r.get("high"), r.get("low"), r.get("open")
        if isinstance(high, (int, float)):
            v = (high / entry - 1) * 100
            mfe = v if mfe is None else max(mfe, v)
        if isinstance(low, (int, float)):
            v = (low / entry - 1) * 100
            mae = v if mae is None else min(mae, v)

        # Conservative gap handling: if open is already below stop, fill at open.
        if isinstance(opn, (int, float)) and opn <= stop_price:
            stop_exit = {
                "date": r["date"], "price": opn,
                "sessions": i - entry_i + 1, "reason": "gap_below_stop"
            }
            break
        if isinstance(low, (int, float)) and low <= stop_price:
            stop_exit = {
                "date": r["date"], "price": stop_price,
                "sessions": i - entry_i + 1, "reason": "hard_stop"
            }
            break

    fixed_exit = rows[exit_i]
    fixed_ret = (fixed_exit["close"] / entry - 1) * 100
    if stop_exit:
        stop_ret = (stop_exit["price"] / entry - 1) * 100
    else:
        stop_ret = fixed_ret

    return {
        "entry_date": entry_row["date"],
        "entry_price": round(entry, 4),
        "fixed_20d_exit_date": fixed_exit["date"],
        "fixed_20d_exit_price": round(fixed_exit["close"], 4),
        "fixed_20d_return_pct": round(fixed_ret, 4),
        "stop_variant_exit_date": stop_exit["date"] if stop_exit else fixed_exit["date"],
        "stop_variant_exit_price": round(stop_exit["price"] if stop_exit else fixed_exit["close"], 4),
        "stop_variant_return_pct": round(stop_ret, 4),
        "stop_variant_reason": stop_exit["reason"] if stop_exit else "20_sessions",
        "stop_variant_holding_sessions": stop_exit["sessions"] if stop_exit else 20,
        "mfe_pct": round(mfe, 4) if mfe is not None else None,
        "mae_pct": round(mae, 4) if mae is not None else None,
    }

def main():
    groups = read(GROUPS_PATH)
    histories, _ = load_histories(groups)
    row_index, dates = build_maps(histories)

    states_by_date = {}
    for i, d in enumerate(dates):
        if i < 60:
            continue
        maps = group_rank_maps(groups, histories, row_index, d)
        states_by_date[d] = one_month_states(groups, maps)

    signals = []
    for i in range(61, len(dates)):
        d, prev_d = dates[i], dates[i - 1]
        cur, prev = states_by_date.get(d), states_by_date.get(prev_d)
        if not cur or not prev:
            continue
        for g in groups.get("groups", []):
            name = g["name"]
            st, pst = cur.get(name), prev.get(name)
            if not st or not pst:
                continue
            eligible = st.get("label") in ELIGIBLE_STATES
            prev_eligible = pst.get("label") in ELIGIBLE_STATES
            if not eligible or prev_eligible:
                continue

            pick = choose_stock(g, histories, row_index, d)
            if not pick:
                continue
            sim = simulate_trade(histories, row_index, pick["code"], d)

            rec = {
                "signal_date": d,
                "group": name,
                "state": st["label"],
                "sector": st,
                "pick": {
                    "code": pick["code"], "name": pick["name"],
                    "ret_20": round(pick["ret_20"], 4),
                    "ret_60": round(pick["ret_60"], 4),
                    "signal_day_pct": round(pick["signal_day_pct"], 4),
                    "signal_close": pick["signal_close"],
                },
                "completed": sim is not None,
            }
            if sim:
                rec.update(sim)
            signals.append(rec)

    done = [x for x in signals if x["completed"]]
    fixed_returns = [x["fixed_20d_return_pct"] for x in done]
    stop_returns = [x["stop_variant_return_pct"] for x in done]

    summary = {
        "completed_trades": len(done),
        "open_or_unscored_signals": len(signals) - len(done),
        "fixed_20d": {
            "wins": sum(1 for x in fixed_returns if x > 0),
            "losses": sum(1 for x in fixed_returns if x <= 0),
            "win_rate_pct": round(sum(1 for x in fixed_returns if x > 0) / len(fixed_returns) * 100, 2) if fixed_returns else None,
            "avg_return_pct": round(mean(fixed_returns), 4) if fixed_returns else None,
            "median_return_pct": round(median(fixed_returns), 4) if fixed_returns else None,
        },
        "hard_stop_minus_7": {
            "wins": sum(1 for x in stop_returns if x > 0),
            "losses": sum(1 for x in stop_returns if x <= 0),
            "win_rate_pct": round(sum(1 for x in stop_returns if x > 0) / len(stop_returns) * 100, 2) if stop_returns else None,
            "avg_return_pct": round(mean(stop_returns), 4) if stop_returns else None,
            "median_return_pct": round(median(stop_returns), 4) if stop_returns else None,
            "stop_triggered": sum(1 for x in done if x["stop_variant_reason"] != "20_sessions"),
        },
        "avg_mfe_pct": round(mean([x["mfe_pct"] for x in done if x.get("mfe_pct") is not None]), 4) if done else None,
        "avg_mae_pct": round(mean([x["mae_pct"] for x in done if x.get("mae_pct") is not None]), 4) if done else None,
    }

    out = {
        "version": "M1_WALK_FORWARD_V1",
        "method": {
            "anti_hindsight": [
                "每個訊號日只使用該日及以前的收盤資料",
                "族群必須由非 eligible 狀態首次轉入 結構完整 或 新轉強",
                "訊號收盤後才成立，下一交易日開盤進場",
                "個股篩選規則在查看未來結果前固定",
            ],
            "sector_signal": "1個月結構首次進入 結構完整 / 新轉強",
            "stock_filter": "20日報酬>0、60日報酬>0、訊號日漲跌介於-3%~+5%；符合者取20日報酬最高",
            "entry": "下一交易日開盤",
            "outcome_a": "固定持有20個交易日（含進場日）後收盤",
            "outcome_b": "-7%硬停損，若未觸發則同樣持有20個交易日；跳空跌破停損以開盤價成交",
            "fees_tax_slippage": "未計入",
        },
        "data_start": dates[0] if dates else None,
        "data_end": dates[-1] if dates else None,
        "summary": summary,
        "signals": signals,
    }
    write(OUT_PATH, out)

if __name__ == "__main__":
    main()
