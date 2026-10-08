#!/usr/bin/env python3
import json, os, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
GROUPS_PATH = ROOT / "docs" / "data" / "groups.json"
HISTORY_DIR = ROOT / "docs" / "data" / "history"
LATEST_PATH = ROOT / "docs" / "data" / "latest.json"
SUMMARY_PATH = ROOT / "docs" / "data" / "summary.json"
DAILY_RANKINGS_PATH = ROOT / "docs" / "data" / "daily_rankings.json"
LEADER_MEMORY_PATH = ROOT / "docs" / "data" / "leader_memory.json"
STATUS_PATH = ROOT / "docs" / "data" / "market_status.json"
API = "https://api.finmindtrade.com/api/v4/data"
TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()
BACKFILL_DAYS = 700
RANGES = (5, 10, 20, 60, 120, 250)
# Daily rankings archive enabled.
# Leader memory archive enabled.

def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

def fetch_stock(code, start_date, end_date):
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": code,
        "start_date": start_date,
        "end_date": end_date,
    }
    headers = {"User-Agent": "WOO-FLOW/1.0"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = Request(API + "?" + urlencode(params), headers=headers)
    last_err = None
    for attempt in range(4):
        try:
            with urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("status") not in (200, None):
                raise RuntimeError(payload.get("msg") or f"FinMind status {payload.get('status')}")
            return payload.get("data", [])
        except (HTTPError, URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{code}: {last_err}")

def compact_rows(rows):
    out = []
    for r in rows:
        out.append({
            "date": r.get("date"),
            "open": r.get("open"),
            "high": r.get("max"),
            "low": r.get("min"),
            "close": r.get("close"),
            "volume": r.get("Trading_Volume"),
            "money": r.get("Trading_money"),
            "turnover": r.get("Trading_turnover"),
            "spread": r.get("spread"),
        })
    return out

def recompute_pct(rows):
    prev_close = None
    for r in rows:
        close = r.get("close")
        if isinstance(close, (int, float)) and close > 0:
            r["pct"] = None if not prev_close else round((close / prev_close - 1) * 100, 4)
            prev_close = close
        else:
            r["pct"] = None
    return rows

def stock_range_stats(rows, sessions):
    valid = [r for r in rows if isinstance(r.get("close"), (int, float)) and r.get("close") > 0]
    if not valid:
        return None
    tail = valid[-min(len(valid), sessions + 1):]
    latest = tail[-1]
    first = tail[0]
    period_return = None
    if len(tail) >= 2 and first["close"]:
        period_return = round((latest["close"] / first["close"] - 1) * 100, 4)
    session_rows = valid[-min(len(valid), sessions):]
    total_money = sum((r.get("money") or 0) for r in session_rows)
    positive_days = sum(1 for r in session_rows if isinstance(r.get("pct"), (int, float)) and r["pct"] > 0)
    negative_days = sum(1 for r in session_rows if isinstance(r.get("pct"), (int, float)) and r["pct"] < 0)
    avg_pct = None
    pcts = [r["pct"] for r in session_rows if isinstance(r.get("pct"), (int, float))]
    if pcts:
        avg_pct = round(sum(pcts) / len(pcts), 4)
    return {
        "sessions": len(session_rows),
        "start_date": first.get("date"),
        "end_date": latest.get("date"),
        "period_return": period_return,
        "avg_daily_pct": avg_pct,
        "positive_days": positive_days,
        "negative_days": negative_days,
        "total_money": total_money,
        "latest_close": latest.get("close"),
        "latest_pct": latest.get("pct"),
        "latest_money": latest.get("money"),
        "latest_volume": latest.get("volume"),
    }

def build_daily_rankings(groups, histories):
    names = {}
    by_code_date = {}
    all_dates = set()

    for g in groups.get("groups", []):
        for m in g.get("members", []):
            names[m["code"]] = m["name"]

    for code, rows in histories.items():
        daymap = {}
        for r in rows:
            d = r.get("date")
            if d:
                daymap[d] = r
                all_dates.add(d)
        by_code_date[code] = daymap

    days = []
    for d in sorted(all_dates):
        ranked = []
        for g in groups.get("groups", []):
            members = []
            for m in g.get("members", []):
                r = by_code_date.get(m["code"], {}).get(d)
                pct = r.get("pct") if r else None
                if isinstance(pct, (int, float)):
                    members.append({
                        "code": m["code"],
                        "name": m["name"],
                        "pct": round(pct, 4),
                        "money": r.get("money") or 0,
                        "volume": r.get("volume") or 0,
                        "close": r.get("close"),
                    })

            if not members:
                continue

            pcts = [x["pct"] for x in members]
            leaders = sorted(members, key=lambda x: x["pct"], reverse=True)[:3]
            ranked.append({
                "name": g["name"],
                "member_count": len(g.get("members", [])),
                "priced_members": len(members),
                "avg_pct": round(sum(pcts) / len(pcts), 4),
                "up_count": sum(1 for x in members if x["pct"] > 0),
                "down_count": sum(1 for x in members if x["pct"] < 0),
                "gt3_count": sum(1 for x in members if x["pct"] >= 3),
                "gt5_count": sum(1 for x in members if x["pct"] >= 5),
                "total_money": sum(x["money"] for x in members),
                "leaders": leaders,
            })

        ranked.sort(key=lambda x: x["avg_pct"], reverse=True)
        for i, g in enumerate(ranked, 1):
            g["rank"] = i

        if ranked:
            days.append({"date": d, "groups": ranked})

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "definition": {
            "group_daily_strength": "arithmetic mean of member daily pct returns",
            "leaders": "top 3 member daily pct returns within each group",
            "gt3_count": "members with daily pct >= 3%",
            "gt5_count": "members with daily pct >= 5%",
        },
        "days": days,
    }

def build_leader_memory(groups, daily_rankings, histories):
    result = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "definition": {
            "activation_day": "group rank <= 3 AND group average daily return >= 2% AND up ratio >= 60%",
            "leader_hit": "stock is strict top 3, OR is >=5% on the activation day and within 0.30 percentage points of the strict #3 return; this avoids treating near-tied strong stocks as non-leaders",
            "top3_hit": "stock appears in that group's strict top 3 daily returns on an activation day",
            "near_leader_hit": "stock is outside strict top 3 but >=5% and within 0.30 percentage points of the strict #3 return",
            "top1_hit": "stock ranks #1 by daily return inside the group on an activation day",
            "note": "close-to-close daily data only; this does not measure intraday first mover timing",
            "follow_through": "after a stock is in the expanded leader cohort on an activation day, measure close-to-close return 1/3/5 market trading days later; missing future prices are excluded",
            "group_follow_through": "for each activation event, average constituent close-to-close returns from activation-day close to 1/3/5 market trading days later; then average those event returns and report positive-event win rate",
            "leader_position_score": "on each activation day rank all priced members by daily pct; first place scores 100 and last place scores 0, linearly scaled in between; report the stock's average score across activation days",
        },
        "ranges": {},
    }

    all_days = daily_rankings.get("days", [])
    day_dates = [d.get("date") for d in all_days if d.get("date")]
    day_index = {d: i for i, d in enumerate(day_dates)}
    close_by_code_date = {}
    pct_by_code_date = {}
    for code, rows in histories.items():
        close_by_code_date[code] = {
            r.get("date"): r.get("close")
            for r in rows
            if r.get("date") and isinstance(r.get("close"), (int, float)) and r.get("close") > 0
        }
        pct_by_code_date[code] = {
            r.get("date"): r.get("pct")
            for r in rows
            if r.get("date") and isinstance(r.get("pct"), (int, float))
        }

    for sessions in RANGES:
        days = all_days[-min(len(all_days), sessions):]
        group_out = []

        for g in groups.get("groups", []):
            group_name = g["name"]
            member_meta = {m["code"]: m["name"] for m in g.get("members", [])}
            counts = {
                code: {
                    "code": code,
                    "name": name,
                    "leader_count": 0,
                    "near_leader_count": 0,
                    "top3_count": 0,
                    "top1_count": 0,
                    "leader_pct_sum": 0.0,
                    "leader_pct_obs": 0,
                    "rank_sum": 0.0,
                    "position_score_sum": 0.0,
                    "position_obs": 0,
                    "follow_returns": {"1": [], "3": [], "5": []},
                }
                for code, name in member_meta.items()
            }

            events = []
            group_follow_returns = {"1": [], "3": [], "5": []}
            for day in days:
                gr = next((x for x in day.get("groups", []) if x.get("name") == group_name), None)
                if not gr:
                    continue
                priced = gr.get("priced_members") or 0
                up_ratio = (gr.get("up_count") or 0) / priced if priced else 0
                is_activation = (
                    (gr.get("rank") or 999) <= 3
                    and isinstance(gr.get("avg_pct"), (int, float))
                    and gr["avg_pct"] >= 2
                    and up_ratio >= 0.60
                )
                if not is_activation:
                    continue

                strict_leaders = gr.get("leaders", [])[:3]
                third_pct = strict_leaders[2].get("pct") if len(strict_leaders) >= 3 else None
                event_date = day.get("date")
                event_pos = day_index.get(event_date)
                event_group_follow = {}

                ranked_members = []
                for code, name in member_meta.items():
                    pct = pct_by_code_date.get(code, {}).get(event_date)
                    if isinstance(pct, (int, float)):
                        ranked_members.append((code, name, pct))
                ranked_members.sort(key=lambda x: x[2], reverse=True)
                ranked_count = len(ranked_members)

                strict_codes = {x.get("code") for x in strict_leaders}
                leader_cohort = []
                for rank_pos, (code, name, pct) in enumerate(ranked_members, 1):
                    is_strict_top3 = code in strict_codes
                    is_near_leader = (
                        not is_strict_top3
                        and isinstance(third_pct, (int, float))
                        and pct >= 5.0
                        and pct >= third_pct - 0.30
                    )
                    if is_strict_top3 or is_near_leader:
                        leader_cohort.append({
                            "code": code,
                            "name": name,
                            "pct": round(pct, 4),
                            "rank": rank_pos,
                            "leader_type": "TOP3" if is_strict_top3 else "NEAR_TOP3",
                        })

                for rank_pos, (code, _name, _pct) in enumerate(ranked_members, 1):
                    if code not in counts:
                        continue
                    position_score = 100.0 if ranked_count <= 1 else (ranked_count - rank_pos) / (ranked_count - 1) * 100
                    counts[code]["rank_sum"] += rank_pos
                    counts[code]["position_score_sum"] += position_score
                    counts[code]["position_obs"] += 1

                if event_pos is not None:
                    for horizon in (1, 3, 5):
                        target_pos = event_pos + horizon
                        if target_pos >= len(day_dates):
                            continue
                        target_date = day_dates[target_pos]
                        member_returns = []
                        for code in member_meta:
                            base_close = close_by_code_date.get(code, {}).get(event_date)
                            target_close = close_by_code_date.get(code, {}).get(target_date)
                            if (
                                isinstance(base_close, (int, float)) and base_close > 0
                                and isinstance(target_close, (int, float)) and target_close > 0
                            ):
                                member_returns.append((target_close / base_close - 1) * 100)

                        if member_returns:
                            group_ret = round(sum(member_returns) / len(member_returns), 4)
                            group_follow_returns[str(horizon)].append(group_ret)
                            event_group_follow[str(horizon)] = {
                                "return": group_ret,
                                "member_samples": len(member_returns),
                                "target_date": target_date,
                            }

                events.append({
                    "date": day["date"],
                    "rank": gr.get("rank"),
                    "avg_pct": gr.get("avg_pct"),
                    "up_count": gr.get("up_count"),
                    "priced_members": priced,
                    "leaders": strict_leaders,
                    "leader_cohort": leader_cohort,
                    "group_follow_through": event_group_follow,
                })

                for leader in leader_cohort:
                    code = leader.get("code")
                    if code not in counts:
                        continue
                    counts[code]["leader_count"] += 1
                    if leader.get("leader_type") == "TOP3":
                        counts[code]["top3_count"] += 1
                    else:
                        counts[code]["near_leader_count"] += 1
                    if leader.get("rank") == 1:
                        counts[code]["top1_count"] += 1
                    pct = leader.get("pct")
                    if isinstance(pct, (int, float)):
                        counts[code]["leader_pct_sum"] += pct
                        counts[code]["leader_pct_obs"] += 1

                    event_date = day.get("date")
                    event_pos = day_index.get(event_date)
                    base_close = close_by_code_date.get(code, {}).get(event_date)
                    if event_pos is not None and isinstance(base_close, (int, float)) and base_close > 0:
                        for horizon in (1, 3, 5):
                            target_pos = event_pos + horizon
                            if target_pos >= len(day_dates):
                                continue
                            target_date = day_dates[target_pos]
                            target_close = close_by_code_date.get(code, {}).get(target_date)
                            if isinstance(target_close, (int, float)) and target_close > 0:
                                ret = round((target_close / base_close - 1) * 100, 4)
                                counts[code]["follow_returns"][str(horizon)].append(ret)

            activation_days = len(events)
            stocks = []
            for item in counts.values():
                obs = item.pop("leader_pct_obs")
                pct_sum = item.pop("leader_pct_sum")
                rank_sum = item.pop("rank_sum")
                position_score_sum = item.pop("position_score_sum")
                position_obs = item.pop("position_obs")
                follow_returns = item.pop("follow_returns")
                item["activation_days"] = activation_days
                item["leader_rate"] = round(item["leader_count"] / activation_days * 100, 2) if activation_days else 0
                item["near_leader_rate"] = round(item["near_leader_count"] / activation_days * 100, 2) if activation_days else 0
                item["top3_rate"] = round(item["top3_count"] / activation_days * 100, 2) if activation_days else 0
                item["top1_rate"] = round(item["top1_count"] / activation_days * 100, 2) if activation_days else 0
                item["avg_pct_when_leader"] = round(pct_sum / obs, 4) if obs else None
                item["position_samples"] = position_obs
                item["avg_rank_when_activation"] = round(rank_sum / position_obs, 4) if position_obs else None
                item["leader_position_score"] = round(position_score_sum / position_obs, 2) if position_obs else None
                item["follow_through"] = {}
                for horizon in ("1", "3", "5"):
                    vals = follow_returns.get(horizon, [])
                    samples = len(vals)
                    item["follow_through"][horizon] = {
                        "samples": samples,
                        "avg_return": round(sum(vals) / samples, 4) if samples else None,
                        "win_rate": round(sum(1 for v in vals if v > 0) / samples * 100, 2) if samples else None,
                    }
                stocks.append(item)

            stocks.sort(key=lambda x: (
                x["leader_position_score"] if x["leader_position_score"] is not None else -999999,
                x["leader_rate"],
                x["top1_count"],
                x["top3_count"],
                x["avg_pct_when_leader"] if x["avg_pct_when_leader"] is not None else -999999
            ), reverse=True)

            group_follow_through = {}
            for horizon in ("1", "3", "5"):
                vals = group_follow_returns.get(horizon, [])
                samples = len(vals)
                group_follow_through[horizon] = {
                    "samples": samples,
                    "avg_return": round(sum(vals) / samples, 4) if samples else None,
                    "win_rate": round(sum(1 for v in vals if v > 0) / samples * 100, 2) if samples else None,
                }

            group_out.append({
                "name": group_name,
                "activation_days": activation_days,
                "group_follow_through": group_follow_through,
                "events": events,
                "stocks": stocks,
            })

        result["ranges"][str(sessions)] = {"groups": group_out}

    return result


