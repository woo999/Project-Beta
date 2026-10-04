#!/usr/bin/env python3
import json
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"
HISTORY = DATA / "history"
BASE = DATA / "backtest_monthly_v1.json"
OUT = DATA / "entry_sweep_v1.json"

def read(p):
    return json.loads(p.read_text(encoding="utf-8"))

def write(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

def load_rows(code):
    p = HISTORY / f"{code}.json"
    if not p.exists():
        return []
    rows = read(p).get("rows", [])
    rows = [r for r in rows if r.get("date") and isinstance(r.get("close"), (int,float)) and r.get("close") > 0]
    rows.sort(key=lambda r:r["date"])
    return rows

def fill_limit(row, price):
    opn, low = row.get("open"), row.get("low")
    if not isinstance(opn,(int,float)) or not isinstance(low,(int,float)):
        return None
    if opn <= price:
        return opn
    if low <= price:
        return price
    return None

def fill_stop(row, price):
    opn, high = row.get("open"), row.get("high")
    if not isinstance(opn,(int,float)) or not isinstance(high,(int,float)):
        return None
    if opn >= price:
        return opn
    if high >= price:
        return price
    return None

def entry_candidate(method, rows, si, signal_row):
    sc = signal_row.get("close")
    sl = signal_row.get("low")
    sh = signal_row.get("high")
    if not isinstance(sc,(int,float)):
        return None

    # direct / time-delayed
    if method == "NEXT_OPEN":
        i=si+1
        return (i, rows[i]["open"]) if i < len(rows) and isinstance(rows[i].get("open"),(int,float)) else None
    if method == "WAIT_1_OPEN":
        i=si+2
        return (i, rows[i]["open"]) if i < len(rows) and isinstance(rows[i].get("open"),(int,float)) else None
    if method == "WAIT_2_OPEN":
        i=si+3
        return (i, rows[i]["open"]) if i < len(rows) and isinstance(rows[i].get("open"),(int,float)) else None

    # limit pullbacks from signal close
    if method.startswith("LIMIT_"):
        if method == "LIMIT_SIGNAL_CLOSE_3D":
            price, window = sc, 3
        elif method == "LIMIT_MINUS2_5D":
            price, window = sc*0.98, 5
        elif method == "LIMIT_MINUS3_5D":
            price, window = sc*0.97, 5
        elif method == "LIMIT_MINUS5_5D":
            price, window = sc*0.95, 5
        elif method == "LIMIT_SIGNAL_LOW_5D":
            if not isinstance(sl,(int,float)): return None
            price, window = sl, 5
        else:
            return None
        for i in range(si+1, min(len(rows), si+1+window)):
            fill=fill_limit(rows[i], price)
            if fill is not None:
                return i, fill
        return None

    # first red day, buy following open
    if method == "FIRST_RED_NEXT_OPEN_5D":
        for i in range(si+1, min(len(rows)-1, si+6)):
            pct=rows[i].get("pct")
            if isinstance(pct,(int,float)) and pct < 0:
                j=i+1
                opn=rows[j].get("open")
                if isinstance(opn,(int,float)):
                    return j, opn
        return None

    # first close at/below signal close, buy next open
    if method == "CLOSE_RETEST_NEXT_OPEN_5D":
        for i in range(si+1, min(len(rows)-1, si+6)):
            close=rows[i].get("close")
            if isinstance(close,(int,float)) and close <= sc:
                j=i+1
                opn=rows[j].get("open")
                if isinstance(opn,(int,float)):
                    return j, opn
        return None

    # pullback first, then first up-close, enter next open
    if method in ("PULLBACK2_UPTURN_7D","PULLBACK3_UPTURN_7D"):
        threshold=sc*(0.98 if method=="PULLBACK2_UPTURN_7D" else 0.97)
        pulled=False
        for i in range(si+1, min(len(rows)-1, si+8)):
            low=rows[i].get("low")
            if isinstance(low,(int,float)) and low <= threshold:
                pulled=True
            if pulled and i>si+1:
                c=rows[i].get("close"); pc=rows[i-1].get("close")
                if isinstance(c,(int,float)) and isinstance(pc,(int,float)) and c>pc:
                    j=i+1
                    opn=rows[j].get("open")
                    if isinstance(opn,(int,float)):
                        return j, opn
        return None

    # breakout confirmation
    if method == "BREAK_SIGNAL_HIGH_5D":
        if not isinstance(sh,(int,float)): return None
        for i in range(si+1, min(len(rows), si+6)):
            fill=fill_stop(rows[i], sh)
            if fill is not None:
                return i, fill
        return None

    if method == "CLOSE_ABOVE_SIGNAL_HIGH_NEXT_OPEN_5D":
        if not isinstance(sh,(int,float)): return None
        for i in range(si+1, min(len(rows)-1, si+6)):
            c=rows[i].get("close")
            if isinstance(c,(int,float)) and c > sh:
                j=i+1
                opn=rows[j].get("open")
                if isinstance(opn,(int,float)):
                    return j, opn
        return None

    return None

def evaluate(rows, entry_i, entry_price):
    exit_i=entry_i+19
    if exit_i >= len(rows) or not isinstance(entry_price,(int,float)) or entry_price<=0:
        return None
    exit_row=rows[exit_i]
    ret=(exit_row["close"]/entry_price-1)*100
    mfe=None; mae=None
    for i in range(entry_i, exit_i+1):
        hi,lo=rows[i].get("high"),rows[i].get("low")
        if isinstance(hi,(int,float)):
            v=(hi/entry_price-1)*100
            mfe=v if mfe is None else max(mfe,v)
        if isinstance(lo,(int,float)):
            v=(lo/entry_price-1)*100
            mae=v if mae is None else min(mae,v)
    return {
        "entry_date":rows[entry_i]["date"],"entry_price":round(entry_price,4),
        "exit_date":exit_row["date"],"exit_price":round(exit_row["close"],4),
        "return_pct":round(ret,4),
        "mfe_pct":round(mfe,4) if mfe is not None else None,
        "mae_pct":round(mae,4) if mae is not None else None,
    }

METHODS = {
    "NEXT_OPEN":"訊號後下一交易日開盤直接進",
    "WAIT_1_OPEN":"多等1個交易日，再下一日開盤進",
    "WAIT_2_OPEN":"多等2個交易日，再下一日開盤進",
    "LIMIT_SIGNAL_CLOSE_3D":"3日內回測訊號日收盤價掛限價",
    "LIMIT_MINUS2_5D":"5日內回檔到訊號收盤-2%掛限價",
    "LIMIT_MINUS3_5D":"5日內回檔到訊號收盤-3%掛限價",
    "LIMIT_MINUS5_5D":"5日內回檔到訊號收盤-5%掛限價",
    "LIMIT_SIGNAL_LOW_5D":"5日內回測訊號日低點掛限價",
    "FIRST_RED_NEXT_OPEN_5D":"5日內第一次收黑後，隔日開盤進",
    "CLOSE_RETEST_NEXT_OPEN_5D":"5日內第一次收盤<=訊號收盤，隔日開盤進",
    "PULLBACK2_UPTURN_7D":"7日內先回檔2%，再出現收盤轉漲，隔日開盤進",
    "PULLBACK3_UPTURN_7D":"7日內先回檔3%，再出現收盤轉漲，隔日開盤進",
    "BREAK_SIGNAL_HIGH_5D":"5日內突破訊號日高點時進",
    "CLOSE_ABOVE_SIGNAL_HIGH_NEXT_OPEN_5D":"5日內收盤站上訊號日高點，隔日開盤進",
}

def metrics(items, eligible_count):
    if not items:
        return {"eligible":eligible_count,"fills":0,"fill_rate_pct":0,"wins":0,"win_rate_pct":None,"avg_return_pct":None,"median_return_pct":None,"avg_mfe_pct":None,"avg_mae_pct":None}
    rets=[x["return_pct"] for x in items]
    mfes=[x["mfe_pct"] for x in items if x.get("mfe_pct") is not None]
    maes=[x["mae_pct"] for x in items if x.get("mae_pct") is not None]
    wins=sum(1 for x in rets if x>0)
    return {
        "eligible":eligible_count,
        "fills":len(items),
        "fill_rate_pct":round(len(items)/eligible_count*100,2) if eligible_count else None,
        "wins":wins,
        "win_rate_pct":round(wins/len(items)*100,2),
        "avg_return_pct":round(mean(rets),4),
        "median_return_pct":round(median(rets),4),
        "avg_mfe_pct":round(mean(mfes),4) if mfes else None,
        "avg_mae_pct":round(mean(maes),4) if maes else None,
    }

def main():
    base=read(BASE)
    signals=base.get("signals", [])
    # Only signals whose baseline trade had enough future data; prevents recent unfinished outcomes leaking into comparison.
    eligible=[x for x in signals if x.get("completed")]
    eligible.sort(key=lambda x:x["signal_date"])
    split=max(1, int(len(eligible)*0.70))
    train_ids=set((x["signal_date"],x["group"],x["pick"]["code"]) for x in eligible[:split])
    test_ids=set((x["signal_date"],x["group"],x["pick"]["code"]) for x in eligible[split:])

    cache={}
    details={m:[] for m in METHODS}
    for sig in eligible:
        code=sig["pick"]["code"]
        rows=cache.setdefault(code, load_rows(code))
        idx={r["date"]:i for i,r in enumerate(rows)}
        si=idx.get(sig["signal_date"])
        if si is None: continue
        signal_row=rows[si]
        for method in METHODS:
            ent=entry_candidate(method, rows, si, signal_row)
            if not ent: continue
            result=evaluate(rows, ent[0], ent[1])
            if not result: continue
            rec={
                "signal_date":sig["signal_date"],"group":sig["group"],"state":sig["state"],
                "code":code,"name":sig["pick"]["name"],
                **result
            }
            details[method].append(rec)

    result_methods={}
    for method,label in METHODS.items():
        rows=details[method]
        tr=[x for x in rows if (x["signal_date"],x["group"],x["code"]) in train_ids]
        te=[x for x in rows if (x["signal_date"],x["group"],x["code"]) in test_ids]
        result_methods[method]={
            "label":label,
            "all":metrics(rows,len(eligible)),
            "train":metrics(tr,len(train_ids)),
            "test":metrics(te,len(test_ids)),
        }

    # Rank recommendation candidates: require >=60% test fill and >=15 test trades;
    # sort first by test win rate, then test avg return.
    ranked=[]
    for method,x in result_methods.items():
        t=x["test"]
        if t["fills"] >= 15 and (t["fill_rate_pct"] or 0) >= 60:
            ranked.append({
                "method":method,"label":x["label"],
                "test_win_rate_pct":t["win_rate_pct"],
                "test_avg_return_pct":t["avg_return_pct"],
                "test_median_return_pct":t["median_return_pct"],
                "test_fill_rate_pct":t["fill_rate_pct"],
                "all_win_rate_pct":x["all"]["win_rate_pct"],
                "all_avg_return_pct":x["all"]["avg_return_pct"],
                "all_fill_rate_pct":x["all"]["fill_rate_pct"],
            })
    ranked.sort(key=lambda x:((x["test_win_rate_pct"] or -999),(x["test_avg_return_pct"] or -999)), reverse=True)

    out={
        "version":"ENTRY_SWEEP_V1",
        "source_backtest_version":base.get("version"),
        "anti_hindsight":{
            "signal_and_stock":"完全沿用 M1_WALK_FORWARD_V1，不重新挑訊號或股票",
            "train_test_split":"依訊號日期前70%作探索、後30%作驗證",
            "holding":"每種進場成交後固定持有20個交易日",
            "fees_tax_slippage":"未計入",
            "note":"比較進場方式，不代表未來績效；低成交率方法不可只看勝率。"
        },
        "eligible_signals":len(eligible),
        "train_signals":len(train_ids),
        "test_signals":len(test_ids),
        "methods":result_methods,
        "recommended_ranking":ranked,
        "details":details,
    }
    write(OUT,out)

if __name__=="__main__":
    main()
