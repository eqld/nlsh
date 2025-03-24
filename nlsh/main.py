#!/usr/bin/env python3
"""
Main entry point for nlsh.

This module provides the main entry point for the nlsh utility.
"""

import sys
import traceback
from nlsh.cli import main

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"Fatal error: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
