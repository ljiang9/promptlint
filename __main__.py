"""Enables `python -m promptlint`."""
import sys

if __package__:
    from .promptlint import main
else:
    from promptlint import main

if __name__ == "__main__":
    sys.exit(main())
