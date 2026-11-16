"""Turn the raw downloads into ONE consistent layout (image sizes untouched).

  datasets/unified/
    classes.yaml                 id -> fine name -> group (+ in_scope flag)
    detection/{train,val,test}/{images,labels}/   YOLO txt: `class cx cy w h` (0..1), unified fine ids
    detection/data.yaml          ready for any YOLO-style trainer
    classification/{train,val}/<fine_class>/*.jpg   whole-image labels (folder per class)
    manifest.csv                 every file written, its source dataset and split

Usage:  python scripts/build_unified.py [--dataset NAME ...] [--exclude-out-of-scope]
"""
import argparse
import csv
import hashlib
import os
import random
import shutil
import sys
from collections import Counter
from pathlib import Path

import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from medsort import importers as imp                      # noqa: E402
from medsort.data import Taxonomy                         # noqa: E402
from medsort.errors import PipelineError                  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW, OUT = ROOT / "datasets" / "raw", ROOT / "datasets" / "unified"

# name -> (kind, raw folder, reader)
SOURCES = {
    "cppe5": ("detection", "cppe-5", imp.read_cppe5),
    "construction_site_safety": ("detection", "construction-site-safety-image-dataset-roboflow", imp.read_construction),
    "medical_waste": ("detection", "medical-waste-dataset-annotated", imp.read_medical_waste),
    "syringe_imagenet": ("classification", "imnet1k_syringe", imp.read_syringe),
    "medbin": ("detection", "medbin", imp.read_medbin),   # manual Roboflow zip, see datasets/README.md
}
# skaarface/medical-personal-protective-equipment-images is byte-identical to cppe-5 (same json md5): not imported twice.


