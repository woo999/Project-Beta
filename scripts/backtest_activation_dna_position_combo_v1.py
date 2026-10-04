#!/usr/bin/env python3
import json
from pathlib import Path
from statistics import mean, median

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"docs"/"data"
HIST=DATA/"history"
GROUPS=DATA/"groups.json"
DAILY=DATA/"daily_rankings.json"
OUT=DATA/"activation_dna_position_combo_v1.json"

HOLDINGS=(1,3,5,10)
LOOKBACKS=(60,120)
MIN_GROUP_SAMPLES=(3,5)
MIN_DNA_SAMPLES=(3,5)

GROUP_FILTERS={
  "G_NONE": lambda s: True,
  "G_H5_POS": lambda s: s and s[5]["avg"]>0,
  "G_H3H5_POS": lambda s: s and s[3]["avg"]>0 and s[5]["avg"]>0,
  "G_H5_WR60": lambda s: s and s[5]["avg"]>0 and s[5]["wr"]>=60,
  "G_H3H5_WR60": lambda s: s and s[3]["avg"]>0 and s[5]["avg"]>0 and s[3]["wr"]>=60 and s[5]["wr"]>=60,
}
DNA_FILTERS={
  "D_NONE": lambda d: True,
  "D_POS60": lambda d: d and d["position_score"]>=60,
  "D_POS70": lambda d: d and d["position_score"]>=70,
  "D_TOP1_25": lambda d: d and d["top1_rate"]>=25,
  "D_TOP1_40": lambda d: d and d["top1_rate"]>=40,
  "D_POS60_TOP1_25": lambda d: d and d["position_score"]>=60 and d["top1_rate"]>=25,
}
CURRENT_POSITIONS=("R1","TOP2","TOP3","R2_3")

def read(p): return json.loads(p.read_text(encoding="utf-8"))
def write(p,o): p.write_text(json.dumps(o,ensure_ascii=False,separators=(",",":")),encoding="utf-8")

def load_hist(groups):
    hist={}
    for g in groups.get("groups",[]):
        for m in g.get("members",[]):
            c=m["code"]
            if c in hist: continue
            p=HIST/f"{c}.json"
            rows=read(p).get("rows",[]) if p.exists() else []
            rows=[r for r in rows if r.get("date") and isinstance(r.get("close"),(int,float)) and r["close"]>0]
            rows.sort(key=lambda r:r["date"])
            hist[c]=rows
    idx={c:{r["date"]:i for i,r in enumerate(rows)} for c,rows in hist.items()}
    dates=sorted({r["date"] for rows in hist.values() for r in rows})
    didx={d:i for i,d in enumerate(dates)}
    return hist,idx,dates,didx

def rowat(hist,idx,code,date):
    i=idx.get(code,{}).get(date)
    return hist[code][i] if i is not None else None

def member_codes(group): return [m["code"] for m in group.get("members",[])]

def events(groups,daily,hist,idx):
    gmap={g["name"]:g for g in groups.get("groups",[])}
    out=[]
    for day in daily.get("days",[]):
        d=day.get("date")
        if not d: continue
        for gr in day.get("groups",[]):
            name=gr.get("name")
            if name not in gmap: continue
            priced=gr.get("priced_members") or 0
            up_ratio=(gr.get("up_count") or 0)/priced if priced else 0
            active=((gr.get("rank") or 999)<=3 and isinstance(gr.get("avg_pct"),(int,float)) and gr["avg_pct"]>=2 and up_ratio>=0.60)
            if not active: continue
            ranked=[]
            for m in gmap[name].get("members",[]):
                r=rowat(hist,idx,m["code"],d)
                p=r.get("pct") if r else None
                if isinstance(p,(int,float)): ranked.append((m["code"],m["name"],p))
            ranked.sort(key=lambda x:x[2],reverse=True)
            out.append({"date":d,"group":name,"ranked":ranked,"group_rank":gr.get("rank"),"avg_pct":gr.get("avg_pct")})
    out.sort(key=lambda x:x["date"])
    return out

