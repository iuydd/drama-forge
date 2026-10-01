#!/usr/bin/env python3
"""Actual run metrics and bounded repair experience. No fabricated success rates.

Keep real and synthetic experiments separate. UNKNOWN is neither PASS nor a
quiet exclusion: report coverage and unknown count beside FP/FN denominators.
"""
from __future__ import annotations
from collections import defaultdict
import math
from pathlib import Path
from typing import Any
from brain_handoff import verify_record, text, digest


def wilson(successes: int,total: int)->list[float]|None:
    if total==0:return None
    z=1.959963984540054;p=successes/total;d=1+z*z/total
    center=(p+z*z/(2*total))/d;half=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/d
    return [max(0,center-half),min(1,center+half)]


def summarize(rows:list[dict],root:Path|None=None)->dict:
    groups=defaultdict(list);seen=set()
    for r in rows:
        key=(r.get('run_id'),r.get('case_id'),r.get('attempt'))
        if any(v is None for v in key) or key in seen:raise ValueError('duplicate/incomplete experiment identity')
        seen.add(key)
        if r.get('data_kind') not in {'real','synthetic'}:raise ValueError('real/synthetic classification required')
        if type(r.get('ground_truth_defect')) is not bool:raise ValueError('independently adjudicated ground truth required')
        if r.get('decision') not in {'PASS','FAIL','UNKNOWN'}:raise ValueError('decision required')
        if r['data_kind']=='real':
            if root is None:raise ValueError('real metrics require accessible actual media/evidence')
            for name in ('media','adjudication_evidence'):
                if verify_record(r.get(name),root):raise ValueError('real run missing media or independent adjudication')
            if not text(r.get('runtime_config_sha256')) or not text(r.get('reviewer_profile_id')):raise ValueError('real run configuration missing')
        for field in ('cost_minor','input_tokens','output_tokens'):
            val=r.get(field)
            if val is not None and (type(val) is not int or val<0):raise ValueError('actual counters must be nonnegative integers or unknown')
        for field in ('accepted_seconds','latency_s'):
            val=r.get(field)
            if val is not None and (type(val) not in (int,float) or not math.isfinite(val) or val<0):raise ValueError('finite actual seconds required')
        if r.get('accepted_seconds',0) and r['decision']!='PASS':raise ValueError('failed/unknown attempt cannot claim accepted seconds')
        groups[(r['data_kind'],r.get('variant','default'),r.get('runtime_config_sha256','unspecified'),r.get('currency','unknown'))].append(r)
    result=[]
    for (kind,variant,config,currency),items in sorted(groups.items()):
        tp=sum(x['ground_truth_defect'] and x['decision']=='FAIL' for x in items)
        fn=sum(x['ground_truth_defect'] and x['decision']=='PASS' for x in items)
        fp=sum(not x['ground_truth_defect'] and x['decision']=='FAIL' for x in items)
        tn=sum(not x['ground_truth_defect'] and x['decision']=='PASS' for x in items)
        unknown=sum(x['decision']=='UNKNOWN' for x in items)
        totals={}
        for field in ('cost_minor','input_tokens','output_tokens','latency_s'):
            known=[x[field] for x in items if x.get(field) is not None]
            totals[field]={'known_total':sum(known),'missing_rows':len(items)-len(known),'complete':len(known)==len(items)}
        seconds=sum(x.get('accepted_seconds') or 0 for x in items)
        cost=totals['cost_minor'];unit_cost=cost['known_total']/seconds if cost['complete'] and seconds>0 else None
        result.append({'data_kind':kind,'variant':variant,'runtime_config_sha256':config,'currency':currency,
            'attempts':len(items),'known_decisions':tp+fn+fp+tn,'unknown':unknown,'true_positive':tp,'false_negative':fn,'false_positive':fp,'true_negative':tn,
            'false_negative_rate_known':fn/(tp+fn) if tp+fn else None,'false_positive_rate_known':fp/(fp+tn) if fp+tn else None,
            'sensitivity_known_interval95':wilson(tp,tp+fn),'specificity_known_interval95':wilson(tn,tn+fp),
            'accepted_seconds':seconds,'cost_minor_per_accepted_second':unit_cost,'actual_counters':totals})
    return {'schema_version':'drama-metrics-1','groups':result,'real_runs':sum(r['data_kind']=='real' for r in rows),
            'warning':'Intervals describe the labeled sample, not guaranteed future production quality. Missing counters are not estimated.'}


def validate_repair_entry(entry:dict,root:Path)->list[str]:
    errors=[]
    for k in ('failure_chain_id','runtime_config_sha256','feature','diagnosed_cause','chosen_method','outcome'):
        if not text(entry.get(k)):errors.append('repair: missing '+k)
    if entry.get('outcome') not in {'PASS','FAIL','UNKNOWN'}:errors.append('repair: actual outcome required')
    for key in ('before_media','after_media','review_evidence'):
        errors+=verify_record(entry.get(key),root)
    if not isinstance(entry.get('retained_quality_spec'),dict):errors.append('repair: protected quality specification missing')
    return errors


def paired_comparison(rows:list[dict],root:Path|None=None)->dict:
    summary=summarize(rows,root);variants={r.get('variant','default') for r in rows}
    case_sets={v:{r['case_id'] for r in rows if r.get('variant','default')==v} for v in variants}
    comparable=len(case_sets)==2 and len({frozenset(s) for s in case_sets.values()})==1
    configs={r.get('runtime_config_sha256') for r in rows}
    return dict(summary,paired_case_coverage=comparable,same_generation_config=len(configs)==1,
                quality_noninferiority_proven=False,
                comparison_note='Same case coverage is necessary, not sufficient: also freeze quality/budget, blind order and real audience criteria.')
