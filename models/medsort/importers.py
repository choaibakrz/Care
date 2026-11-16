"""One reader per source annotation format. Every reader yields the same
neutral records, so the builder never cares where data came from:

  DetRecord: image path + boxes (source class name, normalised cx,cy,w,h)
  ClsRecord: whole-image label + image bytes
"""
from __future__ import annotations

import io
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .errors import DataError


@dataclass
class DetRecord:
    image: Path
    split: str | None                       # train / val / test, or None = builder decides
    boxes: list[tuple[str, float, float, float, float]]   # (source class, cx, cy, w, h) normalised
    group_key: str = ""                     # for leakage-aware splitting (items of one key stay contiguous)
    declared_size: tuple[int, int] | None = None
    origin: str | None = None               # original photo name, to catch the same photo re-exported


@dataclass
class ClsRecord:
    split: str
    label: str                              # source class name
    data: bytes
    ext: str
    name: str


def _norm(x, y, w, h, W, H):
    return ((x + w / 2) / W, (y + h / 2) / H, w / W, h / H)


# ---------------------------------------------------------------- COCO json
def coco_records(json_path: Path, images_dir: Path, split: str | None) -> Iterator[DetRecord]:
    d = json.loads(Path(json_path).read_text(encoding="utf8"))
    cats = {c["id"]: c["name"] for c in d["categories"]}
    by_img = defaultdict(list)
    for a in d["annotations"]:
        if a.get("iscrowd"):
            continue
        by_img[a["image_id"]].append(a)
    for im in d["images"]:
        W, H = im["width"], im["height"]
        boxes = []
        for a in by_img.get(im["id"], []):
            x, y, w, h = a["bbox"]
            boxes.append((cats[a["category_id"]], *_norm(x, y, w, h, W, H)))
        yield DetRecord(Path(images_dir) / im["file_name"], split, boxes, declared_size=(W, H),
                        origin=(im.get("extra") or {}).get("name"))


def coco_categories(json_path: Path, skip_roboflow_placeholder: bool = False) -> list[str]:
    cats = json.loads(Path(json_path).read_text(encoding="utf8"))["categories"]
    # Roboflow COCO exports add a dummy category id 0 (supercategory "none") that carries no boxes
    return [c["name"] for c in cats
            if not (skip_roboflow_placeholder and c["id"] == 0 and c.get("supercategory") == "none")]


def read_cppe5(root: Path):
    base = Path(root) / "CPPE-5"
    names = set()
    recs = []
    for split in ("train", "test"):
        j = base / "annotations" / f"{split}.json"
        names |= set(coco_categories(j))
        recs += list(coco_records(j, base / "images", split))
    return sorted(names), recs


def read_medbin(root: Path):
    names, recs = set(), []
    for src, split in (("train", "train"), ("valid", "val"), ("test", "test")):
        j = Path(root) / src / "_annotations.coco.json"
        if not j.exists():
            raise DataError(f"{j} missing")
        names |= set(coco_categories(j, skip_roboflow_placeholder=True))
        recs += list(coco_records(j, Path(root) / src, split))
    return sorted(names), recs


# ------------------------------------------------- Roboflow YOLO, no data.yaml
# Order verified by viewing sample crops of every class id (see taxonomy.yaml).
CONSTRUCTION_NAMES = ["Hardhat", "Mask", "NO-Hardhat", "NO-Mask", "NO-Safety Vest",
                      "Person", "Safety Cone", "Safety Vest", "machinery", "vehicle"]


def read_construction(root: Path):
    base = Path(root) / "css-data"
    recs = []
    for src_split, split in (("train", "train"), ("valid", "val"), ("test", "test")):
        img_dir, lab_dir = base / src_split / "images", base / src_split / "labels"
        if not img_dir.is_dir():
            raise DataError(f"{img_dir} missing (zip not fully extracted?)")
        for img in sorted(img_dir.glob("*.jpg")):
            lab = lab_dir / (img.stem + ".txt")
            if not lab.exists():
                raise DataError(f"{img}: no label file")
            boxes = []
            for ln, line in enumerate(lab.read_text().splitlines(), 1):
                p = line.split()
                if not p:
                    continue
                if len(p) != 5:
                    raise DataError(f"{lab}:{ln}: expected 5 values, got {len(p)}")
                k = int(p[0])
                if not 0 <= k < len(CONSTRUCTION_NAMES):
                    raise DataError(f"{lab}:{ln}: class id {k} out of range")
                boxes.append((CONSTRUCTION_NAMES[k], *map(float, p[1:])))
            recs.append(DetRecord(img, split, boxes))
    return list(CONSTRUCTION_NAMES), recs


# ------------------------------------------------------------ Pascal VOC xml
def read_medical_waste(root: Path):
    base = Path(root) / "Medical Waste dataset"
    names, recs = set(), []
    for xml in sorted((base / "annotations" / "xml").glob("*.xml")):
        r = ET.parse(xml).getroot()
        folder, fname = r.findtext("folder"), r.findtext("filename")
        img = base / "images" / folder / fname
        if not img.exists():
            raise DataError(f"{xml}: image {img} not found")
        W, H = int(r.findtext("size/width")), int(r.findtext("size/height"))
        boxes = []
        for o in r.findall("object"):
            n = o.findtext("name")
            bb = o.find("bndbox")
            x1, y1, x2, y2 = (float(bb.findtext(t)) for t in ("xmin", "ymin", "xmax", "ymax"))
            names.add(n)
            boxes.append((n, *_norm(x1, y1, x2 - x1, y2 - y1, W, H)))
        recs.append(DetRecord(img, None, boxes, group_key=folder, declared_size=(W, H)))
    return sorted(names), recs


# ------------------------------------------------- Hugging Face parquet (cls)
def read_syringe(root: Path):
    import pyarrow.parquet as pq
    recs, label = [], "syringe"   # every row is ImageNet class 845 = syringe (checked)
    for src, split in (("train", "train"), ("validation", "val")):
        t = pq.read_table(Path(root) / "data" / f"{src}-00000-of-00001.parquet")
        labels = set(t.column("label").to_pylist())
        if labels != {845}:
            raise DataError(f"{src}: unexpected label ids {labels}, expected only 845")
        from PIL import Image
        for i, row in enumerate(t.column("image").to_pylist()):
            data = row["bytes"]
            with Image.open(io.BytesIO(data)) as im:
                ext = ".jpg" if im.format == "JPEG" else ".png"
            recs.append(ClsRecord(split, label, data, ext, f"imnet1k_syringe__{src}_{i:05d}"))
    return [label], recs
