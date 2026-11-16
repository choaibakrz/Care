"""Run the conformance checks against any registered backend.
  python scripts/check_backend.py yolo --image datasets/unified/detection/val/images/<some>.jpg
  python scripts/check_backend.py mine --config '{"weights": "w.pt"}' --image photo.jpg
"""
import argparse
import importlib
import json
from _common import *  # noqa: F401,F403
from medsort.api import create_backend
from medsort.conformance import check_backend

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("backend")
p.add_argument("--image", required=True)
p.add_argument("--config", default="{}", help="JSON kwargs for the backend")
p.add_argument("--module", default=None, help="python module that registers a custom backend, e.g. mymodel")
a = p.parse_args()
if a.module:
    importlib.import_module(a.module)
problems = check_backend(create_backend(a.backend, **json.loads(a.config)), a.image)
print("CONFORMS" if not problems else f"{len(problems)} violation(s):")
for pr in problems:
    print(" -", pr)
raise SystemExit(1 if problems else 0)
