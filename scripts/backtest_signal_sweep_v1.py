#!/usr/bin/env python3
import json
from pathlib import Path
from statistics import mean, median

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"docs"/"data"
HIST=DATA/"history"
GROUPS=DATA/"groups.json"
OUT=DATA/"signal_sweep_v1.json"

HORIZONS=(1,3,5,10,20)
STATE_NAMES=("結構完整","新轉強","轉強中","修復中","高檔整理","觀察","失速","轉弱","弱勢")

def read(p): return json.loads(p.read_text(encoding="utf-8"))
def write(p,o): p.write_text(json.dumps(o,ensure_ascii=False,separators=(",",":")),encoding="utf-8")

def load(groups):
    hist={}
    for g in groups["groups"]:
        for m in g["members"]:
            if m["code"] in hist: continue
            p=HIST/f'{m["code"]}.json'
            rows=read(p).get("rows",[]) if p.exists() else []
            rows=[r for r in rows if r.get("date") and isinstance(r.get("close"),(int,float)) and r["close"]>0]
            rows.sort(key=lambda r:r["date"])
            hist[m["code"]]=rows
    idx={c:{r["date"]:i for i,r in enumerate(rows)} for c,rows in hist.items()}
    dates=sorted({r["date"] for rows in hist.values() for r in rows})
    return hist,idx,dates

def sret(hist,idx,code,date,n):
    i=idx.get(code,{}).get(date)
    rows=hist.get(code,[])
    if i is None or i<n: return None
    a=rows[i-n]["close"]; b=rows[i]["close"]
    return (b/a-1)*100 if a else None

def rowat(hist,idx,code,date):
    i=idx.get(code,{}).get(date)
    return hist[code][i] if i is not None else None

def daily_group_pct(groups,hist,idx,date):
    arr=[]
    for g in groups["groups"]:
        vals=[]
        for m in g["members"]:
            r=rowat(hist,idx,m["code"],date)
            p=r.get("pct") if r else None
            if isinstance(p,(int,float)): vals.append(p)
        if vals: arr.append((g["name"],sum(vals)/len(vals)))
    arr.sort(key=lambda x:x[1],reverse=True)
    return {name:{"rank":i+1,"avg_pct":pct} for i,(name,pct) in enumerate(arr)}

def rankmap(groups,hist,idx,date,n):
    arr=[]
    for g in groups["groups"]:
        vals=[]
        for m in g["members"]:
            v=sret(hist,idx,m["code"],date,n)
            if isinstance(v,(int,float)): vals.append(v)
        if vals: arr.append((g["name"],sum(vals)/len(vals)))
    arr.sort(key=lambda x:x[1],reverse=True)
    return {name:{"rank":i+1,"ret":ret} for i,(name,ret) in enumerate(arr)}

def states(groups,maps):
    out={}
    for g in groups["groups"]:
        name=g["name"]; d={p:maps[p].get(name) for p in (60,20,10,5)}
        if not all(d[p] for p in d):
            out[name]={"label":"資料不足"}; continue
        r60,r20,r10,r5=[d[p]["rank"] for p in (60,20,10,5)]
        a,b,c,e=[d[p]["ret"] for p in (60,20,10,5)]
        background=r60<=8 and a>0
        core=r20<=5 and b>0
        confirm=r10<=6 and c>0
        near=r5<=8
        improving=r20<=10 and r10<r20 and r5<=r10 and b>0
        repairing=r20>=11 and r10<r20 and r5<=r10 and c>0 and e>0
        lost=(background or r20<=8) and ((r5-r20)>=6 or (r5>=12 and e<0))
        weakening=background and r20>=10 and r10>=9 and r5>=9 and b<=0
        weak=(not background) and r20>=12 and r10>=10 and r5>=10 and b<=0
        label="觀察"
        if background and core and confirm and near: label="結構完整"
        elif (not background) and core and confirm and near: label="新轉強"
        elif improving: label="轉強中"
        elif repairing: label="修復中"
        elif lost: label="失速"
        elif weakening: label="轉弱"
        elif weak: label="弱勢"
        elif background and r20<=8: label="高檔整理"
        out[name]={"label":label,"r60":r60,"r20":r20,"r10":r10,"r5":r5,
                   "ret60":a,"ret20":b,"ret10":c,"ret5":e}
    return out

def pick(group,hist,idx,date,mode):
    rows=[]
    for m in group["members"]:
        r=rowat(hist,idx,m["code"],date)
        if not r: continue
        r20=sret(hist,idx,m["code"],date,20)
        r60=sret(hist,idx,m["code"],date,60)
        if not isinstance(r20,(int,float)) or not isinstance(r60,(int,float)): continue
        rows.append({"code":m["code"],"name":m["name"],"r20":r20,"r60":r60,"pct":r.get("pct")})
    if not rows: return None
    if mode=="strong20": rows.sort(key=lambda x:x["r20"],reverse=True)
    elif mode=="weak20": rows.sort(key=lambda x:x["r20"])
    elif mode=="strong60": rows.sort(key=lambda x:x["r60"],reverse=True)
    elif mode=="weak60": rows.sort(key=lambda x:x["r60"])
    elif mode=="low_day": rows.sort(key=lambda x:(x["pct"] if isinstance(x["pct"],(int,float)) else 999))
    elif mode=="high_day": rows.sort(key=lambda x:(x["pct"] if isinstance(x["pct"],(int,float)) else -999),reverse=True)
    return rows[0]

