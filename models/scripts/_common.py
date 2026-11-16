import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `medsort` importable


def train_parser(desc: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=desc)
    p.add_argument("--backend", default="yolo", help="registered backend name (default: yolo)")
    p.add_argument("--weights", default="yolov8s.pt", help="pretrained weights for the backend")
    p.add_argument("--init", default=None, help="checkpoint to start from (e.g. runs/ppe_warmup/weights/best.pt)")
    p.add_argument("--target", default="group", choices=["group", "fine"])
    p.add_argument("--task", default="detect", choices=["detect", "segment"])
    p.add_argument("--epochs", type=int, default=None)
    p.add_argument("--imgsz", type=int, default=None)
    p.add_argument("--batch", type=int, default=None)
    p.add_argument("--device", default=None)
    p.add_argument("--skip-validation", action="store_true")
    return p


def overrides(a) -> dict:
    o = {}
    if a.epochs is not None: o["epochs"] = a.epochs
    if a.imgsz is not None: o["image_size"] = a.imgsz
    if a.batch is not None: o["batch_size"] = a.batch
    if a.device is not None: o["device"] = a.device
    return o