def group_follow(group,hist,idx,dates,didx,event_date,h):
    ei=didx.get(event_date)
    if ei is None or ei+h>=len(dates): return None
    td=dates[ei+h]
    vals=[]
    for c in member_codes(group):
        a=rowat(hist,idx,c,event_date); b=rowat(hist,idx,c,td)
        if a and b and a["close"]>0:
            vals.append((b["close"]/a["close"]-1)*100)
    return sum(vals)/len(vals) if vals else None

def prior_group_stats(group,eby,hist,idx,dates,didx,current_date,lookback,min_samples):
    ci=didx.get(current_date)
    vals={3:[],5:[]}
    for ev in eby.get(group["name"],[]):
        ei=didx.get(ev["date"])
        if ei is None or ei>=ci or ci-ei>lookback: continue
        for h in (3,5):
            if ei+h>=ci: continue
            v=group_follow(group,hist,idx,dates,didx,ev["date"],h)
            if isinstance(v,(int,float)): vals[h].append(v)
    out={}
    for h in (3,5):
        v=vals[h]
        out[h]={"n":len(v),"avg":sum(v)/len(v) if v else None,"wr":sum(x>0 for x in v)/len(v)*100 if v else None}
    if out[3]["n"]<min_samples or out[5]["n"]<min_samples: return None
    return out

def prior_dna(group,stock_code,eby,didx,current_date,lookback,min_samples):
    ci=didx.get(current_date)
    if ci is None: return None
    pos_scores=[]; top1=0; top3=0; obs=0
    for ev in eby.get(group["name"],[]):
        ei=didx.get(ev["date"])
        if ei is None or ei>=ci or ci-ei>lookback: continue
        ranked=ev["ranked"]; n=len(ranked)
        pos=next((i for i,x in enumerate(ranked,1) if x[0]==stock_code),None)
        if pos is None: continue
        obs+=1
        if pos==1: top1+=1
        if pos<=3: top3+=1
        score=100.0 if n<=1 else (n-pos)/(n-1)*100
        pos_scores.append(score)
    if obs<min_samples: return None
    return {
      "samples":obs,
      "position_score":sum(pos_scores)/len(pos_scores),
      "top1_rate":top1/obs*100,
      "top3_rate":top3/obs*100,
    }

def current_codes(ev,mode):
    r=ev["ranked"]
    if mode=="R1": return [r[0][0]] if r else []
    if mode=="TOP2": return [x[0] for x in r[:2]]
    if mode=="TOP3": return [x[0] for x in r[:3]]
    if mode=="R2_3": return [x[0] for x in r[1:3]]
    return []

def trade_ret(ev,codes,hist,idx,dates,didx,holding):
    ei=didx.get(ev["date"])
    if ei is None or ei+1>=len(dates) or ei+holding>=len(dates): return None
    entry_d=dates[ei+1]; exit_d=dates[ei+holding]
    vals=[]
    for c in codes:
        a=rowat(hist,idx,c,entry_d); b=rowat(hist,idx,c,exit_d)
        if not a or not b: continue
        ep=a.get("open")
        if isinstance(ep,(int,float)) and ep>0 and isinstance(b.get("close"),(int,float)):
            vals.append((b["close"]/ep-1)*100)
    return sum(vals)/len(vals) if vals else None

def metric(v):
    if not v:return {"n":0}
    return {"n":len(v),"wins":sum(x>0 for x in v),"win_rate":round(sum(x>0 for x in v)/len(v)*100,2),
            "avg":round(mean(v),4),"median":round(median(v),4)}

