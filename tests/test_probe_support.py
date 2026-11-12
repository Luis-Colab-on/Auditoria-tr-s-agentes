"""Deterministic infrastructure doubles, not executions of a Docker payload."""
import errno
from types import SimpleNamespace
import pytest
from probe_support import private_path_observation


def raising_path(error):
    def stat():
        raise error
    return SimpleNamespace(stat=stat)


@pytest.mark.parametrize("code,expected", [(errno.ENOENT, "absent"), (errno.EACCES, "access_denied"), (errno.EPERM, "access_denied")])
def test_private_path_distinguishes_absence_and_denial(code, expected):
    path = raising_path(OSError(code, "synthetic filesystem result"))
    assert private_path_observation(path) == expected


def test_private_path_still_rejects_visible_credentials():
    path = SimpleNamespace(stat=lambda: object())
    with pytest.raises(AssertionError, match="credential directory visible"):
        private_path_observation(path)


@pytest.mark.parametrize("code", [errno.EIO, errno.ELOOP, errno.ENOTDIR])
def test_unexpected_filesystem_errors_are_not_misreported_as_protection(code):
    error = OSError(code, "synthetic unexpected filesystem error")
    with pytest.raises(OSError) as observed:
        private_path_observation(raising_path(error))
    assert observed.value is error
