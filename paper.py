#!/usr/bin/env python3
"""Compatibility entry point used by Homebrew and existing local symlinks."""

from paper_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
