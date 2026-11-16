"""Dataset handling, independent of any model: acquire (no API key needed),
validate, remap through the taxonomy, write a ready-to-train dataset."""
from __future__ import annotations

import hashlib
import os
import random
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import yaml

from .api import PreparedDataset
from .errors import ConfigError, DataError

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SPLIT_ALIASES = {"train": ("train",), "val": ("valid", "val", "validation"), "test": ("test",)}
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


# --------------------------------------------------------------------------- #
# Acquire: local folder, local zip, URL to a zip, Hugging Face dataset repo.
# Roboflow API is a last, optional route. None of the others need a key.
# --------------------------------------------------------------------------- #

def acquire(source: str, dest: Path) -> Path:
    """Get a YOLO-format export into `dest` and return the folder holding data.yaml."""
    dest = Path(dest)
    if source.startswith("hf:"):
        try:
            from huggingface_hub import snapshot_download
        except ImportError as e:
            raise DataError("pip install huggingface_hub to use hf: sources") from e
        snapshot_download(repo_id=source[3:], repo_type="dataset", local_dir=dest)
    elif source.startswith("roboflow:"):  # roboflow:workspace/project/version, needs ROBOFLOW_API_KEY
        key = os.environ.get("ROBOFLOW_API_KEY")
        if not key:
            raise DataError("roboflow: source needs ROBOFLOW_API_KEY; use a zip/folder instead")
        from roboflow import Roboflow
        ws, proj, ver = source[len("roboflow:"):].split("/")
        Roboflow(api_key=key).workspace(ws).project(proj).version(int(ver)).download("yolov8", location=str(dest))
    elif source.startswith(("http://", "https://")):
        dest.mkdir(parents=True, exist_ok=True)
        zpath = dest / "download.zip"
        urllib.request.urlretrieve(source, zpath)
        _safe_extract(zpath, dest)
        zpath.unlink()
    else:
        p = Path(source)
        if not p.exists():
            raise DataError(f"source not found: {p}")
        if p.is_dir():
            return find_export_root(p)
        _safe_extract(p, dest)
    return find_export_root(dest)


def _safe_extract(zpath: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zpath) as z:
            base = dest.resolve()
            for member in z.namelist():
                if not (base / member).resolve().is_relative_to(base):
                    raise DataError(f"unsafe path in zip {zpath}: {member}")
            z.extractall(dest)
    except zipfile.BadZipFile as e:
        raise DataError(f"not a valid zip: {zpath}") from e


def find_export_root(base: Path) -> Path:
    hits = sorted(base.rglob("data.yaml"), key=lambda p: len(p.parts))
    if not hits:
        raise DataError(f"no data.yaml under {base}: not a YOLO-format export "
                        "(on Roboflow pick 'YOLOv8' / 'YOLO26' format when downloading)")
    return hits[0].parent