def main():
    groups=read(GROUPS); daily=read(DAILY)
    hist,idx,dates,didx=load_hist(groups)
    evs=events(groups,daily,hist,idx)
    gmap={g["name"]:g for g in groups.get("groups",[])}
    eby={}
    for e in evs: eby.setdefault(e["group"],[]).append(e)
    ev_dates=sorted({e["date"] for e in evs})
    split_date=ev_dates[max(0,int(len(ev_dates)*.70)-1)] if ev_dates else None

    store={}
    for ev in evs:
        group=gmap[ev["group"]]
        for lookback in LOOKBACKS:
            for min_g in MIN_GROUP_SAMPLES:
                gs=prior_group_stats(group,eby,hist,idx,dates,didx,ev["date"],lookback,min_g)
                for gf_name,gf in GROUP_FILTERS.items():
                    if gf_name!="G_NONE" and not gf(gs): continue
                    for min_d in MIN_DNA_SAMPLES:
                        for df_name,df in DNA_FILTERS.items():
                            for cp in CURRENT_POSITIONS:
                                raw_codes=current_codes(ev,cp)
                                if not raw_codes: continue
                                codes=[]
                                for c in raw_codes:
                                    dna=prior_dna(group,c,eby,didx,ev["date"],lookback,min_d)
                                    if df_name=="D_NONE" or df(dna):
                                        codes.append(c)
                                if not codes: continue
                                for h in HOLDINGS:
                                    ret=trade_ret(ev,codes,hist,idx,dates,didx,h)
                                    if ret is None: continue
                                    key=f"{lookback}|{min_g}|{gf_name}|{min_d}|{df_name}|{cp}|{h}"
                                    x=store.setdefault(key,{"lookback":lookback,"min_group_samples":min_g,"group_filter":gf_name,
                                        "min_dna_samples":min_d,"dna_filter":df_name,"current_position":cp,"holding":h,
                                        "all":[],"train":[],"test":[]})
                                    x["all"].append(ret)
                                    (x["train"] if ev["date"]<=split_date else x["test"]).append(ret)

    rows=[]
    for x in store.values():
        rec={k:x[k] for k in ("lookback","min_group_samples","group_filter","min_dna_samples","dna_filter","current_position","holding")}
        rec["all"]=metric(x["all"]); rec["train"]=metric(x["train"]); rec["test"]=metric(x["test"])
        if rec["all"]["n"]>=20 and rec["test"]["n"]>=8:
            rows.append(rec)

    # Exclude pure no-filter combos from combo shortlist.
    combos=[x for x in rows if x["group_filter"]!="G_NONE" and x["dna_filter"]!="D_NONE"]
    robust=[x for x in combos if x["train"]["n"]>=15 and x["test"]["n"]>=10
            and x["train"]["win_rate"]>=55 and x["test"]["win_rate"]>=55
            and x["train"]["avg"]>0 and x["test"]["avg"]>0]
    robust.sort(key=lambda x:(min(x["train"]["win_rate"],x["test"]["win_rate"]),
                              min(x["train"]["avg"],x["test"]["avg"]),x["all"]["n"]),reverse=True)

    # simpler baselines for comparison
    baselines=[x for x in rows if x["lookback"]==60 and x["min_group_samples"]==3 and x["min_dna_samples"]==3
               and x["group_filter"]=="G_NONE" and x["dna_filter"]=="D_NONE"]
    baselines.sort(key=lambda x:(x["current_position"],x["holding"]))

    write(OUT,{
      "version":"ACTIVATION_DNA_POSITION_COMBO_V1",
      "definition":{
        "activation":"族群排名前3 + 平均漲幅>=2% + 至少60%成員上漲",
        "group_followthrough":"只用當下以前且已成熟的3/5日歷史發動結果",
        "dna":"只用當下以前發動日的個股排名，計算領漲位置與第一率",
        "current_position":{"R1":"這次發動第1名","TOP2":"這次發動前2名等權","TOP3":"這次發動前3名等權","R2_3":"這次發動第2~3名等權"},
        "entry":"發動日收盤確認，下一交易日開盤",
        "holding":[1,3,5,10],
        "fees_tax_slippage":"未計入"
      },
      "activation_events":len(evs),"split_date":split_date,
      "baselines":baselines,
      "top_robust":robust[:120],
      "top_all":sorted(combos,key=lambda x:(x["test"]["win_rate"],x["test"]["avg"]),reverse=True)[:300]
    })

if __name__=="__main__": main()
