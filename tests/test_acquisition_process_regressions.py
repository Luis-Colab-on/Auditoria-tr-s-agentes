"""Benign local acquisition/process reproductions; never execute audited code."""
import asyncio
import hashlib
import shlex
import subprocess
import sys
import time

import pytest

from audit3.config import Config, Profile
from audit3.evidence import Store
from audit3.executor import process
from audit3.security import PolicyError
from audit3.snapshot import git_entries, prepare, verify_source


def git_fixture(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args, data=None):
        return subprocess.run(["git", "-C", str(repo), *args], input=data,
                              check=True, capture_output=True).stdout

    git("init")
    (repo / "app.py").write_text("value = 1\n")
    (repo / ".gitattributes").write_text("app.py filter=benign\n")
    git("add", ".")
    git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
        "commit", "-m", "synthetic acquisition fixture")
    return repo, git


def test_local_git_filter_never_runs_and_commit_bytes_preserved(tmp_path):
    repo, git = git_fixture(tmp_path)
    marker = tmp_path / "filter-called"
    callback = tmp_path / "benign_filter.py"
    callback.write_text("import pathlib, sys\n"
                        f"pathlib.Path({str(marker)!r}).write_text('called')\n"
                        "sys.stdout.buffer.write(sys.stdin.buffer.read())\n")
    git("config", "filter.benign.clean", shlex.join([sys.executable, str(callback)]))
    (repo / "app.py").write_text("value = 2\n")  # same size: status invokes clean
    store = Store(tmp_path / "state")
    m = prepare(store, str(repo), "HEAD", Profile(name="synthetic"), Config())
    assert not marker.exists(), "git status executed the received clean filter"
    assert store.path(m.run_id, "source/app.py").read_text() == "value = 1\n"
    assert (repo / "app.py").read_text() == "value = 2\n"
    assert m.tree_state == "worktree_not_inspected_commit_only"
    verify_source(store, m)


def test_bare_acquisition_and_uninspected_clean_worktree(tmp_path):
    repo, git = git_fixture(tmp_path)
    entries, sha, _, state, _ = git_entries(repo, "HEAD", Config())
    assert state == "worktree_not_inspected_commit_only"
    bare = tmp_path / "bare.git"
    subprocess.run(["git", "clone", "--bare", str(repo), str(bare)], check=True, capture_output=True)
    bare_entries, bare_sha, _, bare_state, _ = git_entries(bare, sha, Config())
    assert (bare_entries, bare_sha, bare_state) == (entries, sha, "bare")


def test_acquisition_disables_received_hooks_and_fsmonitor(tmp_path):
    repo, git = git_fixture(tmp_path)
    marker = tmp_path / "hook-called"
    hook = tmp_path / "benign-hook"
    hook.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\n")
    hook.chmod(0o755)
    git("config", "core.fsmonitor", str(hook))
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "post-index-change").symlink_to(hook)
    git("config", "core.hooksPath", str(hooks))
    (repo / "app.py").write_text("value = 2\n")
    git_entries(repo, "HEAD", Config())
    assert not marker.exists()


def test_git_links_and_submodules_remain_excluded_without_following(tmp_path):
    repo, git = git_fixture(tmp_path)
    commit = git("rev-parse", "HEAD").decode().strip()
    outside = tmp_path / "outside.py"
    outside.write_text("raise AssertionError('must never execute')\n")
    (repo / "link.py").symlink_to(outside)
    git("add", "link.py")
    git("update-index", "--add", "--cacheinfo", f"160000,{commit},module")
    git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
        "commit", "-m", "synthetic links")
    store = Store(tmp_path / "state")
    manifest = prepare(store, str(repo), "HEAD", Profile(name="synthetic"), Config())
    index = {f.path: f for f in manifest.files}
    assert index["link.py"].reason == "symlink_excluded"
    assert index["module"].reason == "submodule_not_materialized"
    assert manifest.submodules == ["module@" + commit]
    assert not store.path(manifest.run_id, "source/link.py").exists()
    assert not store.path(manifest.run_id, "source/module").exists()
    assert outside.read_text() == "raise AssertionError('must never execute')\n"
    verify_source(store, manifest)


@pytest.mark.parametrize("size", [1_999_999, 2_000_000, 2_000_001])
def test_git_symlink_size_checked_before_blob_materialization(tmp_path, monkeypatch, size):
    import audit3.snapshot as snapshot
    repo, git = git_fixture(tmp_path)
    oid = git("hash-object", "-w", "--stdin", data=b"x" * size).decode().strip()
    git("update-index", "--add", "--cacheinfo", f"120000,{oid},link")
    git("-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
        "commit", "-m", "synthetic link blob")
    original = snapshot.git
    materialized = []

    def observed(repo, *args):
        if args[:2] == ("cat-file", "blob"):
            materialized.append(args[2])
        return original(repo, *args)

    monkeypatch.setattr(snapshot, "git", observed)
    if size > 2_000_000:
        with pytest.raises(PolicyError, match="arquivo excede limite"):
            snapshot.git_entries(repo, "HEAD", Config())
        assert oid not in materialized
    else:
        entries, *_ = snapshot.git_entries(repo, "HEAD", Config())
        assert ("link", b"x" * size, "symlink_excluded") in entries


