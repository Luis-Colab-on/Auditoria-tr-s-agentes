import argparse
import json
from pathlib import Path
from audit3.evaluation import evaluate

parser = argparse.ArgumentParser()
parser.add_argument('--report', type=Path, required=True)
parser.add_argument('--fixture', required=True)
parser.add_argument('--mapping', type=Path, required=True, help='reviewed JSON {finding_id: known_defect_id_or_null}')
args = parser.parse_args()
oracle = json.loads((Path(__file__).resolve().parents[1]/'tests/expectations.json').read_text())
print(json.dumps(evaluate(json.loads(args.report.read_text()), oracle[args.fixture]['known_defects'], json.loads(args.mapping.read_text())), indent=2, ensure_ascii=False))
