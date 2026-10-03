#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
TRADES_PATH = DATA / "monthly_trades.json"
SUMMARY_PATH = DATA / "summary.json"
DAILY_PATH = DATA / "daily_rankings.json"
MEMORY_PATH = DATA / "leader_memory.json"
GROUPS_PATH = DATA / "groups.json"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

def rank_map(summary, period):
    groups = summary.get("ranges", {}).get(str(period), {}).get("groups", [])
    rows = [g for g in groups if isinstance(g.get("avg_return"), (int, float))]
    rows.sort(key=lambda g: g["avg_return"], reverse=True)
    return {g["name"]: i + 1 for i, g in enumerate(rows)}

def group_stat(summary, name, period):
    return next((g for g in summary.get("ranges", {}).get(str(period), {}).get("groups", []) if g.get("name") == name), None)

def one_month_state(summary, name):
    ranks = {p: rank_map(summary, p).get(name) for p in (60, 20, 10, 5)}
    stats = {p: group_stat(summary, name, p) for p in (60, 20, 10, 5)}
    rets = {p: (stats[p] or {}).get("avg_return") for p in (60, 20, 10, 5)}
    if not all(isinstance(ranks[p], int) for p in ranks) or not isinstance(rets[20], (int, float)):
        return "資料不足"

    background = ranks[60] <= 8 and isinstance(rets[60], (int, float)) and rets[60] > 0
    core = ranks[20] <= 5 and rets[20] > 0
    confirm = ranks[10] <= 6 and isinstance(rets[10], (int, float)) and rets[10] > 0
    near_ok = ranks[5] <= 8
    improving = ranks[20] <= 10 and ranks[10] < ranks[20] and ranks[5] <= ranks[10] and rets[20] > 0
    repairing = ranks[20] >= 11 and ranks[10] < ranks[20] and ranks[5] <= ranks[10] and isinstance(rets[10], (int, float)) and rets[10] > 0 and isinstance(rets[5], (int, float)) and rets[5] > 0
    lost = (background or ranks[20] <= 8) and ((ranks[5] - ranks[20]) >= 6 or (ranks[5] >= 12 and isinstance(rets[5], (int, float)) and rets[5] < 0))
    weakening = background and ranks[20] >= 10 and ranks[10] >= 9 and ranks[5] >= 9 and rets[20] <= 0
    weak = (not background) and ranks[20] >= 12 and ranks[10] >= 10 and ranks[5] >= 10 and rets[20] <= 0

    if background and core and confirm and near_ok:
        return "結構完整"
    if (not background) and core and confirm and near_ok:
        return "新轉強"
    if improving:
        return "轉強中"
    if repairing:
        return "修復中"
    if lost:
        return "失速"
    if weakening:
        return "轉弱"
    if weak:
        return "弱勢"
    if background and ranks[20] <= 8:
        return "高檔整理"
    return "觀察"

def find_group(groups, code):
    for g in groups.get("groups", []):
        if any(m.get("code") == code for m in g.get("members", [])):
            return g.get("name")
    return None

def latest_daily_group(daily, name):
    days = daily.get("days", [])
    if not days:
        return None
    return next((g for g in days[-1].get("groups", []) if g.get("name") == name), None)

def memory_stock(memory, name, period, code):
    group = next((g for g in memory.get("ranges", {}).get(str(period), {}).get("groups", []) if g.get("name") == name), None)
    if not group:
        return None, None
    stock = next((s for s in group.get("stocks", []) if s.get("code") == code), None)
    return group, stock

def main():
    if not TRADES_PATH.exists():
        return
    journal = read(TRADES_PATH)
    summary = read(SUMMARY_PATH)
    daily = read(DAILY_PATH)
    memory = read(MEMORY_PATH)
    groups = read(GROUPS_PATH)
    latest_date = summary.get("latest_date")
    if not latest_date:
        return

    changed = False
    for trade in journal.get("trades", []):
        if trade.get("status") not in ("OPEN", "PARTIAL"):
            continue
        code = trade.get("code")
        group = trade.get("group") or find_group(groups, code)
        if not code or not group:
            continue
        snaps = trade.setdefault("snapshots", [])
        if any(s.get("date") == latest_date for s in snaps):
            continue

        stock_ranges = summary.get("stocks", {}).get(code, {})
        gs = {p: group_stat(summary, group, p) for p in (60, 20, 10, 5)}
        ranks = {p: rank_map(summary, p).get(group) for p in (60, 20, 10, 5)}
        latest_stock = stock_ranges.get("5") or stock_ranges.get("20") or {}
        daily_group = latest_daily_group(daily, group)
        mg20, ms20 = memory_stock(memory, group, 20, code)
        mg60, ms60 = memory_stock(memory, group, 60, code)

        entry_price = trade.get("entry", {}).get("avg_price")
        close = latest_stock.get("latest_close")
        unrealized = None
        if isinstance(entry_price, (int, float)) and entry_price > 0 and isinstance(close, (int, float)):
            unrealized = round((close / entry_price - 1) * 100, 4)

        snaps.append({
            "date": latest_date,
            "close": close,
            "daily_pct": latest_stock.get("latest_pct"),
            "unrealized_return_pct": unrealized,
            "stock_returns": {str(p): (stock_ranges.get(str(p)) or {}).get("period_return") for p in (5, 10, 20, 60)},
            "sector": {
                "name": group,
                "one_month_state": one_month_state(summary, group),
                "ranks": {str(p): ranks[p] for p in (5, 10, 20, 60)},
                "returns": {str(p): (gs[p] or {}).get("avg_return") for p in (5, 10, 20, 60)},
                "daily_rank": (daily_group or {}).get("rank"),
                "daily_avg_pct": (daily_group or {}).get("avg_pct")
            },
            "dna_20": {
                "activation_days": (mg20 or {}).get("activation_days"),
                "leader_position_score": (ms20 or {}).get("leader_position_score"),
                "top1_rate": (ms20 or {}).get("top1_rate")
            },
            "dna_60": {
                "activation_days": (mg60 or {}).get("activation_days"),
                "leader_position_score": (ms60 or {}).get("leader_position_score"),
                "top1_rate": (ms60 or {}).get("top1_rate")
            }
        })
        changed = True

    if changed:
        journal["updated_at"] = datetime.now(timezone.utc).isoformat()
        write(TRADES_PATH, journal)

if __name__ == "__main__":
    main()