@pytest.mark.parametrize("config", [Config(max_files=1), Config(max_total_bytes=1)])
def test_git_inventory_limits_checked_before_excess_blob(tmp_path, monkeypatch, config):
    import audit3.snapshot as snapshot
    repo, git = git_fixture(tmp_path)
    original = snapshot.git
    read = []

    def observed(repo, *args):
        if args[:2] == ("cat-file", "blob"):
            read.append(args[2])
        return original(repo, *args)

    monkeypatch.setattr(snapshot, "git", observed)
    with pytest.raises(PolicyError, match="inventário excede limites"):
        snapshot.git_entries(repo, "HEAD", config)
    assert len(read) <= (1 if config.max_files == 1 else 0)


def parent_with_child(tmp_path, child_seconds=2):
    # Trusted temporary test helper, wholly independent of source acquisition.
    pid_file = tmp_path / "child.pid"
    script = tmp_path / "controller_helper.py"
    script.write_text("import subprocess, sys, time\nfrom pathlib import Path\n"
                      f"child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep({child_seconds})'])\n"
                      f"Path({str(pid_file)!r}).write_text(str(child.pid))\n"
                      "print('ready', flush=True)\ntime.sleep(10)\n")
    return [sys.executable, str(script)], pid_file


def process_running(pid):
    try:
        with open(f"/proc/{pid}/stat") as stream:
            return stream.read().split(") ", 1)[1][0] != "Z"
    except FileNotFoundError:
        return False


def test_timeout_kills_descendant_with_inherited_pipe(tmp_path):
    argv, pid_file = parent_with_child(tmp_path, child_seconds=.85)
    started = time.monotonic()
    result = asyncio.run(process(argv, .15))
    elapsed = time.monotonic() - started
    assert result.timeout
    assert elapsed < .65, f"timeout cleanup consumed {elapsed:.3f}s"
    assert not process_running(int(pid_file.read_text()))
    assert result.stdout == "ready\n"
    assert result.output_complete
    assert result.execution_seconds >= .15
    assert 0 <= result.cleanup_seconds < .5


def test_timeout_includes_drain_after_parent_has_already_exited(tmp_path):
    argv, pid_file = parent_with_child(tmp_path)
    script = tmp_path / "controller_helper.py"
    script.write_text(script.read_text().replace("time.sleep(10)", "sys.exit(0)"))
    started = time.monotonic()
    result = asyncio.run(process(argv, .15))
    assert result.timeout and time.monotonic() - started < .65
    assert not process_running(int(pid_file.read_text()))


def test_pipe_cleanup_has_deadline_even_without_eof(monkeypatch):
    import audit3.executor as executor
    original = asyncio.create_subprocess_exec

    class StuckReader:
        async def read(self, size):
            await asyncio.Future()

    async def with_stuck_pipe(*args, **kwargs):
        proc = await original(*args, **kwargs)
        proc.stdout = StuckReader()
        return proc

    monkeypatch.setattr(executor.asyncio, "create_subprocess_exec", with_stuck_pipe)
    started = time.monotonic()
    result = asyncio.run(process([sys.executable, "-c", "pass"], .05))
    assert result.timeout and not result.output_complete and result.truncated
    assert result.cleanup_seconds >= executor.PROCESS_CLEANUP_SECONDS
    assert time.monotonic() - started < .65
    assert result.out_hash == hashlib.sha256(b"").hexdigest()


def test_cancellation_kills_descendants_and_drainer_tasks(tmp_path):
    argv, pid_file = parent_with_child(tmp_path)

    async def run():
        task = asyncio.create_task(process(argv, 5))
        async with asyncio.timeout(2):
            while not pid_file.exists():
                await asyncio.sleep(.005)
        started = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert time.monotonic() - started < .65
        assert not process_running(int(pid_file.read_text()))
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task() and not t.done()]

    asyncio.run(run())


def test_output_hash_covers_full_stream_while_retention_is_bounded():
    result = asyncio.run(process([sys.executable, "-c", "import sys; sys.stdout.write('x'*20000)"], 2, 1024))
    assert result.code == 0 and result.truncated
    assert result.stdout == "x" * 1024
    assert result.out_hash == hashlib.sha256(b"x" * 20000).hexdigest()
