"""Canonical Godot adapter command line."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from . import install, server

LIFECYCLE_VERBS = {"install", "status", "verify", "uninstall", "upgrade"}


def main(argv: Sequence[str] | None = None) -> int:
    """Route lifecycle verbs while preserving the historical no-argument server."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in LIFECYCLE_VERBS:
        return install.main(arguments)
    if arguments == ["serve"]:
        arguments = []
    if arguments:
        raise SystemExit(f"unknown command: {arguments[0]}")
    server.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
