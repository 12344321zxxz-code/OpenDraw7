#!/usr/bin/env python3
"""Start OpenDraw7 from a source checkout or a frozen build."""
import sys

from opendraw7.app import main

if __name__ == "__main__":
    sys.exit(main())
