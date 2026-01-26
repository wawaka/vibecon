#!/usr/bin/env python3

# This is the new entry point that delegates to the refactored package
import sys
from pathlib import Path

# Add the current directory to Python path to import vibecon package
sys.path.insert(0, str(Path(__file__).parent))

from vibecon import main

if __name__ == "__main__":
    main()