# Frozen Phase 0 record: shim so the probe scripts still import. Real code moved to app/llm.py (tag phase0-final has the original).
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.llm import *  # noqa
from app.llm import os, json, time  # noqa
