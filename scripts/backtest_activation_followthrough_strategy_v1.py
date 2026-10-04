#!/usr/bin/env python3
import json
from pathlib import Path
from statistics import mean, median

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"docs"/"data"
HIST=DATA/"history"
GROUPS=DATA/"groups.json"
DAILY=DATA/"daily_rankings.json"
OUT=DATA/"activation_followthrough_strategy_v1.json"

HOLDINGS=(1,3,5,10)
LOOKBACKS=(60,120)
PICK_MODES=("leader1","top3","group_equal","laggard")
FILTERS=("NONE","H3_POS","H5_POS","H3H5_POS","H5_WR60","H5_WR70","H3H5_WR60")
MIN_SAMPLES=(3,5)

def read(p): return json.loads(p.read_text(encoding="utf-8"))
def write(p,o): p.write_text(json.dumps(o,ensure_ascii=False,separators=(",",":")),encoding="utf-8")

def load_hist(groups):
    hist={}
    for g in groups.get("groups",[]):
        for m in g.get("members",[]):
            code=m["code"]
            if code in hist: continue
            p=HIST/f"{code}.json"
            rows=read(p).get("rows",[]) if p.exists() else []
            rows=[r for r in rows if r.get("date") and isinstance(r.get("close"),(int,float)) and r["close"]>0]
            rows.sort(key=lambda r:r["date"])
            hist[code]=rows
    idx={c:{r["date"]:i for i,r in enumerate(rows)} for c,rows in hist.items()}
    dates=sorted({r["date"] for rows in hist.values() for r in rows})
    didx={d:i for i,d in enumerate(dates)}
    return hist,idx,dates,didx

def rowat(hist,idx,code,date):
    i=idx.get(code,{}).get(date)
    return hist[code][i] if i is not None else None

def daily_return_pct(hist,idx,code,date):
    r=rowat(hist,idx,code,date)
    return r.get("pct") if r else None

def activation_events(groups,daily):
    out=[]
    group_map={g["name"]:g for g in groups.get("groups",[])}
    for day in daily.get("days",[]):
        d=day.get("date")
        if not d: continue
        for gr in day.get("groups",[]):
            name=gr.get("name")
            if name not in group_map: continue
            priced=gr.get("priced_members") or 0
            up_ratio=(gr.get("up_count") or 0)/priced if priced else 0
            active=((gr.get("rank") or 999)<=3 and isinstance(gr.get("avg_pct"),(int,float)) and gr["avg_pct"]>=2 and up_ratio>=0.60)
            if active:
                out.append({
                    "date":d,"group":name,"rank":gr.get("rank"),"avg_pct":gr.get("avg_pct"),
                    "up_ratio":up_ratio,"leaders":gr.get("leaders",[])[:3]
                })
    out.sort(key=lambda x:x["date"])
    return out

def member_codes(group):
    return [m["code"] for m in group.get("members",[])]

def close_to_close_group_return(group,hist,idx,dates,didx,event_date,h):
    ei=didx.get(event_date)
    if ei is None or ei+h>=len(dates): return None,None
    td=dates[ei+h]
    vals=[]
    for code in member_codes(group):
        a=rowat(hist,idx,code,event_date); b=rowat(hist,idx,code,td)
        if a and b and a["close"]>0:
            vals.append((b["close"]/a["close"]-1)*100)
    if not vals: return None,td
    return sum(vals)/len(vals),td

def prior_stats(group,events_by_group,hist,idx,dates,didx,current_date,lookback,min_samples):
    ci=didx.get(current_date)
    if ci is None: return None
    vals={3:[],5:[]}
    for ev in events_by_group.get(group["name"],[]):
        ed=ev["date"]; ei=didx.get(ed)
        if ei is None or ei>=ci: continue
        if ci-ei>lookback: continue
        for h in (3,5):
            # Result must already be fully observable BEFORE current signal day.
            if ei+h>=ci: 
                continue
            ret,_=close_to_close_group_return(group,hist,idx,dates,didx,ed,h)
            if isinstance(ret,(int,float)): vals[h].append(ret)
    out={}
    for h in (3,5):
        v=vals[h]
        out[h]={
            "n":len(v),
            "avg":sum(v)/len(v) if v else None,
            "wr":sum(x>0 for x in v)/len(v)*100 if v else None
        }
    if out[3]["n"]<min_samples or out[5]["n"]<min_samples:
        return None
    return out

def filter_ok(stats,kind):
    if kind=="NONE": return True
    if not stats: return False
    s3,s5=stats[3],stats[5]
    if kind=="H3_POS": return s3["avg"]>0
    if kind=="H5_POS": return s5["avg"]>0
    if kind=="H3H5_POS": return s3["avg"]>0 and s5["avg"]>0
    if kind=="H5_WR60": return s5["wr"]>=60 and s5["avg"]>0
    if kind=="H5_WR70": return s5["wr"]>=70 and s5["avg"]>0
    if kind=="H3H5_WR60": return s3["wr"]>=60 and s5["wr"]>=60 and s3["avg"]>0 and s5["avg"]>0
    return False

