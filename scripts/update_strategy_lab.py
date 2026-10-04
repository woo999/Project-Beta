#!/usr/bin/env python3
import json
from pathlib import Path
from datetime import datetime, timezone
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
HISTORY = DATA / "history"
ALERTS_PATH = DATA / "strategy_alerts.json"
OUT = DATA / "strategy_lab.json"

RULE_VERSION = "WOO_STRATEGY_V1"
LOCKED_AT = "2026-10-04"
NEXT_REVIEW_DATE = "2026-10-11"

def read(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))

def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

def history(code):
    p = HISTORY / f"{code}.json"
    if not p.exists():
        return []
    rows = read(p, {}).get("rows", [])
    rows = [r for r in rows if r.get("date") and isinstance(r.get("close"), (int, float))]
    rows.sort(key=lambda r: r["date"])
    return rows

def signal_id(a, signal_date):
    return "|".join([
        RULE_VERSION,
        signal_date or "",
        a.get("strategy") or "",
        a.get("code") or "",
        a.get("side") or "",
    ])

def calc_path_metrics(rows, start_i, end_i, entry_price, side):
    if start_i is None or end_i is None or end_i < start_i or entry_price <= 0:
        return None, None
    window = rows[start_i:end_i + 1]
    highs = [r.get("high") for r in window if isinstance(r.get("high"), (int, float))]
    lows = [r.get("low") for r in window if isinstance(r.get("low"), (int, float))]
    if not highs or not lows:
        return None, None
    if side == "SHORT":
        mfe = (entry_price - min(lows)) / entry_price * 100
        mae = (entry_price - max(highs)) / entry_price * 100
    else:
        mfe = (max(highs) / entry_price - 1) * 100
        mae = (min(lows) / entry_price - 1) * 100
    return round(mfe, 4), round(mae, 4)

def evaluate(record):
    rows = history(record["code"])
    idx = {r["date"]: i for i, r in enumerate(rows)}
    signal_date = record["signal_date"]
    si = idx.get(signal_date)
    if si is None:
        record["status"] = "WAIT_DATA"
        return record

    holding = int(record.get("holding_days") or 1)
    entry_i = si + 1
    exit_i = si + holding

    if entry_i >= len(rows):
        record["status"] = "WAIT_ENTRY"
        return record

    entry_row = rows[entry_i]
    entry_price = entry_row.get("open")
    if not isinstance(entry_price, (int, float)) or entry_price <= 0:
        record["status"] = "WAIT_ENTRY"
        return record

    record["entry"] = {
        "date": entry_row["date"],
        "price": round(entry_price, 4),
        "basis": "NEXT_OPEN",
    }

    latest_row = rows[-1]
    current_close = latest_row.get("close")
    if isinstance(current_close, (int, float)) and current_close > 0:
        if record["side"] == "SHORT":
            current_ret = (entry_price - current_close) / entry_price * 100
        else:
            current_ret = (current_close / entry_price - 1) * 100
        record["current"] = {
            "date": latest_row["date"],
            "close": round(current_close, 4),
            "gross_return_pct": round(current_ret, 4),
        }

    if exit_i >= len(rows):
        record["status"] = "OPEN"
        mfe, mae = calc_path_metrics(rows, entry_i, len(rows)-1, entry_price, record["side"])
        record["mfe_pct"] = mfe
        record["mae_pct"] = mae
        return record

    exit_row = rows[exit_i]
    exit_price = exit_row.get("close")
    if not isinstance(exit_price, (int, float)) or exit_price <= 0:
        record["status"] = "OPEN"
        return record

    if record["side"] == "SHORT":
        ret = (entry_price - exit_price) / entry_price * 100
    else:
        ret = (exit_price / entry_price - 1) * 100

    mfe, mae = calc_path_metrics(rows, entry_i, exit_i, entry_price, record["side"])
    record["exit"] = {
        "date": exit_row["date"],
        "price": round(exit_price, 4),
        "basis": "CLOSE",
    }
    record["gross_return_pct"] = round(ret, 4)
    record["result"] = "WIN" if ret > 0 else "LOSS" if ret < 0 else "FLAT"
    record["status"] = "COMPLETED"
    record["mfe_pct"] = mfe
    record["mae_pct"] = mae
    return record

def strategy_stats(records):
    out = []
    names = sorted({r.get("strategy") for r in records if r.get("strategy")})
    for name in names:
        rows = [r for r in records if r.get("strategy") == name]
        completed = [r for r in rows if r.get("status") == "COMPLETED" and isinstance(r.get("gross_return_pct"), (int, float))]
        vals = [r["gross_return_pct"] for r in completed]
        wins = sum(v > 0 for v in vals)
        losses = sum(v < 0 for v in vals)
        out.append({
            "strategy": name,
            "grade": rows[-1].get("grade"),
            "signals": len(rows),
            "completed": len(completed),
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(wins / len(completed) * 100, 2) if completed else None,
            "avg_return_pct": round(mean(vals), 4) if vals else None,
            "median_return_pct": round(median(vals), 4) if vals else None,
        })
    return out

def main():
    alerts = read(ALERTS_PATH, {}) or {}
    lab = read(OUT, None)
    if not lab:
        lab = {
            "schema_version": 1,
            "rule_version": RULE_VERSION,
            "locked_at": LOCKED_AT,
            "next_review_date": NEXT_REVIEW_DATE,
            "principle": "訊號產生後永久保留當時規則與等級；之後規則更新不得回寫舊訊號。",
            "cost_model": "GROSS_NO_FEES_TAX_SLIPPAGE",
            "signals": [],
        }

    # Do not silently migrate an existing lab to another rule version.
    if lab.get("rule_version") != RULE_VERSION:
        raise RuntimeError(f"strategy lab rule version mismatch: {lab.get('rule_version')} != {RULE_VERSION}")

    signal_date = alerts.get("latest_date")
    existing = {r.get("id"): r for r in lab.get("signals", [])}

    if signal_date:
        for a in alerts.get("alerts", []):
            sid = signal_id(a, signal_date)
            if sid in existing:
                continue
            rec = {
                "id": sid,
                "rule_version": RULE_VERSION,
                "signal_date": signal_date,
                "grade": a.get("grade"),
                "strategy": a.get("strategy"),
                "group": a.get("group"),
                "code": a.get("code"),
                "name": a.get("name"),
                "side": a.get("side"),
                "holding_days": int(a.get("holding_days") or 1),
                "signal_status": a.get("status"),
                "reason": a.get("reason"),
                "status": "WAIT_ENTRY",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            lab.setdefault("signals", []).append(rec)
            existing[sid] = rec

    lab["signals"] = [evaluate(r) for r in lab.get("signals", [])]
    lab["signals"].sort(key=lambda r: (r.get("signal_date") or "", r.get("strategy") or "", r.get("code") or ""))
    lab["strategy_stats"] = strategy_stats(lab["signals"])
    lab["updated_at"] = datetime.now(timezone.utc).isoformat()
    lab["latest_market_date"] = alerts.get("latest_date")

    counts = {
        "signals": len(lab["signals"]),
        "waiting_entry": sum(r.get("status") == "WAIT_ENTRY" for r in lab["signals"]),
        "open": sum(r.get("status") == "OPEN" for r in lab["signals"]),
        "completed": sum(r.get("status") == "COMPLETED" for r in lab["signals"]),
    }
    lab["summary"] = counts
    write(OUT, lab)

if __name__ == "__main__":
    main()
