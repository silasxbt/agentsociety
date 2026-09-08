#!/usr/bin/env python3
"""Extract transparent, rule-selected qualitative cases from batch traces."""
from __future__ import annotations
import json
from pathlib import Path

def load(p):
    return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines() if x.strip()] if p.is_file() else []
def replay(run):
    rows=[]
    for p in sorted((run/'replay').glob('elder_support_agent_state.*.jsonl')): rows += load(p)
    # Replay shards are hash-named, so filename order is not chronological.
    return sorted(rows, key=lambda r: (r.get('t',''), r.get('agent_id',-1)))

def main():
    root=Path(__file__).resolve().parents[1]/'tmp/batch'; cases=[]
    # Pre-registered rule: strongest observed rebound among casework_s1/s3, requiring intervention and m18/m19/m24 replay.
    candidates=[]
    for name in ('casework_s1','casework_s3'):
        run=root/name; ds=load(run/'env/ElderSupportEnv/state/decisions.jsonl'); rr=replay(run)
        visits={d.get('elder') for d in ds if d.get('action')=='casework_visit' and 7<=d.get('month',-1)<=18}
        for aid in sorted(x for x in visits if isinstance(x,int)):
            # Rows are sorted by timestamp in replay(); index 0 is baseline month 0.
            seq=[r for r in rr if r.get('agent_id')==aid]
            if len(seq)<25: continue
            r18,r19,r24=seq[18],seq[19],seq[24]
            rebound=r24.get('loneliness',0)-r18.get('loneliness',0)
            if rebound>=.05:
                quote=next((d for d in ds if d.get('agent_id')==aid and d.get('reason')),None)
                candidates.append((rebound,name,aid,r18,r19,r24,quote))
    if candidates:
        rebound,name,aid,r18,r19,r24,q=max(candidates)
        cases.append({'type':'casework_withdrawal_rebound','evidence_level':'exploratory','selection_rule':'eligible casework run, intervention visit, replay at months 18/19/24, largest m18-to-m24 loneliness rebound >= .05','run':name,'agent_id':aid,'months':{'18':r18,'19':r19,'24':r24},'decision_quote':q,'rebound':round(rebound,4)})
    # Timebank: explicit matches are required. Current only match-bearing run is s3, which fails strict gate, so label exploratory.
    run=root/'timebank_s3'; ds=load(run/'env/ElderSupportEnv/state/decisions.jsonl'); rr=replay(run)
    matches=[d for d in ds if d.get('action')=='timebank_match']
    if matches:
        m=matches[0]; aid=m.get('elder'); seq=[r for r in rr if r.get('agent_id')==aid]
        if len(seq)>=25:
            cases.append({'type':'timebank_persistence','evidence_level':'exploratory_only_invalid_run','selection_rule':'first explicit timebank match in the only match-bearing run; report replay persistence, not causal proof','run':'timebank_s3','helper_id':m.get('helper'),'elder_id':aid,'match':m,'months':{'18':seq[18],'19':seq[19],'24':seq[24]},'note':'Run exceeds the 10% decision-silence gate; no clean confirmatory timebank case is available.'})
    out=root/'narrative_cases.json'; out.write_text(json.dumps({'selection_rules_version':'2026-09-04','cases':cases},ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps({'cases':len(cases),'output':str(out)},ensure_ascii=False))
if __name__=='__main__': main()
