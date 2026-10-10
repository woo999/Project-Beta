#!/usr/bin/env python3
"""Leader first-limit-up event entry experiment. Research only."""
import json, os, sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "docs/data/a_repair_intraday_short_leader_limit_candidates.json"
OUT = ROOT / "docs/data/a_repair_intraday_short_leader_limit_entry_result.json"
API = "https://api.finmindtrade.com/api/v4/data"

def seconds(value):
    time = str(value).split(" ")[-1]
    h, m, s = time.split(":")
    return int(h)*3600 + int(m)*60 + float(s)

def tick_step(p):
    return .01 if p < 10 else .05 if p < 50 else .1 if p < 100 else .5 if p < 500 else 1 if p < 1000 else 5

def fetch_ticks(code, date):
    params = {"dataset": "TaiwanStockPriceTick", "data_id": code, "start_date": date}
    token = os.environ.get("FINMIND_TOKEN", "").strip()
    headers = {"User-Agent": "WOO-short-research/1.0"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(API + "?" + urlencode(params), headers=headers)
    try:
        with urlopen(req, timeout=40) as resp:
            payload = json.load(resp)
    except HTTPError as exc:
        try:
            body = json.loads(exc.read())
        except Exception:
            body = {}
        msg = str(body.get("msg", "")).lower()
        if "level" in msg or "sponsor" in msg or "backer" in msg:
            raise RuntimeError("HISTORICAL_TICK_ACCESS_LEVEL_REQUIRED") from None
        raise RuntimeError("HTTP_STATUS_" + str(exc.code)) from None
    if payload.get("status") not in (None, 200):
        raise RuntimeError("DATA_PROVIDER_NON_SUCCESS")
    out = []
    for row in payload.get("data", []):
        if str(row.get("date", ""))[:10] != date:
            raise RuntimeError("TICK_DATE_MISMATCH")
        try:
            t = seconds(row.get("Time") or row["date"])
            p = float(row["deal_price"])
            volume = float(row.get("volume", 0))
        except (KeyError, TypeError, ValueError):
            continue
        if 32400 <= t <= 48780 and p > 0 and volume > 0:
            out.append({"t": t, "price": p})
    out.sort(key=lambda row: row["t"])
    if not out:
        raise RuntimeError("NO_VALID_TICKS")
    return out

def validate_ticks(ticks, bar):
    # Ordinary auction/regular-lot trades are required, not partial-day data.
    if abs(ticks[0]["price"] - bar["open"]) > .00001:
        raise RuntimeError("TICK_OPEN_DOES_NOT_MATCH_DAILY")
    if abs(ticks[-1]["price"] - bar["close"]) > .00001:
        raise RuntimeError("TICK_CLOSE_DOES_NOT_MATCH_DAILY")
    if max(r["price"] for r in ticks) > bar["high"] + .00001 or min(r["price"] for r in ticks) < bar["low"] - .00001:
        raise RuntimeError("TICK_OUTSIDE_DAILY_RANGE")

def evaluate(candidate, peer_ticks, target_ticks, delay=1):
    events = []
    for peer in candidate["touching_peers"]:
        hits = [r for r in peer_ticks[peer["code"]] if abs(r["price"]-peer["upper"]) < .00001]
        if hits:
            events.append((hits[0]["t"], peer["code"], peer["name"]))
    if not events:
        return {"status": "NO_OBSERVED_PEER_LIMIT_TOUCH"}
    event = min(events)
    # Continuous matching ends at 13:25. A closing-only touch has no later entry.
    available = [r for r in target_ticks if event[0] + delay <= r["t"] < 48300]
    if not available:
        return {"status": "NO_CONTINUOUS_SESSION_ENTRY_AFTER_TRIGGER", "trigger_seconds": event[0], "leader": event[2]}
    entry = available[0]
    close = candidate["exit_price"]
    ret = (entry["price"]-close)/entry["price"]*100
    later = [r["price"] for r in target_ticks if r["t"] >= entry["t"]]
    adverse = (max(later)-entry["price"])/entry["price"]*100
    slip = entry["price"] - tick_step(entry["price"])
    slipped_ret = (slip-close)/slip*100
    return {"status":"ENTERED","leader":event[2],"leader_code":event[1],"trigger_seconds":event[0],
            "entry_seconds":entry["t"],"entry_proxy":entry["price"],"delay_seconds":delay,
            "close":close,"return_pct":ret,"mae_pct":adverse,
            "gross_pnl_ntd":candidate["allocated_ntd"]*ret/100,
            "one_tick_adverse_return_pct":slipped_ret,
            "one_tick_adverse_pnl_ntd":candidate["allocated_ntd"]*slipped_ret/100}

def run():
    source = json.loads(INPUT.read_text())
    result = {"generated_at":datetime.now(timezone.utc).isoformat(),"status":"RUNNING",
              "candidate_count":len(source["candidates"]),"definition":source["definition"],
              "allocation":"Reserve each of the original 96 opening-qualified signals' original pool share. Non-triggered shares remain idle; never allocate using future trigger counts.",
              "limitations":["Next observed trade is a market-entry proxy, not bid/ask execution; no size, fees, taxes, impact or availability model.",
                             "First peer to touch limit is the operational leader definition, not hindsight closing leader.",
                             "Only intraday trigger research; baseline and production rules unchanged."],
              "entries":[]}
    cache = {}
    def get(code,date,bar):
        key = (code,date)
        if key not in cache:
            vals = fetch_ticks(code,date)
            validate_ticks(vals,bar)
            cache[key] = vals
        return cache[key]
    for c in source["candidates"]:
        try:
            peers = {p["code"]:get(p["code"],c["entry_date"],p) for p in c["peers"] if p["code"] in {t["code"] for t in c["touching_peers"]}}
            target = get(c["code"],c["entry_date"],c["target_bar"])
            trials = {str(delay):evaluate(c,peers,target,delay) for delay in (1,5,10)}
            result["entries"].append({"date":c["entry_date"],"code":c["code"],"name":c["name"],
                                      "allocated_ntd":c["allocated_ntd"],"baseline_return_pct":c["baseline_return_pct"],"trials":trials})
        except RuntimeError as exc:
            reason = str(exc)
            result["entries"].append({"date":c["entry_date"],"name":c["name"],"status":"PENDING_DATA","reason":reason})
            if reason == "HISTORICAL_TICK_ACCESS_LEVEL_REQUIRED":
                result["status"]="BLOCKED_DATA_PERMISSION"
                result["blocker"]=reason
                break
        except Exception as exc:
            result["entries"].append({"date":c["entry_date"],"name":c["name"],"status":"PENDING_DATA","reason":type(exc).__name__})
    if result["status"] == "RUNNING":
        result["status"] = "COMPLETE" if all("trials" in r for r in result["entries"]) else "PARTIAL_DATA"
    for delay in (1,5,10):
        entered = [r["trials"][str(delay)] for r in result["entries"] if "trials" in r and r["trials"][str(delay)]["status"]=="ENTERED"]
        result.setdefault("summaries",{})[str(delay)]={"entered":len(entered),"wins":sum(r["return_pct"]>0 for r in entered),
               "losses":sum(r["return_pct"]<0 for r in entered),"flats":sum(r["return_pct"]==0 for r in entered),
               "gross_pnl_ntd":sum(r["gross_pnl_ntd"] for r in entered),
               "one_tick_adverse_pnl_ntd":sum(r["one_tick_adverse_pnl_ntd"] for r in entered)}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"processed":len(result["entries"]),"blocker":result.get("blocker")}))
    return result

if __name__ == "__main__":
    run()
