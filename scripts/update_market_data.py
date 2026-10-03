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
STATUS_PATH = ROOT / "docs" / "data" / "market_status.json"
API = "https://api.finmindtrade.com/api/v4/data"
TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()

# Current UI supports up to 1 year. Use 400 calendar days so the archive
# comfortably contains a full Taiwan-market year including holidays.
BACKFILL_DAYS = 400

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
            last_date = max(by_date)
            start = datetime.strptime(last_date, "%Y-%m-%d").date() + timedelta(days=1)
        else:
            start = default_start

        try:
            if start <= today:
                fetched = fetch_stock(code, start.isoformat(), today.isoformat())
                for row in compact_rows(fetched):
                    if row.get("date"):
                        by_date[row["date"]] = row

            rows = [by_date[d] for d in sorted(by_date)]
            # Keep the complete backfill window; do not silently drop old rows.
            rows = recompute_pct(rows)
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

        # Anonymous FinMind quota is 300/hour; 78 stocks is comfortably below it.
        time.sleep(0.25)

    write_json(LATEST_PATH, {
        "source": "FinMind TaiwanStockPrice",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "stocks": latest,
    })
    write_json(STATUS_PATH, {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "requested_stocks": len(members),
        "successes": successes,
        "failures": failures,
        "earliest_date": earliest_seen,
        "latest_date": latest_seen,
        "backfill_days": BACKFILL_DAYS,
    })

    # Fail the Action if a meaningful portion failed, but still save diagnostics.
    if len(failures) > max(3, len(members) // 10):
        raise SystemExit(f"Too many failures: {len(failures)}/{len(members)}")

if __name__ == "__main__":
    main()