# --------------------------------------------------------------------------- #
# Reading and validating one YOLO export
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class LabelRow:
    cls: int
    pts: tuple[float, ...]   # 4 numbers (cx,cy,w,h) for a box, or 2N for a polygon (normalised)

    @property
    def is_polygon(self) -> bool:
        return len(self.pts) > 4

    def as_box(self) -> tuple[float, float, float, float]:
        if not self.is_polygon:
            return self.pts  # type: ignore[return-value]
        xs, ys = self.pts[0::2], self.pts[1::2]
        x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
        return ((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1)


def parse_label_file(path: Path, n_classes: int) -> list[LabelRow]:
    rows = []
    for ln, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split()
        where = f"{path}:{ln}"
        try:
            cls = int(parts[0])
            vals = tuple(float(v) for v in parts[1:])
        except ValueError as e:
            raise DataError(f"{where}: non-numeric value") from e
        if not (0 <= cls < n_classes):
            raise DataError(f"{where}: class id {cls} outside 0..{n_classes - 1}")
        if len(vals) == 4:
            pass
        elif len(vals) >= 6 and len(vals) % 2 == 0:
            pass
        else:
            raise DataError(f"{where}: expected 4 box values or an even polygon of >=6, got {len(vals)}")
        if any(v < -1e-6 or v > 1 + 1e-6 for v in vals):
            raise DataError(f"{where}: coordinates outside the image (not in 0..1)")
        rows.append(LabelRow(cls, vals))
    return rows


@dataclass(frozen=True)
class Sample:
    image: Path
    label: Path


class YoloExport:
    def __init__(self, root: Path, name: str):
        self.root, self.name = Path(root), name
        cfg_path = self.root / "data.yaml"
        if not cfg_path.exists():
            raise DataError(f"missing {cfg_path}")
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        names = cfg.get("names")
        if isinstance(names, dict):
            names = [names[k] for k in sorted(names, key=int)]
        if not names:
            raise DataError(f"{cfg_path}: no 'names'")
        self.names: list[str] = [str(n) for n in names]
        self.dirs: dict[str, tuple[Path, Path]] = {}
        for split, aliases in SPLIT_ALIASES.items():
            for a in aliases:
                for img, lab in ((self.root / a / "images", self.root / a / "labels"),
                                 (self.root / "images" / a, self.root / "labels" / a)):
                    if img.is_dir():
                        self.dirs[split] = (img, lab)
                        break
                if split in self.dirs:
                    break
        if "train" not in self.dirs:
            raise DataError(f"{self.root}: no train/images folder found")

    def samples(self, split: str) -> list[Sample]:
        if split not in self.dirs:
            return []
        img_dir, lab_dir = self.dirs[split]
        out = []
        for p in sorted(img_dir.iterdir()):
            if p.suffix.lower() in IMG_EXT:
                out.append(Sample(p, lab_dir / (p.stem + ".txt")))
        return out

    def validate(self, check_images: bool = True) -> list[str]:
        """Return every problem found (empty list = clean). Each names its file."""
        from PIL import Image
        problems: list[str] = []
        seen: dict[str, Path] = {}
        for split in self.dirs:
            for s in self.samples(split):
                if not s.label.exists():
                    problems.append(f"{s.image}: missing label file {s.label.name}")
                else:
                    try:
                        parse_label_file(s.label, len(self.names))
                    except DataError as e:
                        problems.append(str(e))
                if check_images:
                    try:
                        with Image.open(s.image) as im:
                            im.verify()
                    except Exception as e:  # noqa: BLE001
                        problems.append(f"{s.image}: corrupt image ({e})")
                        continue
                digest = hashlib.md5(s.image.read_bytes()).hexdigest()
                if digest in seen:
                    problems.append(f"{s.image}: byte-identical to {seen[digest]} (possible train/test leakage)")
                else:
                    seen[digest] = s.image
        return problems


# --------------------------------------------------------------------------- #
# Taxonomy
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Taxonomy:
    groups: tuple[str, ...]
    datasets: dict[str, dict[str, tuple[str, str]]]   # dataset -> source class -> (group, fine)
    out_of_scope_groups: tuple[str, ...] = ()

    @classmethod
    def load(cls, path: Path | None = None) -> "Taxonomy":
        path = Path(path or CONFIG_DIR / "taxonomy.yaml")
        raw = yaml.safe_load(path.read_text()) or {}
        groups = tuple(raw.get("groups") or ())
        if not groups:
            raise ConfigError(f"{path}: 'groups' is empty")
        ds: dict[str, dict[str, tuple[str, str]]] = {}
        for dname, mapping in (raw.get("datasets") or {}).items():
            ds[dname] = {}
            for src, tgt in (mapping or {}).items():
                if not isinstance(tgt, dict) or "group" not in tgt or "fine" not in tgt:
                    raise ConfigError(f"{path}: {dname}.{src} needs group and fine")
                if tgt["group"] not in groups:
                    raise ConfigError(f"{path}: {dname}.{src} has unknown group '{tgt['group']}'")
                ds[dname][str(src)] = (tgt["group"], tgt["fine"])
        return cls(groups, ds, tuple(raw.get("out_of_scope_groups") or ()))

    def check(self, dataset: str, export_names: list[str]) -> None:
        """Both directions: every dataset class mapped, every mapped class exists."""
        if dataset not in self.datasets:
            raise ConfigError(f"dataset '{dataset}' not in taxonomy.yaml")
        mapped = set(self.datasets[dataset])
        have = set(export_names)
        if have - mapped:
            raise ConfigError(f"{dataset}: classes in data.yaml but not in taxonomy: {sorted(have - mapped)}")
        if mapped - have:
            raise ConfigError(f"{dataset}: taxonomy lists classes not in data.yaml: {sorted(mapped - have)} "
                              f"(data.yaml has {sorted(have)})")

    def group_of(self, fine: str) -> str:
        for m in self.datasets.values():
            for g, f in m.values():
                if f == fine:
                    return g
        raise ConfigError(f"unknown fine label '{fine}'")

    def class_index(self, target: str) -> list[str]:
        """Global ordered class list, identical across phases so heads stay compatible."""
        if target == "group":
            return list(self.groups)
        if target == "fine":
            return sorted({f for m in self.datasets.values() for _, f in m.values()})
        raise ConfigError(f"target must be 'group' or 'fine', got '{target}'")


# --------------------------------------------------------------------------- #
# Build one training set from one or more exports
# --------------------------------------------------------------------------- #

@dataclass
class SourceSpec:
    name: str                 # key in taxonomy.yaml
    export: YoloExport
    train_fraction: float = 1.0
    use_for_eval: bool = True  # include its val/test splits


def build_training_set(sources: list[SourceSpec], taxonomy: Taxonomy, out_dir: Path,
                       target: str = "group", task: str = "detect", seed: int = 0) -> PreparedDataset:
    if task not in ("detect", "segment"):
        raise ConfigError("task must be detect or segment")
    classes = taxonomy.class_index(target)
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    rng = random.Random(seed)
    counts: dict[str, int] = {}

    for src in sources:
        taxonomy.check(src.name, src.export.names)
        remap = {}
        for i, n in enumerate(src.export.names):
            group, fine = taxonomy.datasets[src.name][n]
            remap[i] = classes.index(group if target == "group" else fine)
        for split in ("train", "val", "test"):
            samples = src.export.samples(split)
            if split != "train" and not src.use_for_eval:
                continue
            if split == "train" and src.train_fraction < 1.0:
                samples = rng.sample(samples, round(len(samples) * src.train_fraction))
            img_out, lab_out = out_dir / split / "images", out_dir / split / "labels"
            img_out.mkdir(parents=True, exist_ok=True)
            lab_out.mkdir(parents=True, exist_ok=True)
            for s in samples:
                rows = parse_label_file(s.label, len(src.export.names)) if s.label.exists() else []
                lines = []
                for r in rows:
                    if task == "segment" and r.is_polygon:
                        coords = " ".join(f"{v:.6f}" for v in r.pts)
                    else:
                        coords = " ".join(f"{v:.6f}" for v in r.as_box())
                    lines.append(f"{remap[r.cls]} {coords}")
                stem = f"{src.name}__{s.image.stem}"
                _link_or_copy(s.image, img_out / (stem + s.image.suffix.lower()))
                (lab_out / (stem + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""))
                counts[split] = counts.get(split, 0) + 1

    if "train" not in counts:
        raise DataError("no training images were written")
    cfg = {"path": str(out_dir.resolve()), "train": "train/images",
           "val": "val/images" if "val" in counts else "train/images",
           "names": {i: n for i, n in enumerate(classes)}}
    if "test" in counts:
        cfg["test"] = "test/images"
    cfg_path = out_dir / "data.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return PreparedDataset(out_dir, cfg_path, tuple(classes), task, counts)


def _link_or_copy(src: Path, dst: Path) -> None:
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)
