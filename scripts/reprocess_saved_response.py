#!/usr/bin/env python3
"""Offline, immutable-input reprocessing; never resumes a run or invokes models."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'tests'))
from audit3.reprocess import ReadOnlyStore, reprocess_response
from audit3.acceptance import assert_known_cause
from audit3.completion import VERSION
from audit3.security import PolicyError
from integration_support import assert_real_process


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store', type=Path, default=ROOT / '.audit3')
    parser.add_argument('--run', required=True)
    parser.add_argument('--invocation', required=True)
    parser.add_argument('--response', type=Path, required=True)
    parser.add_argument('--certificates', type=Path, required=True)
    parser.add_argument('--completion-review', type=Path, required=True)
    parser.add_argument('--known-path', required=True)
    parser.add_argument('--known-line', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.absolute()
    if (destination.exists() or destination.is_relative_to(args.store.absolute())
        or destination.is_relative_to(args.response.absolute().parent)):
        raise ValueError('Saída deve ser nova e separada do store e das evidências originais')
    raw = args.response.read_bytes()
    certificates = json.loads(args.certificates.read_text())
    review = json.loads(args.completion_review.read_text())
    store = ReadOnlyStore(args.store)
    acceptance = {'version': VERSION, 'new_real_execution': False, 'passed': False}
    report = None
    try:
        report, view = reprocess_response(store, args.run, args.invocation, raw, certificates, review)
        events = sorted([store.get(args.run, 'events/' + n) for n in store.names(args.run, 'events')], key=lambda e:e['at'])
        from audit3.schemas import RunManifest
        assert_real_process(view, RunManifest.model_validate(report['manifest']), report, events)
        result = assert_known_cause(report, {'path':args.known_path,'start':args.known_line,'end':args.known_line})
        acceptance.update(passed=True, **result)
    except AssertionError as exc:
        acceptance['failure'] = str(exc) or 'Requisito de participação/inspeção/conclusão não satisfeito'
    except PolicyError as exc:
        acceptance['evidence_gap'] = str(exc)
    code_files = ['src/audit3/completion.py','src/audit3/causality.py','src/audit3/acceptance.py',
        'src/audit3/reprocess.py','src/audit3/workflow.py','src/audit3/report.py',
        'src/audit3/tools.py','tests/integration_support.py','tests/test_fixtures_integration.py',
        'scripts/reprocess_saved_response.py']
    metadata = {'version': VERSION, 'new_real_execution': False, 'model_calls': 0,
        'original_response_sha256':hashlib.sha256(raw).hexdigest(), 'run_id':args.run,
        'selected_invocation':args.invocation, 'criteria':{
            'scope_completion':'no structural blockers, pending phases or unexplained limitations',
            'roles_and_inspections':'existing assert_real_process requirements retained',
            'causes':'one verified cause, one verdict per preserved ID',
            'known_location':{'path':args.known_path,'line':args.known_line},
            'control_case':'no other proven/risk finding'},
        'code_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in code_files}}
    destination.mkdir(parents=True)
    records = [('derived-acceptance.json',acceptance),('version-and-criteria.json',metadata)]
    if report is not None:
        records.append(('derived-report.json',report))
    for name, data in records:
        (destination/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    (destination/'original-response.json').write_bytes(raw)
    print(json.dumps({'output':str(destination),'new_real_execution':False,
        'raw_status':report['state']['status'] if report else None,
        'derived_status':report['completion_assessment']['status'] if report else 'evidence_gap',
        'derived_acceptance':acceptance['passed'],
        'cause_count':len(report['proven_causal_groups']) if report else None,
        'preserved_verdicts':len(report['verdicts']) if report else None},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
