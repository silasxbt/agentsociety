#!/usr/bin/env python3
"""Validate and summarize elder-support batch runs.

Outputs comparison.json, comparison_long.csv, and figures/*.png. Invalid or
incomplete runs are reported separately and never enter condition summaries.
"""
from __future__ import annotations
import argparse, csv, json, re, statistics
from collections import defaultdict
from pathlib import Path
IV_START, IV_END = 7, 18
CONDITIONS = ["none", "casework", "timebank", "platform"]
METRICS = {"isolation_rate":"isolation_rate", "deep_isolation_rate":"deep_isolation_rate", "avg_loneliness":"avg_loneliness", "avg_active_ties":"avg_active_ties"}

def read_jsonl(p):
    if not p.is_file(): return []
    out=[]
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try: out.append(json.loads(line))
            except json.JSONDecodeError: pass
    return out

def validate(d, expected=24):
    reasons=[]; mp=d/"env/ElderSupportEnv/state/metrics.jsonl"; dp=d/"env/ElderSupportEnv/state/decisions.jsonl"
    ms=read_jsonl(mp); ds=read_jsonl(dp)
    months=[m.get("month") for m in ms]
    if not (d/"DONE").is_file(): reasons.append("missing DONE")
    if months != list(range(expected+1)): reasons.append(f"months are not 0..{expected}")
    required=set(METRICS)|{"month"}
    for m in ms:
        if not required.issubset(m): reasons.append("missing metric field"); break
        if any(not isinstance(m[k],(int,float)) for k in required if k!="month"): reasons.append("non-numeric metric"); break
        if any(m[k] < 0 or (k != "avg_active_ties" and m[k] > 1) for k in METRICS): reasons.append("metric out of range"); break
    if not ds: reasons.append("zero decisions")
    focal_months={(x.get("agent_id"),x.get("month")) for x in ds if x.get("agent_id",0)>0}
    focal=sorted({a for a,m in focal_months})
    cells=len(focal)*len(months)
    silence=1-len(focal_months)/cells if cells else 1.0
    if silence > .10: reasons.append(f"decision silence {silence:.1%} > 10%")
    return {"valid":not reasons,"reasons":reasons,"metrics":ms,"decisions":ds,"silence_rate":round(silence,3),"months":len(ms)-1}

def avg(ms,key,lo,hi):
    x=[m[key] for m in ms if lo<=m["month"]<=hi]
    return sum(x)/len(x) if x else None

