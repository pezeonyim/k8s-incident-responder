"""Shared test setup.

Disables RBAC impersonation by default so command-building assertions are about
the command itself, not the identity flags. One test re-enables it explicitly.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

# identity.py reads this at import time, so it must be set before anything
# imports the modules under test.
os.environ.setdefault("USE_RBAC", "false")
