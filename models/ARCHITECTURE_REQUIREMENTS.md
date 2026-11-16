# What a model must provide to plug into medsort

You implement ONE class. Robot code never changes. You are done when
`python scripts/check_backend.py <name> --image <photo>` prints `CONFORMS`.

```python
from medsort.api import VisionBackend, Capability, AnalysisResult, ItemResult, Box, Status, register_backend

@register_backend("mine")
class Mine(VisionBackend):
    name = "mine"
    def capabilities(self): return {Capability.DETECT}          # declare only what is really implemented
    def known_products(self): ...                               # list[str] of labels you can output
    def analyze(self, image): ...                               # -> AnalysisResult
    # optional: add_product, remove_product, fine_tune, evaluate
```
Start from `medsort/backends/yolo_backend.py` (reference) and `composite.py` (how to wrap models).

## 1. Hard requirements (checked by `medsort/conformance.py`)
| # | Rule |
|---|---|
| R1 | `analyze` accepts a path **or** an HxWx3 uint8 RGB array (`load_image` converts) |
| R2 | Boxes are axis-aligned **pixels of the original image** (not resized/letterboxed), `x1<x2`, `y1<y2`, inside the image |
| R3 | `confidence` in 0..1; `status` is a `Status`; `group` and `label` non-empty |
| R4 | Nothing found = empty `items`, never an exception. Blank and noise images must not crash |
| R5 | Bad input or internal failure raises a `PipelineError` subclass (`DataError`, `BackendError`), never a raw library exception |
| R6 | Deterministic: the same image twice gives the same items |
| R7 | `to_dict()` is JSON-serialisable (use plain floats/strings in `extra`) |
| R8 | Anything you did not implement stays unimplemented and is not in `capabilities()` (calls raise `CapabilityError`). `angle_deg` only if `ORIENTATION` is declared |
| R9 | A model that cannot name an item says so: `label="unknown"`, `status=UNKNOWN`. It never guesses. Below your calibrated threshold use `LOW_CONFIDENCE` |

## 2. Behaviour the project needs (not machine-checked yet)
- **Recall over precision**: a missed item is worse than a spurious box. Default thresholds low, let later stages reject.
- **Overlap**: items legitimately touch and stack. Do not let NMS delete a real neighbour (YOLO: `iou` about 0.6-0.7, or an NMS-free head).
- **Look-alikes** (syringe sizes, glove types): output "unknown" or low confidence rather than a confident wrong label.
- **Medical first**: medical items must win over general objects. The `composite` backend already enforces this; a single model must not trade medical recall for COCO classes.
- **Group + label**: always fill `group` (`config/taxonomy.yaml` groups) and `label` (fine class). If you only know the group, `label = group`.
- **Latency**: no hard budget yet (laptop GPU/CPU). Report your seconds per image.
- **License**: note it. Ultralytics is AGPL-3.0; RF-DETR (Apache-2.0) is the swap-in candidate.

## 3. Optional capabilities
| Capability | Contract |
|---|---|
| `ORIENTATION` | `angle_deg` in degrees, in-plane, document the zero direction and the range |
| `SCALE` | `mm_per_pixel` on the result (from the ArUco markers), `size_mm` per item |
| `RECOGNIZE` | fine labels from embeddings/classifier, with "unknown" rejection |
| `ADD_PRODUCT` | `add_product(label, images)` learns a product from a few photos **without retraining the detector**; `known_products()` must then list it; `remove_product` undoes it |
| `FINE_TUNE` | `fine_tune(TrainRequest) -> TrainReport` (checkpoint, metrics, output dir); write seed, library versions and git commit next to the checkpoint |

## 4. Data you train and evaluate on (`datasets/unified/`)
- `detection/`: YOLO txt `class cx cy w h` (0..1), `train/val/test`, 68 class ids in `classes.yaml` (id, name, group, `in_scope`). Five classes have no boxes yet (hospital set not downloaded).
- `classification/`: folder per class, `train/val/test`; native syringe photos + crops from detection boxes (`manifest.csv` tells which).
- Never evaluate on `train`. Splits already avoid leakage; do not reshuffle them.
- Out-of-scope groups (`person`, `site`, `waste_state`) exist for completeness; drop them with `--exclude-out-of-scope` if they hurt.
- Reserved ids (hospital classes, markers) must keep their ids: append new classes, never reorder.

## 4b. Keeping general knowledge ("other" objects)
A dummy "none of the above" class cannot be trained (it needs examples). Instead:
- known-but-irrelevant objects: run a general model next to the medical one (`composite`: yolov8s COCO, 80 classes), reported as `group="other"`, `source="general"`;
- truly unknown objects: `status=UNKNOWN`.
- Upgrade path if you want ONE model: pseudo-label the training images with the COCO model, add its classes (ids appended after 68), copy the pretrained COCO head rows into the new head, and keep a replay mix. Expect more work and some forgetting.

## 5. What to report for any new model (same table every time)
mAP50-95 and recall@IoU0.5 on `detection/val` and `test`, per source dataset; top-1 on `classification/val`; unknown-rejection rate on a held-out class; seconds/image; the 50 worst crops. Baseline to beat: `yolov8s.pt` fine-tuned with `scripts/train_*.py`.

## 6. Environment
- Verified here: ultralytics 8.4.213, `yolov8s.pt` and `yolo26s.pt` both load (`models/weights/`).
- Torch on this machine is the CPU build. For the RTX 5060 (Blackwell) install a CUDA 12.8 build:
  `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128` (a cp314 wheel exists; or use Python 3.12).
