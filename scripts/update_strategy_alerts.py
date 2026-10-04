#!/usr/bin/env python3
import json
from pathlib import Path
from statistics import mean

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"docs"/"data"
HISTORY=DATA/"history"
GROUPS_PATH=DATA/"groups.json"
DAILY_PATH=DATA/"daily_rankings.json"
OUT=DATA/"strategy_alerts.json"

GRADE_ORDER={"SSS":0,"SS":1,"A":2,"B":3,"C":4}

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def write(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":")),encoding="utf-8")

def load_histories(groups):
    hist={}
    for g in groups.get("groups",[]):
        for m in g.get("members",[]):
            code=m["code"]
            if code in hist:
                continue
            p=HISTORY/f"{code}.json"
            if not p.exists():
                hist[code]=[]
                continue
            rows=read(p).get("rows",[])
            rows=[r for r in rows if r.get("date") and isinstance(r.get("close"),(int,float)) and r["close"]>0]
            rows.sort(key=lambda r:r["date"])
            hist[code]=rows
    idx={c:{r["date"]:i for i,r in enumerate(rows)} for c,rows in hist.items()}
    dates=sorted({r["date"] for rows in hist.values() for r in rows})
    didx={d:i for i,d in enumerate(dates)}
    return hist,idx,dates,didx

def rowat(hist,idx,code,date):
    i=idx.get(code,{}).get(date)
    return hist.get(code,[])[i] if i is not None else None

def sret(hist,idx,code,date,n):
    i=idx.get(code,{}).get(date)
    rows=hist.get(code,[])
    if i is None or i<n:
        return None
    a=rows[i-n].get("close"); b=rows[i].get("close")
    if not isinstance(a,(int,float)) or not a:
        return None
    return (b/a-1)*100

def group_rank_map(groups,hist,idx,date,n):
    arr=[]
    for g in groups.get("groups",[]):
        vals=[]
        for m in g.get("members",[]):
            v=sret(hist,idx,m["code"],date,n)
            if isinstance(v,(int,float)):
                vals.append(v)
        if vals:
            arr.append((g["name"],sum(vals)/len(vals)))
    arr.sort(key=lambda x:x[1],reverse=True)
    return {name:{"rank":i+1,"ret":ret} for i,(name,ret) in enumerate(arr)}

def state_map(groups,hist,idx,date):
    maps={p:group_rank_map(groups,hist,idx,date,p) for p in (60,20,10,5)}
    out={}
    for g in groups.get("groups",[]):
        name=g["name"]
        d={p:maps[p].get(name) for p in maps}
        if not all(d[p] for p in d):
            out[name]={"label":"資料不足"}
            continue
        r60,r20,r10,r5=[d[p]["rank"] for p in (60,20,10,5)]
        ret60,ret20,ret10,ret5=[d[p]["ret"] for p in (60,20,10,5)]
        background=r60<=8 and ret60>0
        core=r20<=5 and ret20>0
        confirm=r10<=6 and ret10>0
        near_ok=r5<=8
        improving=r20<=10 and r10<r20 and r5<=r10 and ret20>0
        repairing=r20>=11 and r10<r20 and r5<=r10 and ret10>0 and ret5>0
        lost=(background or r20<=8) and ((r5-r20)>=6 or (r5>=12 and ret5<0))
        weakening=background and r20>=10 and r10>=9 and r5>=9 and ret20<=0
        weak=(not background) and r20>=12 and r10>=10 and r5>=10 and ret20<=0
        label="觀察"
        if background and core and confirm and near_ok:
            label="結構完整"
        elif (not background) and core and confirm and near_ok:
            label="新轉強"
        elif improving:
            label="轉強中"
        elif repairing:
            label="修復中"
        elif lost:
            label="失速"
        elif weakening:
            label="轉弱"
        elif weak:
            label="弱勢"
        elif background and r20<=8:
            label="高檔整理"
        out[name]={"label":label,"r60":r60,"r20":r20,"r10":r10,"r5":r5,
                   "ret60":ret60,"ret20":ret20,"ret10":ret10,"ret5":ret5}
    return out

