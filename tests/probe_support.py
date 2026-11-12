"""Trusted test helper copied into the Docker payload; no host credential probing."""


def private_path_observation(path):
    """Record absence or access denial; visible paths and other errors fail."""
    try:
        path.stat()
    except FileNotFoundError:
        return "absent"
    except PermissionError:
        return "access_denied"
    else:
        raise AssertionError("credential directory visible")