def selected_codes(group,event,hist,idx,mode):
    codes=member_codes(group)
    ranked=[]
    for code in codes:
        p=daily_return_pct(hist,idx,code,event["date"])
        if isinstance(p,(int,float)): ranked.append((code,p))
    ranked.sort(key=lambda x:x[1],reverse=True)
    if not ranked: return []
    if mode=="leader1": return [ranked[0][0]]
    if mode=="top3": return [x[0] for x in ranked[:3]]
    if mode=="group_equal": return [x[0] for x in ranked]
    if mode=="laggard": return [ranked[-1][0]]
    return []

def trade_return(group,event,hist,idx,dates,didx,mode,holding):
    ei=didx.get(event["date"])
    if ei is None or ei+1>=len(dates): return None
    entry_date=dates[ei+1]
    exit_pos=ei+holding
    if exit_pos>=len(dates): return None
    exit_date=dates[exit_pos]
    vals=[]
    for code in selected_codes(group,event,hist,idx,mode):
        er=rowat(hist,idx,code,entry_date); xr=rowat(hist,idx,code,exit_date)
        if not er or not xr: continue
        ep=er.get("open"); xp=xr.get("close")
        if isinstance(ep,(int,float)) and ep>0 and isinstance(xp,(int,float)):
            vals.append((xp/ep-1)*100)
    if not vals: return None
    return sum(vals)/len(vals)

def metric(vals):
    if not vals: return {"n":0}
    v=list(vals)
    return {
        "n":len(v),
        "wins":sum(x>0 for x in v),
        "win_rate":round(sum(x>0 for x in v)/len(v)*100,2),
        "avg":round(mean(v),4),
        "median":round(median(v),4),
    }

def main():
    groups=read(GROUPS); daily=read(DAILY)
    hist,idx,dates,didx=load_hist(groups)
    events=activation_events(groups,daily)
    gmap={g["name"]:g for g in groups.get("groups",[])}
    eby={}
    for e in events: eby.setdefault(e["group"],[]).append(e)

    # Date split rather than random split.
    usable_dates=sorted({e["date"] for e in events})
    split_date=usable_dates[max(0,int(len(usable_dates)*0.70)-1)] if usable_dates else None

    rows={}
    for ev in events:
        group=gmap[ev["group"]]
        for lookback in LOOKBACKS:
            for mins in MIN_SAMPLES:
                stats=prior_stats(group,eby,hist,idx,dates,didx,ev["date"],lookback,mins)
                for flt in FILTERS:
                    # NONE is baseline and must not require stats.
                    if flt!="NONE" and not filter_ok(stats,flt): continue
                    for pm in PICK_MODES:
                        for hold in HOLDINGS:
                            ret=trade_return(group,ev,hist,idx,dates,didx,pm,hold)
                            if ret is None: continue
                            key=f"{lookback}|{mins}|{flt}|{pm}|{hold}"
                            x=rows.setdefault(key,{
                                "lookback":lookback,"min_samples":mins,"filter":flt,"pick":pm,"holding":hold,
                                "all":[],"train":[],"test":[]
                            })
                            x["all"].append(ret)
                            (x["train"] if ev["date"]<=split_date else x["test"]).append(ret)

    out=[]
    for x in rows.values():
        # de-duplicate NONE across min-sample variants logically by retaining both only for raw output; shortlist handles.
        rec={k:x[k] for k in ("lookback","min_samples","filter","pick","holding")}
        rec["all"]=metric(x["all"]); rec["train"]=metric(x["train"]); rec["test"]=metric(x["test"])
        if rec["all"]["n"]>=15 and rec["test"]["n"]>=5:
            out.append(rec)

    # Robust: enough observations, positive avg both periods, train/test WR >=55.
    robust=[x for x in out if x["test"]["n"]>=8 and x["train"]["n"]>=12
            and x["test"].get("win_rate",0)>=55 and x["train"].get("win_rate",0)>=55
            and x["test"].get("avg",-999)>0 and x["train"].get("avg",-999)>0]
    robust.sort(key=lambda x:(
        min(x["train"]["win_rate"],x["test"]["win_rate"]),
        min(x["train"]["avg"],x["test"]["avg"]),
        x["all"]["n"]
    ),reverse=True)

    # Separate baseline for direct comparison: no filter, next open.
    baseline=[x for x in out if x["filter"]=="NONE" and x["lookback"]==60 and x["min_samples"]==3]
    baseline.sort(key=lambda x:(x["pick"],x["holding"]))

    write(OUT,{
        "version":"ACTIVATION_FOLLOWTHROUGH_STRATEGY_V1",
        "definition":{
            "activation":"族群當日排名前3 + 平均漲幅>=2% + 至少60%成員上漲",
            "historical_filter":"每次發動只能使用該日以前、且1/3/5日結果已成熟的舊發動紀錄",
            "entry":"發動日收盤確認，下一交易日開盤進",
            "picks":{"leader1":"發動日族群第1名","top3":"發動日族群前3等權","group_equal":"全族群等權","laggard":"發動日族群最弱股"},
            "holding":"進場後固定持有1/3/5/10個交易日",
            "fees_tax_slippage":"未計入",
        },
        "data_start":dates[0] if dates else None,
        "data_end":dates[-1] if dates else None,
        "activation_events":len(events),
        "split_date":split_date,
        "baseline":baseline,
        "top_robust":robust[:100],
        "all_results":sorted(out,key=lambda x:(x["test"].get("win_rate",0),x["test"].get("avg",0)),reverse=True)[:300],
    })

if __name__=="__main__": main()