def activation_events(groups,daily,hist,idx):
    gnames={g["name"] for g in groups.get("groups",[])}
    out=[]
    for day in daily.get("days",[]):
        date=day.get("date")
        if not date:
            continue
        for gr in day.get("groups",[]):
            if gr.get("name") not in gnames:
                continue
            priced=gr.get("priced_members") or 0
            up_ratio=(gr.get("up_count") or 0)/priced if priced else 0
            active=((gr.get("rank") or 999)<=3 and isinstance(gr.get("avg_pct"),(int,float))
                    and gr["avg_pct"]>=2 and up_ratio>=0.60)
            if not active:
                continue
            ranked=[]
            group=next(g for g in groups["groups"] if g["name"]==gr["name"])
            for m in group.get("members",[]):
                r=rowat(hist,idx,m["code"],date)
                p=r.get("pct") if r else None
                if isinstance(p,(int,float)):
                    ranked.append({"code":m["code"],"name":m["name"],"pct":p})
            ranked.sort(key=lambda x:x["pct"],reverse=True)
            out.append({"date":date,"group":gr["name"],"ranked":ranked})
    out.sort(key=lambda x:x["date"])
    return out

def group_follow_return(group,hist,idx,dates,didx,event_date,h):
    ei=didx.get(event_date)
    if ei is None or ei+h>=len(dates):
        return None
    target=dates[ei+h]
    vals=[]
    for m in group.get("members",[]):
        a=rowat(hist,idx,m["code"],event_date)
        b=rowat(hist,idx,m["code"],target)
        if a and b and a["close"]>0:
            vals.append((b["close"]/a["close"]-1)*100)
    return sum(vals)/len(vals) if vals else None

def prior_group_h5(group,eby,hist,idx,dates,didx,current_date,lookback=120):
    ci=didx.get(current_date)
    vals=[]
    if ci is None:
        return None
    for ev in eby.get(group["name"],[]):
        ei=didx.get(ev["date"])
        if ei is None or ei>=ci or ci-ei>lookback:
            continue
        if ei+5>=ci:
            continue
        v=group_follow_return(group,hist,idx,dates,didx,ev["date"],5)
        if isinstance(v,(int,float)):
            vals.append(v)
    if len(vals)<5:
        return None
    return {"n":len(vals),"avg":sum(vals)/len(vals),"win_rate":sum(v>0 for v in vals)/len(vals)*100}

def prior_stock_dna(group_name,code,eby,didx,current_date,lookback=120):
    ci=didx.get(current_date)
    if ci is None:
        return None
    obs=top1=0
    for ev in eby.get(group_name,[]):
        ei=didx.get(ev["date"])
        if ei is None or ei>=ci or ci-ei>lookback:
            continue
        pos=next((i for i,x in enumerate(ev["ranked"],1) if x["code"]==code),None)
        if pos is None:
            continue
        obs+=1
        if pos==1:
            top1+=1
    if obs<5:
        return None
    return {"samples":obs,"top1_rate":top1/obs*100}

def strongest_member(group,hist,idx,date,n=60,reverse=True):
    rows=[]
    for m in group.get("members",[]):
        v=sret(hist,idx,m["code"],date,n)
        if isinstance(v,(int,float)):
            rows.append((v,m))
    if not rows:
        return None
    rows.sort(key=lambda x:x[0],reverse=reverse)
    return rows[0][1]

def weakest_day_member(group,hist,idx,date):
    rows=[]
    for m in group.get("members",[]):
        r=rowat(hist,idx,m["code"],date)
        p=r.get("pct") if r else None
        if isinstance(p,(int,float)):
            rows.append((p,m))
    if not rows:
        return None
    rows.sort(key=lambda x:x[0])
    return rows[0][1]

def add(alerts,grade,strategy,side,group,stock,holding,reason,status="明日開盤觀察"):
    alerts.append({
        "grade":grade,"strategy":strategy,"side":side,
        "group":group,"code":stock["code"],"name":stock["name"],
        "holding_days":holding,"status":status,"reason":reason
    })

