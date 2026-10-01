#!/usr/bin/env python3
"""Run offline maintenance regressions. Does not submit any generation jobs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/production-ops/scripts'))
from brain_handoff import POLICY
SUITES=['tools/short-drama-writer/scripts','tools/reference-builder/scripts',
        'tools/visual-continuity-prompter/scripts','tools/production-ops/scripts','tools/tests']


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path)
    a=p.parse_args();rows=[]
    for rel in SUITES:
        proc=subprocess.run([sys.executable,'-m','unittest','discover','-s',str(ROOT/rel),
            '-p','test_*.py'],cwd=ROOT,capture_output=True,text=True,timeout=120)
        log=proc.stdout+proc.stderr;match=re.search(r'Ran (\d+) tests?',log)
        count=int(match[1]) if match else 0
        skip=re.search(r'skipped=(\d+)',log)
        row={'suite':rel,'tests':count,'skipped':int(skip[1]) if skip else 0,'returncode':proc.returncode,'output':log}
        rows.append(row);print(rel,':',count,'tests,', 'PASS' if not proc.returncode and count else 'FAIL')
    maintenance=[]
    for script in ['sync_skill.py','build_brain_skill.py']:
        proc=subprocess.run([sys.executable,str(ROOT/'scripts'/script),'--check'],
            cwd=ROOT,capture_output=True,text=True,timeout=30)
        maintenance.append({'check':script,'returncode':proc.returncode,'output':proc.stdout+proc.stderr})
        print(script,':','PASS' if proc.returncode==0 else 'FAIL')
    success=all(r['returncode']==0 and r['tests']>0 for r in rows) and all(r['returncode']==0 for r in maintenance)
    result={'status':'PASS' if success else 'FAIL','policy_version':POLICY,
        'checked_at_utc':datetime.now(timezone.utc).isoformat(),
        'test_count':sum(r['tests'] for r in rows),'skipped_count':sum(r['skipped'] for r in rows),'python':sys.version,'suites':rows,'maintenance':maintenance,
        'real_generation_executed':False,'user_video_inspected':False,
        'scope':'Synthetic/offline code, contract and document consistency checks only.'}
    if a.report:
        a.report.parent.mkdir(parents=True,exist_ok=True)
        a.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if not success:
        for r in rows+maintenance:
            if r['returncode']:print(r['output'],file=sys.stderr)
    print('TOTAL:',result['test_count'],'STATUS:',result['status'])
    return 0 if success else 1


if __name__=='__main__':raise SystemExit(main())