def fwd(hist,idx,code,date,h):
    i=idx.get(code,{}).get(date); rows=hist.get(code,[])
    if i is None or i+1+h-1>=len(rows): return None
    e=rows[i+1]
    ex=rows[i+h]
    if not isinstance(e.get("open"),(int,float)): return None
    ep=e["open"]; xp=ex["close"]
    if not ep: return None
    return (xp/ep-1)*100

def metric(vals):
    if not vals: return {"n":0}
    wins=sum(v>0 for v in vals)
    return {"n":len(vals),"win_rate":round(wins/len(vals)*100,2),"avg":round(mean(vals),4),"median":round(median(vals),4)}

def main():
    groups=read(GROUPS); hist,idx,dates=load(groups)
    state_by_date={}; daily_by_date={}
    for di,d in enumerate(dates):
        if di<60: continue
        maps={p:rankmap(groups,hist,idx,d,p) for p in (60,20,10,5)}
        state_by_date[d]=states(groups,maps)
        daily_by_date[d]=daily_group_pct(groups,hist,idx,d)

    events=[]
    for di in range(61,len(dates)):
        d=dates[di]; prev=dates[di-1]
        cur=state_by_date.get(d); prv=state_by_date.get(prev); daily=daily_by_date.get(d,{})
        if not cur or not prv: continue
        for g in groups["groups"]:
            name=g["name"]; st=cur.get(name,{}); ps=prv.get(name,{})
            dg=daily.get(name,{})
            base={
                "date":d,"group":name,"state":st.get("label"),"prev_state":ps.get("label"),
                "daily_rank":dg.get("rank"),"daily_pct":dg.get("avg_pct"),
                **{k:st.get(k) for k in ("r60","r20","r10","r5","ret60","ret20","ret10","ret5")}
            }
            # Event families
            tags=set()
            if st.get("label")!=ps.get("label"): tags.add("STATE_ENTER_"+str(st.get("label")))
            tags.add("STATE_"+str(st.get("label")))
            if dg.get("rank") is not None and dg["rank"]<=3 and dg.get("avg_pct",0)>=2: tags.add("TODAY_TOP3_UP2")
            if dg.get("rank") is not None and dg["rank"]>=14 and dg.get("avg_pct",0)<=-2: tags.add("TODAY_BOTTOM3_DN2")
            if st.get("r60") is not None and st["r60"]<=5 and st.get("r5") is not None and st["r5"]>=12: tags.add("LONG_STRONG_SHORT_WEAK")
            if st.get("r60") is not None and st["r60"]>=12 and st.get("r5") is not None and st["r5"]<=5: tags.add("LONG_WEAK_SHORT_STRONG")
            if st.get("r20") is not None and st["r20"]<=5 and st.get("r5") is not None and st["r5"]>=12: tags.add("MID_STRONG_NEAR_WEAK")
            if st.get("r20") is not None and st["r20"]>=12 and st.get("r5") is not None and st["r5"]<=5: tags.add("MID_WEAK_NEAR_STRONG")
            for tag in tags:
                events.append((tag,base,g))

    # split by date 70/30
    event_dates=sorted({e[1]["date"] for e in events})
    split_date=event_dates[max(0,int(len(event_dates)*0.70)-1)] if event_dates else None

    results={}
    pick_modes=("strong20","weak20","strong60","weak60","low_day","high_day")
    for tag,base,g in events:
        for pm in pick_modes:
            p=pick(g,hist,idx,base["date"],pm)
            if not p: continue
            for side in ("LONG","SHORT"):
                for h in HORIZONS:
                    rr=fwd(hist,idx,p["code"],base["date"],h)
                    if rr is None: continue
                    val=rr if side=="LONG" else -rr
                    key=f"{tag}|{pm}|{side}|{h}"
                    rec=results.setdefault(key,{"tag":tag,"pick":pm,"side":side,"horizon":h,"all":[],"train":[],"test":[]})
                    rec["all"].append(val)
                    (rec["train"] if base["date"]<=split_date else rec["test"]).append(val)

    out=[]
    for rec in results.values():
        a,t,u=metric(rec["all"]),metric(rec["train"]),metric(rec["test"])
        if a.get("n",0)<20 or u.get("n",0)<8: continue
        out.append({**{k:rec[k] for k in ("tag","pick","side","horizon")},"all":a,"train":t,"test":u})
    out.sort(key=lambda x:((x["test"].get("win_rate") or -999),(x["test"].get("avg") or -999),x["test"].get("n",0)),reverse=True)

    # robust shortlist: test >=60%, train >=55%, both avg >0, test n>=10
    robust=[x for x in out if x["test"].get("n",0)>=10 and x["test"].get("win_rate",0)>=60 and x["train"].get("win_rate",0)>=55 and x["test"].get("avg",-999)>0 and x["train"].get("avg",-999)>0]
    robust=robust[:100]

    write(OUT,{
        "version":"SIGNAL_SWEEP_V1",
        "data_start":dates[0] if dates else None,
        "data_end":dates[-1] if dates else None,
        "split_date":split_date,
        "method":{
            "anti_hindsight":"每日只用當日以前資料定義訊號；隔日開盤進；固定持有h個交易日。",
            "horizons":list(HORIZONS),
            "pick_modes":{
                "strong20":"族群內20日最強","weak20":"族群內20日最弱",
                "strong60":"族群內60日最強","weak60":"族群內60日最弱",
                "low_day":"族群內訊號日最弱","high_day":"族群內訊號日最強"
            },
            "sides":["LONG","SHORT"],
            "fees_tax_slippage":"未計入"
        },
        "top_robust":robust,
        "top_all":out[:200]
    })

if __name__=="__main__": main()