def main():
    groups=read(GROUPS_PATH)
    daily=read(DAILY_PATH)
    hist,idx,dates,didx=load_histories(groups)
    if not daily.get("days"):
        write(OUT,{"latest_date":None,"alerts":[]})
        return
    latest=daily["days"][-1]["date"]
    if latest not in didx:
        write(OUT,{"latest_date":latest,"alerts":[],"note":"latest daily date missing from history"})
        return
    prev=dates[didx[latest]-1] if didx[latest]>0 else None
    cur_states=state_map(groups,hist,idx,latest)
    prev_states=state_map(groups,hist,idx,prev) if prev else {}
    gmap={g["name"]:g for g in groups.get("groups",[])}
    latest_groups={x["name"]:x for x in daily["days"][-1].get("groups",[])}
    evs=activation_events(groups,daily,hist,idx)
    eby={}
    for ev in evs:
        eby.setdefault(ev["group"],[]).append(ev)
    current_events={(e["group"],e["date"]):e for e in evs}

    alerts=[]

    # SS: 發動續強・真領漲
    for g in groups.get("groups",[]):
        ev=current_events.get((g["name"],latest))
        if not ev:
            continue
        gf=prior_group_h5(g,eby,hist,idx,dates,didx,latest,120)
        if not gf or gf["avg"]<=0 or gf["win_rate"]<60:
            continue
        for x in ev["ranked"][:2]:
            dna=prior_stock_dna(g["name"],x["code"],eby,didx,latest,120)
            if dna and dna["top1_rate"]>=40:
                add(alerts,"SS","發動續強・真領漲","LONG",g["name"],x,10,
                    f"120日發動後5日勝率 {gf['win_rate']:.0f}%（n={gf['n']}）｜歷史第一率 {dna['top1_rate']:.0f}%（n={dna['samples']}）｜本次發動前2")

    # SS: 新轉強・當日落後補漲
    for g in groups.get("groups",[]):
        now=cur_states.get(g["name"],{})
        old=prev_states.get(g["name"],{})
        if now.get("label")=="新轉強" and old.get("label")!="新轉強":
            stock=weakest_day_member(g,hist,idx,latest)
            if stock:
                add(alerts,"SS","新轉強・當日落後補漲","LONG",g["name"],stock,5,
                    "族群今日首次進入新轉強｜選當日族群內漲幅最弱股")

    # A: 中期弱、短期突然強・落後補漲
    for g in groups.get("groups",[]):
        st=cur_states.get(g["name"],{})
        if isinstance(st.get("r20"),int) and isinstance(st.get("r5"),int) and st["r20"]>=12 and st["r5"]<=5:
            stock=strongest_member(g,hist,idx,latest,20,reverse=False)
            if stock:
                add(alerts,"A","中期弱短期強・落後補漲","LONG",g["name"],stock,10,
                    f"20日排名 #{st['r20']}｜5日排名 #{st['r5']}｜選20日最弱股")

    # A: 高檔整理・長期強股
    for g in groups.get("groups",[]):
        now=cur_states.get(g["name"],{})
        old=prev_states.get(g["name"],{})
        if now.get("label")=="高檔整理" and old.get("label")!="高檔整理":
            stock=strongest_member(g,hist,idx,latest,60,reverse=True)
            if stock:
                add(alerts,"A","高檔整理・長期強股","LONG",g["name"],stock,20,
                    "族群今日進入高檔整理｜選60日最強股")

    # A: 修復中・弱股隔日短空
    for g in groups.get("groups",[]):
        now=cur_states.get(g["name"],{})
        old=prev_states.get(g["name"],{})
        if now.get("label")=="修復中" and old.get("label")!="修復中":
            stock=strongest_member(g,hist,idx,latest,20,reverse=False)
            if stock:
                add(alerts,"A","修復中・弱股隔日當沖空","SHORT",g["name"],stock,1,
                    "族群今日進入修復中｜選20日最弱股｜下一交易日開盤放空、同日收盤回補（當沖）")

    # de-duplicate same strategy/stock
    uniq={}
    for a in alerts:
        uniq[(a["strategy"],a["code"])]=a
    alerts=list(uniq.values())
    alerts.sort(key=lambda a:(GRADE_ORDER.get(a["grade"],9),a["strategy"],a["group"],a["code"]))

    write(OUT,{
        "version":"WOO_ALERT_V1",
        "latest_date":latest,
        "generated_from":"收盤資料",
        "alerts":alerts,
        "strategy_count":5,
        "note":"策略訊號為歷史統計規則掃描，不是保證獲利或個人化投資建議。"
    })

if __name__=="__main__":
    main()
