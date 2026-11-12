import zipfile
from pathlib import Path
import pytest
from audit3.config import Config, Profile
from audit3.evidence import Store
from audit3.snapshot import prepare

# Audited fixtures must only run in disposable containers, never via host collection.
collect_ignore = ["fixtures"]


@pytest.fixture
def make_run(tmp_path):
    counter = 0
    def create(content=None, config=None, profile=None):
        nonlocal counter
        counter += 1
        archive = tmp_path / f"fixture-{counter}.zip"
        with zipfile.ZipFile(archive, "w") as z:
            for name, data in (content or {"app.py": "def safe(value):\n    return max(0, value)\n", "tests/test_app.py": "# synthetic test specification\n"}).items():
                z.writestr(name, data)
        store = Store(tmp_path / "state")
        manifest = prepare(store, str(archive), None, profile or Profile(name="synthetic"), config or Config(), "Use apenas dados sintéticos; saldo deve diminuir no reembolso.")
        return store, manifest
    return create
