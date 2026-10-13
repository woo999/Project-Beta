#!/usr/bin/env python3
"""Independent research overlay: four LONG signals, next-day intraday exit.
No modification of WOO_STRATEGY_V1. API key comes exclusively from environment.
"""
import collections, datetime as dt, json, os, pathlib, time, urllib.error, urllib.parse, urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
SRC=ROOT/"docs/data/backtest_woo_strategies_v1.json"
OUT=ROOT/"docs/data/research_long_intraday_night.json"
KEY=os.environ.get("FUGLE_API_KEY","").strip()
if not KEY: raise SystemExit("FUGLE_API_KEY missing (configure GitHub Actions secret)")
def get(url, params):
    q=urllib.parse.urlencode(params)
    req=urllib.request.Request(url+"?"+q,headers={"X-API-KEY":KEY,"Accept":"application/json"})
    for n in range(4):
        try:
            with urllib.request.urlopen(req,timeout=45) as r: return json.load(r).get("data",[])
        except urllib.error.HTTPError as e:
            if e.code==404: return []
            if e.code in (401,403): raise RuntimeError("Fugle authorization/plan denied (HTTP %s)"%e.code)
            if e.code!=429 and e.code<500: raise RuntimeError("Fugle HTTP %s"%e.code)
            if n==3: raise
            time.sleep(2**n*3)
def stock(code,day):
    url="https://api.fugle.tw/marketdata/v1.0/stock/historical/candles/"+urllib.parse.quote(code)
    return get(url,{"from":day,"to":day,"timeframe":"1","sort":"asc"})
def night(day):
    url="https://api.fugle.tw/marketdata/v1.0/futopt/historical/candles/TXF"
    return get(url,{"contractMonth":"1!","from":day,"to":day,"timeframe":"60","session":"afterhours","sort":"asc"})
def tstamp(r): return dt.datetime.fromisoformat(r["date"].replace("Z","+00:00")).astimezone(dt.timezone(dt.timedelta(hours=8)))
def price(r,k): return r.get(k) if isinstance(r.get(k),(int,float)) and r[k]>0 else None
def calc(rows,mode):
    vals=[r[mode] for r in rows if r.get(mode) is not None]
    return {"trades":len(vals),"wins":sum(x>0 for x in vals),"losses":sum(x<0 for x in vals),"flats":sum(x==0 for x in vals),"win_rate_pct":round(100*sum(x>0 for x in vals)/len(vals),2) if vals else None,"avg_gross_pct":round(sum(vals)/len(vals),4) if vals else None,"gross_pnl_ntd_at_500k":round(sum(vals)*5000,2)}
def main():
    src=json.loads(SRC.read_text(encoding="utf-8"))
    trades=[t for t in src["trades"] if t.get("side")=="LONG" and t.get("entry_date") and t.get("exit_date")]
    pairs=sorted(set((t["code"],t["entry_date"]) for t in trades))
    days=sorted(set(d for _,d in pairs))
    scache={}; ncache={}; errors=[]
    for i,(code,day) in enumerate(pairs,1):
        try: scache[(code,day)]=stock(code,day)
        except Exception as e: errors.append({"code":code,"date":day,"source":"stock","error":str(e)[:180]})
        if i%40==0: print("stock requests",i,"/",len(pairs),flush=True)
        time.sleep(.12)
    for day in days:
        try: ncache[day]=night(day)
        except Exception as e: errors.append({"date":day,"source":"night","error":str(e)[:180]})
        time.sleep(.12)
    results=[]
    for t in trades:
        code,day=t["code"],t["entry_date"]
        bars=sorted(scache.get((code,day),[]),key=lambda x:x["date"])
        reg=[b for b in bars if tstamp(b).date().isoformat()==day and dt.time(9,0)<=tstamp(b).time()<=dt.time(13,30)]
        opening=next((price(b,"open") for b in reg if tstamp(b).time()==dt.time(9,0)),None)
        delayed=next((price(b,"open") for b in reg if tstamp(b).time()==dt.time(9,30)),None)
        # 13:30 auction close is not guaranteed by minute bars; prefer authoritative daily OHLC exit
        closing=next((price(b,"close") for b in reversed(reg) if tstamp(b).time()==dt.time(13,30)),None)
        if closing is None and reg: closing=price(reg[-1],"close")
        nb=sorted(ncache.get(day,[]),key=lambda x:x["date"])
        night_open=price(nb[0],"open") if nb else None
        night_close=price(nb[-1],"close") if nb else None
        direction="UP" if night_open and night_close and night_close>night_open else "DOWN" if night_open and night_close and night_close<night_open else "FLAT" if night_open and night_close else "MISSING"
        def ret(p): return round((closing/p-1)*100,6) if p and closing else None
        results.append({"strategy":t["strategy"],"code":code,"name":t.get("name"),"signal_date":t["signal_date"],"entry_date":day,"night_direction":direction,"night_open":night_open,"night_close":night_close,"open_0900":opening,"open_0930":delayed,"close":closing,"baseline":ret(opening),"night_rule":ret(opening if direction=="UP" else delayed if direction=="DOWN" else None)})
    by={}
    for strategy in sorted(set(t["strategy"] for t in trades)):
        sub=[r for r in results if r["strategy"]==strategy]
        by[strategy]={"baseline":calc(sub,"baseline"),"night_rule":calc(sub,"night_rule"),"signals":len(sub)}
    report={"research_only":True,"original_rules_unchanged":True,"source_backtest_generated_at":src.get("generated_at"),"generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),"period":[src.get("test_start"),src.get("test_end")],"entry":"1m bar open at 09:00 or 09:30; exact bar required","exit":"last available regular-session 1m bar close (typically 13:30 auction); check execution assumptions","night_rule":"TXF 1! afterhours first 60m bar open vs last 60m bar close; UP=>09:00, DOWN=>09:30, FLAT/MISSING=>skip","cost_model":"GROSS_NO_FEES_TAX_SLIPPAGE","warning":"Night close to next day 05:00 and 09:00/09:30 prices require execution and time availability validation. Signals historically generated with current membership approximation.","strategies":by,"missing_count":sum(r["baseline"] is None or r["night_rule"] is None for r in results),"errors":errors[:100],"trades":results}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"strategies":by,"missing_count":report["missing_count"],"errors":len(errors)},ensure_ascii=False))
if __name__=="__main__": main()