def link_or_copy(src: Path, dst: Path):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def assign_splits(recs, seed=0):
    """Fill missing splits. Sources with none (medical waste) are split in contiguous
    blocks per class folder, ordered by file name (= timestamp), 80/10/10: consecutive
    frames of one scene stay together, which avoids train/test leakage.
    Sources with only train/test get 10% of train as val (seeded)."""
    if all(r.split is None for r in recs):
        groups = {}
        for r in recs:
            groups.setdefault(r.group_key, []).append(r)
        for g in groups.values():
            g.sort(key=lambda r: r.image.name)
            n = len(g)
            for i, r in enumerate(g):
                r.split = "train" if i < n * 0.8 else "val" if i < n * 0.9 else "test"
    elif not any(r.split == "val" for r in recs):
        train = [r for r in recs if r.split == "train"]
        for r in random.Random(seed).sample(train, round(len(train) * 0.1)):
            r.split = "val"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", nargs="*", choices=list(SOURCES), default=list(SOURCES))
    ap.add_argument("--exclude-out-of-scope", action="store_true",
                    help="drop classes in out_of_scope_groups (person, site) from the output")
    ap.add_argument("--crops-per-class", type=int, default=300,
                    help="also cut classification crops out of detection boxes: max N train crops per class "
                         "(val/test get N/4). 0 = no crops")
    ap.add_argument("--min-crop-px", type=int, default=48, help="skip boxes whose short side is below this")
    a = ap.parse_args()

    tax = Taxonomy.load()
    fine_all = tax.class_index("fine")
    skip_fine = {f for m in tax.datasets.values() for g, f in m.values() if a.exclude_out_of_scope and g in tax.out_of_scope_groups}
    classes = [f for f in fine_all if f not in skip_fine]
    cid = {f: i for i, f in enumerate(classes)}

    if OUT.exists():
        shutil.rmtree(OUT)
    manifest, det_counts, cls_counts = [], Counter(), Counter()
    inst = Counter()
    crop_cands = []   # (split, fine, image, x1,y1,x2,y2 in px, stem)
    warnings = Counter()

    for name in a.dataset:
        kind, folder, reader = SOURCES[name]
        raw = RAW / folder
        if not raw.exists():
            print(f"[skip] {name}: {raw} not downloaded")
            continue
        src_names, recs = reader(raw)
        tax.check(name, src_names)                      # both directions, fails loudly
        mapping = tax.datasets[name]

        if kind == "classification":
            for r in recs:
                fine = mapping[r.label][1]
                d = OUT / "classification" / r.split / fine
                d.mkdir(parents=True, exist_ok=True)
                (d / (r.name + r.ext)).write_bytes(r.data)
                manifest.append((name, "classification", r.split, fine, str((d / (r.name + r.ext)).relative_to(OUT))))
                cls_counts[(r.split, fine)] += 1
            continue

        assign_splits(recs)
        # Byte-identical images (cppe-5 has some, even between its train and test) would leak into
        # evaluation. Keep one copy, priority train > val > test.
        rank = {"train": 0, "val": 1, "test": 2}
        recs.sort(key=lambda r: rank[r.split])
        seen, seen_origin = {}, {}
        kept = []
        for r in recs:
            if not r.image.exists():
                raise PipelineError(f"{r.image}: listed in annotations but missing")
            h = hashlib.md5(r.image.read_bytes()).hexdigest()
            if h in seen:
                warnings[f"{name}: duplicate image dropped ({r.split}, same as a {seen[h]} image)"] += 1
                continue
            if r.origin and r.origin in seen_origin and seen_origin[r.origin] != r.split:
                # same original photo re-exported under another file name, in another split
                warnings[f"{name}: same-photo-in-two-splits dropped ({r.split}, also in {seen_origin[r.origin]})"] += 1
                continue
            seen[h] = r.split
            if r.origin:
                seen_origin[r.origin] = r.split
            kept.append(r)
        for r in kept:
            if not r.image.exists():
                raise PipelineError(f"{r.image}: listed in annotations but missing")
            with Image.open(r.image) as im:
                W, H = im.size
            # Pixel boxes were divided by the size declared in the annotation file. In cppe-5 that
            # size is wrong for 48 images (boxes are in REAL pixels), so rescale to the real size.
            sx = sy = 1.0
            if r.declared_size and r.declared_size != (W, H):
                sx, sy = r.declared_size[0] / W, r.declared_size[1] / H
                warnings[f"{name}: declared size != real size, boxes rescaled to real size"] += 1
            lines = []
            for src_cls, cx, cy, w, h in r.boxes:
                cx, w, cy, h = cx * sx, w * sx, cy * sy, h * sy
                group, fine = mapping[src_cls]
                if fine in skip_fine:
                    continue
                x1, y1, x2, y2 = max(0, cx - w / 2), max(0, cy - h / 2), min(1, cx + w / 2), min(1, cy + h / 2)
                if x2 - x1 < 1e-3 or y2 - y1 < 1e-3:
                    warnings[f"{name}: degenerate box dropped"] += 1
                    continue
                if (x1, y1, x2, y2) != (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2):
                    warnings[f"{name}: box clipped to image"] += 1
                lines.append(f"{cid[fine]} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}")
                inst[fine] += 1
                if group not in tax.out_of_scope_groups:
                    crop_cands.append((r.split, fine, r.image, x1 * W, y1 * H, x2 * W, y2 * H, f"{name}__{r.image.stem}"))
            stem = f"{name}__{r.image.stem}"
            ext = r.image.suffix.lower()
            idir, ldir = OUT / "detection" / r.split / "images", OUT / "detection" / r.split / "labels"
            idir.mkdir(parents=True, exist_ok=True)
            ldir.mkdir(parents=True, exist_ok=True)
            link_or_copy(r.image, idir / (stem + ext))
            (ldir / (stem + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""))
            manifest.append((name, "detection", r.split, "", f"detection/{r.split}/images/{stem}{ext}"))
            det_counts[(name, r.split)] += 1

    # ---- classification crops cut from detection boxes (same split as the parent image => no leakage)
    crops_written = Counter()
    if a.crops_per_class > 0 and crop_cands:
        rng = random.Random(0)
        small = Counter()
        by_key = {}
        for c in crop_cands:
            if min(c[5] - c[3], c[6] - c[4]) < a.min_crop_px:
                small[c[1]] += 1
                continue
            by_key.setdefault((c[0], c[1]), []).append(c)
        by_img = {}
        for (split, fine), items in by_key.items():
            cap = a.crops_per_class if split == "train" else max(1, a.crops_per_class // 4)
            for k, c in enumerate(rng.sample(items, min(cap, len(items)))):
                by_img.setdefault(c[2], []).append((k, c))
        for img_path, items in by_img.items():
            with Image.open(img_path) as im:
                im = im.convert("RGB")
                W, H = im.size
                for j, (_, (split, fine, _p, x1, y1, x2, y2, stem)) in enumerate(items):
                    pw, ph = 0.08 * (x2 - x1), 0.08 * (y2 - y1)         # a little context around the box
                    box = (max(0, int(x1 - pw)), max(0, int(y1 - ph)), min(W, int(x2 + pw)), min(H, int(y2 + ph)))
                    d = OUT / "classification" / split / fine
                    d.mkdir(parents=True, exist_ok=True)
                    out = d / f"{stem}__c{j}.jpg"
                    im.crop(box).save(out, quality=95)
                    manifest.append((stem.split("__")[0], "classification_crop", split, fine, str(out.relative_to(OUT))))
                    cls_counts[(split, fine)] += 1
                    crops_written[fine] += 1
        for f, n in small.items():
            warnings[f"crops: {f}: boxes under {a.min_crop_px}px skipped"] += n

    # ---- metadata
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "classes.yaml").write_text(yaml.safe_dump({
        "classes": [{"id": i, "name": f, "group": tax.group_of(f),
                     "in_scope": tax.group_of(f) not in tax.out_of_scope_groups} for i, f in enumerate(classes)]},
        sort_keys=False))
    if (OUT / "detection").exists():
        (OUT / "detection" / "data.yaml").write_text(yaml.safe_dump({
            "path": str((OUT / "detection").resolve()), "train": "train/images", "val": "val/images",
            "test": "test/images", "names": dict(enumerate(classes))}, sort_keys=False))
    with open(OUT / "manifest.csv", "w", newline="") as fh:
        csv.writer(fh).writerows([("source", "kind", "split", "label", "path"), *manifest])

    print("\nDETECTION images per source/split:")
    for k in sorted(det_counts):
        print(f"  {k[0]:26s} {k[1]:5s} {det_counts[k]}")
    print("DETECTION boxes per class:")
    for f in classes:
        if inst[f]:
            print(f"  {f:22s} {inst[f]}")
    print("CLASSIFICATION images per split/class:")
    for k in sorted(cls_counts, key=lambda k: (k[1], k[0])):
        print(f"  {k[1]:24s} {k[0]:5s} {cls_counts[k]}")
    for w, n in warnings.items():
        print(f"[warn] {w}: {n}")


if __name__ == "__main__":
    try:
        main()
    except PipelineError as e:
        sys.exit(f"error: {e}")