def trace_stats(d):
    calls=errors=0; seconds=0.0
    for p in (d/"trace").glob("trace_*.jsonl"):
        for r in read_jsonl(p):
            if r.get("name")!="llm.completion": continue
            calls+=1; st=r.get("status",{}); errors += int(st.get("code") not in (None,"ok",0))
            seconds += max(0,(r.get("end_time_unix_nano",0)-r.get("start_time_unix_nano",0))/1e9)
    return {"calls":calls,"errors":errors,"error_rate":round(errors/calls,4) if calls else None,"latency_s":round(seconds/calls,2) if calls else 0}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--batch-dir",default=str(Path(__file__).resolve().parents[1]/"tmp/batch")); ap.add_argument("--months",type=int,default=24); args=ap.parse_args(); batch=Path(args.batch_dir)
    valid=defaultdict(list); invalid=[]; pending=[]; long=[]; costs=[]
    for d in sorted(batch.iterdir()):
        m=re.match(r"(none|casework|timebank|platform)_s(\d+)$",d.name)
        if not m: continue
        v=validate(d,args.months); cond,seed=m.group(1),int(m.group(2)); ts=trace_stats(d)
        costs.append({"run":d.name,"condition":cond,"seed":seed,**ts})
        if ts["error_rate"] is not None and ts["error_rate"] > 0.05:
            v["reasons"].append(f"LLM completion error rate {ts['error_rate']:.1%} > 5%")
            v["valid"] = False
        if not v["valid"]:
            record={"run":d.name,"condition":cond,"seed":seed,"reasons":v["reasons"],"months":v["months"],"silence_rate":v["silence_rate"],"llm_error_rate":ts["error_rate"]}
            # Partial canonical runs are pending, not failed scientific replicates.
            if v["months"] < args.months and not (d/"INVALID").is_file(): pending.append(record)
            else: invalid.append(record)
            continue
        ms=v["metrics"]
        iso_iv=avg(ms,"isolation_rate",IV_START,IV_END); iso_post=avg(ms,"isolation_rate",19,args.months)
        lon_iv=avg(ms,"avg_loneliness",IV_START,IV_END); lon_post=avg(ms,"avg_loneliness",19,args.months)
        row={"run":d.name,"condition":cond,"seed":seed,"iso_iv":iso_iv,"lon_iv":lon_iv,"iso_post":iso_post,"lon_post":lon_post,"iso_rebound":iso_post-iso_iv,"lon_rebound":lon_post-lon_iv,"deep_final":ms[-1]["deep_isolation_rate"],"ties_final":ms[-1]["avg_active_ties"],"silence_rate":v["silence_rate"],**ts}; valid[cond].append(row)
        for mm in ms:
            for key in METRICS: long.append({"run":d.name,"condition":cond,"seed":seed,"month":mm["month"],"metric":key,"value":mm[key]})
    def stats(key,rows):
        x=[r[key] for r in rows if r.get(key) is not None];
        return {"n":len(x),"mean":round(statistics.mean(x),6) if x else None,"sd":round(statistics.stdev(x),6) if len(x)>1 else None,"min":min(x) if x else None,"max":max(x) if x else None}
    summary={c:{k:stats(k,rows) for k in ["iso_iv","lon_iv","iso_post","lon_post","iso_rebound","lon_rebound","deep_final","ties_final"]}|{"seeds":rows} for c,rows in valid.items()}
    trajectories = {}
    for metric in METRICS:
        trajectories[metric] = {}
        for cond in CONDITIONS:
            rows = [x for x in long if x["condition"] == cond and x["metric"] == metric]
            by_month = defaultdict(list)
            for x in rows:
                by_month[x["month"]].append(x["value"])
            trajectories[metric][cond] = [
                {"month": month, "n": len(vals), "mean": round(statistics.mean(vals), 6),
                 "sd": round(statistics.stdev(vals), 6) if len(vals) > 1 else None,
                 "values": vals,
                 "seed_values": [{"seed": x["seed"], "value": x["value"]}
                                 for x in rows if x["month"] == month]}
                for month, vals in sorted(by_month.items())
            ]
    paired = {}
    baseline_by_seed = {r["seed"]: r for r in valid.get("none", [])}
    for cond in CONDITIONS[1:]:
        paired[cond] = {}
        for key in ["iso_iv", "lon_iv", "iso_post", "lon_post", "iso_rebound", "lon_rebound", "deep_final", "ties_final"]:
            rows = []
            for r in valid.get(cond, []):
                base = baseline_by_seed.get(r["seed"])
                if base and r.get(key) is not None and base.get(key) is not None:
                    rows.append({"seed": r["seed"], "difference_vs_none": round(r[key] - base[key], 6)})
            vals = [r["difference_vs_none"] for r in rows]
            paired[cond][key] = {"pairs": rows, "n": len(vals),
                                 "mean_difference": round(statistics.mean(vals), 6) if vals else None,
                                 "sd_difference": round(statistics.stdev(vals), 6) if len(vals) > 1 else None}
    total_calls = sum(x["calls"] for x in costs)
    token_assumptions = {"input_per_call": 3500, "output_per_call": 450}
    pricing = {"input_usd_per_million": 4.0, "output_usd_per_million": 20.0}
    estimated_input = total_calls * token_assumptions["input_per_call"]
    estimated_output = total_calls * token_assumptions["output_per_call"]
    estimated_usd = estimated_input / 1e6 * pricing["input_usd_per_million"] + estimated_output / 1e6 * pricing["output_usd_per_million"]
    cost = {"runs": costs, "actual_calls": total_calls, "trace_errors": sum(x["errors"] for x in costs),
            "actual_tokens_available": False, "token_assumptions": token_assumptions,
            "pricing_assumptions": pricing, "estimated_input_tokens": estimated_input,
            "estimated_output_tokens": estimated_output, "estimated_usd": round(estimated_usd, 2),
            "note": "Calls and trace errors are observed; tokens and currency are estimates because traces contain no usage fields."}
    out={"windows":{"intervention":[IV_START,IV_END],"post":[19,args.months]},"valid_runs":sum(map(len,valid.values())),"invalid_runs":invalid,"pending_runs":pending,"conditions":summary,"trajectories":trajectories,"paired_contrasts_vs_none":paired,"cost":cost}
    (batch/"comparison.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    with (batch/"comparison_long.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["run","condition","seed","month","metric","value"]); w.writeheader(); w.writerows(long)
    (batch/"cost_summary.json").write_text(json.dumps(out["cost"],ensure_ascii=False,indent=2),encoding="utf-8")
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        figdir=batch/"figures"; figdir.mkdir(exist_ok=True); colors=dict(zip(CONDITIONS,["#2A78D6","#EB6834","#1BAF7A","#EDA100"]))
        for metric,label in [("isolation_rate","Isolation rate"),("avg_loneliness","Average loneliness")]:
            fig,ax=plt.subplots(figsize=(9,5));
            for c in CONDITIONS:
                rows=[x for x in long if x["condition"]==c and x["metric"]==metric]
                by=defaultdict(list)
                for x in rows: by[x["month"]].append(x["value"])
                if not by: continue
                xs=sorted(by); means=[statistics.mean(by[x]) for x in xs]; sds=[statistics.stdev(by[x]) if len(by[x])>1 else 0 for x in xs]
                ax.plot(xs,means,label=c,color=colors[c],lw=2); ax.fill_between(xs,[a-b for a,b in zip(means,sds)],[a+b for a,b in zip(means,sds)],color=colors[c],alpha=.12)
                for x in xs:
                    if len(by[x])>1: ax.scatter([x]*len(by[x]),by[x],color=colors[c],s=9,alpha=.35)
            ax.axvspan(IV_START-.5,IV_END+.5,color="#999999",alpha=.12,label="intervention")
            ax.set(xlabel="Simulated month",ylabel=label,title=f"{label}: condition means, SD bands, and seed points"); ax.legend(ncol=2); ax.grid(alpha=.2); fig.tight_layout(); fig.savefig(figdir/f"{metric}_trajectory.png",dpi=160); plt.close(fig)
        for key,label in [("iso_iv","Intervention isolation"),("lon_iv","Intervention loneliness"),("iso_post","Post-withdrawal isolation"),("lon_post","Post-withdrawal loneliness")]:
            fig,ax=plt.subplots(figsize=(8,4.5)); data=[]; labs=[]
            for c in CONDITIONS:
                vals=[r[key] for r in valid[c] if r.get(key) is not None]
                if vals: data.append(vals); labs.append(c)
            if data: ax.boxplot(data,tick_labels=labs,showfliers=False); [ax.scatter([i+1]*len(vals),vals,color=colors[c],s=28,zorder=3) for i,(c,vals) in enumerate(zip(labs,data))]
            ax.set_title(f"{label}: seed-level descriptive spread"); ax.grid(axis="y",alpha=.2); fig.tight_layout(); fig.savefig(figdir/f"{key}_seed_scatter.png",dpi=160); plt.close(fig)
    except ImportError:
        out["chart_warning"]="matplotlib unavailable; tabular outputs still generated"
        (batch/"comparison.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"valid_runs":out["valid_runs"],"invalid_runs":invalid,"pending_runs":pending,"calls":out["cost"]["actual_calls"]},ensure_ascii=False,indent=2))
if __name__=="__main__": main()
