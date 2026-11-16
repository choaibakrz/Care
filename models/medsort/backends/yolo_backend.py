"""Ultralytics YOLO backend. The only module that imports ultralytics.

Detection only: coarse group (or fine label if trained with target=fine).
Orientation / scale / add_product are NOT provided here and say so via
capabilities(); a recognizer or refiner backend can add them later without
touching callers.
"""
from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path
from typing import Any

from ..api import (AnalysisResult, Box, Capability, ImageLike, ItemResult, PreparedDataset,
                   Status, TrainReport, TrainRequest, VisionBackend, load_image, register_backend)
from ..data import Taxonomy
from ..errors import BackendError


@register_backend("yolo")
class YoloBackend(VisionBackend):
    name = "yolo"

    def __init__(self, weights: str = "yolov8s.pt", conf: float = 0.15, iou: float = 0.65,
                 image_size: int = 960, low_conf: float = 0.4, device: str | None = None,
                 taxonomy_path: str | None = None):
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise BackendError("pip install ultralytics") from e
        self.weights, self.conf, self.iou = weights, conf, iou
        self.image_size, self.low_conf, self.device = image_size, low_conf, device
        local = Path(__file__).resolve().parents[2] / "weights" / weights
        if not Path(weights).exists() and local.exists():   # prefer models/weights/<name> over re-downloading
            weights = str(local)
        try:
            self._model = YOLO(weights)
        except Exception as e:  # noqa: BLE001
            raise BackendError(f"cannot load weights '{weights}': {e}") from e
        # fine label -> group, so results always carry a group
        tax = Taxonomy.load(Path(taxonomy_path) if taxonomy_path else None)
        self._fine_to_group = {f: g for m in tax.datasets.values() for g, f in m.values()}
        self._groups = set(tax.groups)

    def capabilities(self) -> set[Capability]:
        return {Capability.DETECT, Capability.FINE_TUNE}

    def known_products(self) -> list[str]:
        return [str(n) for n in self._model.names.values()]

    def analyze(self, image: ImageLike) -> AnalysisResult:
        arr = load_image(image)
        try:
            res = self._model.predict(arr[:, :, ::-1], conf=self.conf, iou=self.iou,  # ultralytics expects BGR arrays
                                      imgsz=self.image_size, device=self.device, verbose=False)[0]
        except Exception as e:  # noqa: BLE001
            raise BackendError(f"yolo inference failed: {e}") from e
        items = []
        for b in res.boxes:
            name = str(self._model.names[int(b.cls)])
            group = name if name in self._groups else self._fine_to_group.get(name, name)
            conf = float(b.conf)
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            items.append(ItemResult(Box(x1, y1, x2, y2), group, name, conf,
                                    Status.OK if conf >= self.low_conf else Status.LOW_CONFIDENCE))
        h, w = arr.shape[:2]
        return AnalysisResult(items, (w, h), self.name)

    def evaluate(self, dataset: PreparedDataset, split: str = "val", **options: Any) -> dict[str, float]:
        m = self._model.val(data=str(dataset.config_path), split=split, imgsz=self.image_size,
                            device=self.device, verbose=False, **options)
        return {"mAP50": float(m.box.map50), "mAP50-95": float(m.box.map),
                "precision": float(m.box.mp), "recall": float(m.box.mr)}

    def fine_tune(self, req: TrainRequest) -> TrainReport:
        from ultralytics import YOLO
        model = YOLO(req.init_from or self.weights)
        args: dict[str, Any] = dict(
            data=str(req.dataset.config_path), epochs=req.epochs, imgsz=req.image_size,
            batch=req.batch_size, freeze=req.freeze_layers or None, seed=req.seed,
            device=req.device, project=str(req.output_dir.parent.resolve()), name=req.output_dir.name,
            exist_ok=True, plots=True)
        if req.learning_rate is not None:
            args["lr0"] = req.learning_rate
        args.update(req.options)
        try:
            results = model.train(**args)
        except Exception as e:  # noqa: BLE001
            raise BackendError(f"yolo training failed: {e}") from e
        best = Path(results.save_dir) / "weights" / "best.pt"
        if not best.exists():
            raise BackendError(f"training finished but {best} is missing")
        metrics = {k: float(v) for k, v in (results.results_dict or {}).items()}
        _write_run_meta(Path(results.save_dir), req, args)
        return TrainReport(best, metrics, Path(results.save_dir))


def _write_run_meta(out: Path, req: TrainRequest, args: dict) -> None:
    import ultralytics
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True,
                                         stderr=subprocess.DEVNULL).strip()
    except Exception:  # noqa: BLE001 - not a git repo is fine
        commit = None
    meta = {"seed": req.seed, "git_commit": commit, "python": platform.python_version(),
            "ultralytics": ultralytics.__version__, "classes": list(req.dataset.class_names),
            "dataset_counts": req.dataset.counts, "train_args": {k: str(v) for k, v in args.items()}}
    try:
        import torch
        meta["torch"] = torch.__version__
    except ImportError:
        pass
    (out / "run_meta.json").write_text(json.dumps(meta, indent=2))
