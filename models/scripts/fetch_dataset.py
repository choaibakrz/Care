"""Put a dataset in data/raw/<name>, no Roboflow API key needed.

Sources (first match wins):
  folder   path to an already-extracted YOLO export
  zip      path to the zip you downloaded from the Universe page
  URL      direct link to a zip
  hf:REPO  a Hugging Face dataset repo holding a YOLO export
  roboflow:workspace/project/version   (optional; needs ROBOFLOW_API_KEY)

Getting the zip without a key: open the dataset on universe.roboflow.com,
click Download Dataset, choose the YOLOv8 (or YOLO26) format, "download zip".
That needs a free login in the browser, not an API key.
"""
import argparse
from _common import *  # noqa: F401,F403
from medsort.training import get_export

p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
p.add_argument("dataset", choices=["hospital_consumables", "biosafety_ppe"])
p.add_argument("--source", required=True)
a = p.parse_args()

exp = get_export(a.dataset, a.source)
print(f"ok: {exp.root}")
print(f"classes ({len(exp.names)}): {exp.names}")
for split in ("train", "val", "test"):
    print(f"  {split}: {len(exp.samples(split))} images")