def build_summary(groups, histories, latest):
    now = datetime.now(timezone.utc).isoformat()
    stock_stats = {}
    for code, rows in histories.items():
        stock_stats[code] = {str(n): stock_range_stats(rows, n) for n in RANGES}

    ranges = {}
    for n in RANGES:
        key = str(n)
        group_stats = []
        for g in groups.get("groups", []):
            member_stats = []
            for m in g.get("members", []):
                st = stock_stats.get(m["code"], {}).get(key)
                if st and st.get("period_return") is not None:
                    member_stats.append({
                        "code": m["code"],
                        "name": m["name"],
                        **st,
                    })
            returns = [x["period_return"] for x in member_stats if x.get("period_return") is not None]
            latest_pcts = [x["latest_pct"] for x in member_stats if isinstance(x.get("latest_pct"), (int, float))]
            total_money = sum((x.get("total_money") or 0) for x in member_stats)
            latest_money = sum((x.get("latest_money") or 0) for x in member_stats)
            avg_return = round(sum(returns) / len(returns), 4) if returns else None
            avg_latest_pct = round(sum(latest_pcts) / len(latest_pcts), 4) if latest_pcts else None
            leaders = sorted(member_stats, key=lambda x: x.get("period_return") if x.get("period_return") is not None else -999999, reverse=True)
            group_stats.append({
                "name": g["name"],
                "member_count": len(g.get("members", [])),
                "avg_return": avg_return,
                "avg_latest_pct": avg_latest_pct,
                "total_money": total_money,
                "latest_money": latest_money,
                "leaders": leaders[:5],
            })
        ordered = sorted(group_stats, key=lambda x: x.get("avg_return") if x.get("avg_return") is not None else -999999, reverse=True)
        ranges[key] = {
            "groups": group_stats,
            "strongest_group": ordered[0]["name"] if ordered and ordered[0].get("avg_return") is not None else None,
            "strongest_group_return": ordered[0]["avg_return"] if ordered and ordered[0].get("avg_return") is not None else None,
        }

    latest_money_unique = sum((x.get("money") or 0) for x in latest.values())
    latest_date = max((x.get("date") for x in latest.values() if x.get("date")), default=None)

    return {
        "updated_at": now,
        "latest_date": latest_date,
        "tracked_stock_count": len(latest),
        "latest_money_unique": latest_money_unique,
        "ranges": ranges,
        "stocks": stock_stats,
    }

