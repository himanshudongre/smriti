"""Allow `python -m smriti_cli` as an entry point."""

import sys

from .main import main

if __name__ == "__main__":
    sys.exit(main())
