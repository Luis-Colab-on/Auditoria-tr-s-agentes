"""Package only a synthetic fixture as ZIP; never executes its code on the host."""
import argparse
import zipfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('fixture', choices=['bug','clean','layered','rare','partial','wordpress','versions/before','versions/after'])
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1] / 'tests/fixtures' / args.fixture
args.output.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(root.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            archive.write(path, path.relative_to(root).as_posix())
print(args.output)