def main():
    groups = read_json(GROUPS_PATH, {})
    members = {}
    for g in groups.get("groups", []):
        for m in g.get("members", []):
            members[m["code"]] = m["name"]

    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    default_start = today - timedelta(days=BACKFILL_DAYS)
    latest = {}
    histories = {}
    failures = []
    successes = 0
    earliest_seen = None
    latest_seen = None

    for idx, (code, name) in enumerate(sorted(members.items()), 1):
        path = HISTORY_DIR / f"{code}.json"
        old = read_json(path, {"code": code, "name": name, "rows": []})
        old_rows = old.get("rows", [])
        by_date = {r["date"]: r for r in old_rows if r.get("date")}

        if by_date:
            first_date = min(by_date)
            last_date = max(by_date)
            start = datetime.strptime(last_date, "%Y-%m-%d").date() + timedelta(days=1)
            backfill_end = datetime.strptime(first_date, "%Y-%m-%d").date() - timedelta(days=1)
        else:
            start = default_start
            backfill_end = None

        try:
            if backfill_end is not None and default_start <= backfill_end:
                fetched_old = fetch_stock(code, default_start.isoformat(), backfill_end.isoformat())
                for row in compact_rows(fetched_old):
                    if row.get("date"):
                        by_date[row["date"]] = row

            if start <= today:
                fetched = fetch_stock(code, start.isoformat(), today.isoformat())
                for row in compact_rows(fetched):
                    if row.get("date"):
                        by_date[row["date"]] = row

            rows = recompute_pct([by_date[d] for d in sorted(by_date)])
            histories[code] = rows
            archive = {
                "code": code,
                "name": name,
                "source": "FinMind TaiwanStockPrice",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "rows": rows,
            }
            write_json(path, archive)

            valid = [r for r in rows if isinstance(r.get("close"), (int, float)) and r.get("close") > 0]
            if valid:
                latest[code] = {"code": code, "name": name, **valid[-1]}
                earliest_seen = valid[0]["date"] if earliest_seen is None else min(earliest_seen, valid[0]["date"])
                latest_seen = valid[-1]["date"] if latest_seen is None else max(latest_seen, valid[-1]["date"])
            successes += 1
            print(f"[{idx}/{len(members)}] {code} {name}: {len(rows)} rows")
        except Exception as e:
            failures.append({"code": code, "name": name, "error": str(e)})
            print(f"[{idx}/{len(members)}] ERROR {code} {name}: {e}")
        time.sleep(0.25)

    write_json(LATEST_PATH, {
        "source": "FinMind TaiwanStockPrice",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "stocks": latest,
    })
    write_json(SUMMARY_PATH, build_summary(groups, histories, latest))
    daily_rankings = build_daily_rankings(groups, histories)
    write_json(DAILY_RANKINGS_PATH, daily_rankings)
    write_json(LEADER_MEMORY_PATH, build_leader_memory(groups, daily_rankings, histories))
    write_json(STATUS_PATH, {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "requested_stocks": len(members),
        "successes": successes,
        "failures": failures,
        "earliest_date": earliest_seen,
        "latest_date": latest_seen,
        "backfill_days": BACKFILL_DAYS,
    })

    if len(failures) > max(3, len(members) // 10):
        raise SystemExit(f"Too many failures: {len(failures)}/{len(members)}")

if __name__ == "__main__":
    main()
