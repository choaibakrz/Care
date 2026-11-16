import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from medsort.api import (AnalysisResult, Box, Capability, ItemResult, VisionBackend,
                         create_backend, register_backend)
from medsort.data import SourceSpec, Taxonomy, YoloExport, build_training_set, parse_label_file
from medsort.errors import BackendError, CapabilityError, ConfigError, DataError

NAMES = ["bandage", "syringe", "box-of-gloves", "box-of-masks", "dressing-tray", "square", "triangle"]


def make_export(root: Path, names=NAMES, n=4, bad_label=None):
    (root).mkdir(parents=True)
    (root / "data.yaml").write_text(yaml.safe_dump({"names": names}))
    k = 0
    for split in ("train", "valid"):
        (root / split / "images").mkdir(parents=True)
        (root / split / "labels").mkdir(parents=True)
        for i in range(n):
            k += 1
            Image.fromarray(np.full((32, 32, 3), k * 7 % 255, np.uint8)).save(root / split / "images" / f"{k}.jpg")
            (root / split / "labels" / f"{k}.txt").write_text(f"0 0.5 0.5 0.2 0.2\n{min(5, len(names) - 1)} 0.3 0.3 0.1 0.1\n")
    if bad_label:
        (root / "train" / "labels" / "1.txt").write_text(bad_label)
    return root


def test_clean_export_validates(tmp_path):
    assert YoloExport(make_export(tmp_path / "e"), "hospital_consumables").validate() == []


@pytest.mark.parametrize("bad", ["9 0.5 0.5 0.1 0.1\n", "0 1.5 0.5 0.1 0.1\n", "0 0.5 0.5\n"])
def test_bad_labels_name_the_file(tmp_path, bad):
    exp = YoloExport(make_export(tmp_path / "e", bad_label=bad), "x")
    problems = exp.validate()
    assert problems and "1.txt" in problems[0]


def test_missing_label_and_corrupt_image(tmp_path):
    root = make_export(tmp_path / "e")
    (root / "train" / "labels" / "2.txt").unlink()
    (root / "train" / "images" / "3.jpg").write_bytes(b"not an image")
    text = "\n".join(YoloExport(root, "x").validate())
    assert "2.jpg" in text and "3.jpg" in text


def test_duplicate_across_splits_flagged(tmp_path):
    root = make_export(tmp_path / "e")
    (root / "valid" / "images" / "5.jpg").write_bytes((root / "train" / "images" / "1.jpg").read_bytes())
    assert any("identical" in p for p in YoloExport(root, "x").validate())


def test_taxonomy_both_directions(tmp_path):
    tax = Taxonomy.load()
    tax.check("hospital_consumables", NAMES)
    with pytest.raises(ConfigError):
        tax.check("hospital_consumables", NAMES + ["extra"])
    with pytest.raises(ConfigError):
        tax.check("hospital_consumables", NAMES[:-1])
    with pytest.raises(ConfigError):
        tax.check("nope", NAMES)


def test_build_remaps_to_groups_and_replays(tmp_path):
    a = YoloExport(make_export(tmp_path / "a"), "hospital_consumables")
    b = YoloExport(make_export(tmp_path / "b", names=["mask", "gloves", "goggles"], n=8), "biosafety_ppe")
    tax = Taxonomy.load()
    ds = build_training_set([SourceSpec("hospital_consumables", a),
                             SourceSpec("biosafety_ppe", b, train_fraction=0.5, use_for_eval=False)],
                            tax, tmp_path / "out")
    assert ds.class_names == ("marker", "pack", "box", "tray", "ppe", "person", "site", "waste_state")
    assert ds.counts["train"] == 4 + 4 and ds.counts["val"] == 4      # replay only in train
    lab = next((tmp_path / "out/train/labels").glob("hospital_consumables__1.txt")).read_text().split("\n")
    assert lab[0].startswith("1 ") and lab[1].startswith("0 ")        # bandage->pack(1), square->marker(0)
    cfg = yaml.safe_load((tmp_path / "out/data.yaml").read_text())
    assert cfg["names"][4] == "ppe"


def test_polygon_becomes_box_for_detect():
    p = Path("poly.txt")
    p.write_text("0 0.1 0.1 0.5 0.1 0.5 0.3\n")
    try:
        row = parse_label_file(p, 3)[0]
        assert row.is_polygon and row.as_box() == pytest.approx((0.3, 0.2, 0.4, 0.2))
    finally:
        p.unlink()


def test_backend_swap_without_caller_change():
    @register_backend("dummy")
    class Dummy(VisionBackend):
        name = "dummy"
        def capabilities(self): return {Capability.DETECT}
        def known_products(self): return ["pack"]
        def analyze(self, image):
            return AnalysisResult([ItemResult(Box(0, 0, 5, 5), "pack", "pack", 0.9)], (32, 32), self.name)

    v = create_backend("dummy")
    out = v.analyze(np.zeros((32, 32, 3), np.uint8)).to_dict()
    assert out["items"][0]["status"] == "ok" and out["backend"] == "dummy"
    with pytest.raises(CapabilityError):
        v.add_product("x", [])
    with pytest.raises(BackendError):
        create_backend("does-not-exist")


def test_assign_splits_blocks_and_val_carving():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from build_unified import assign_splits
    from medsort.importers import DetRecord
    recs = [DetRecord(Path(f"{i:03d}.jpg"), None, [], group_key="a") for i in range(10)]
    assign_splits(recs)
    assert [r.split for r in recs] == ["train"] * 8 + ["val", "test"]      # contiguous, no shuffling
    recs = [DetRecord(Path(f"{i}.jpg"), "train" if i < 20 else "test", []) for i in range(30)]
    assign_splits(recs)
    assert sum(r.split == "val" for r in recs) == 2 and sum(r.split == "test" for r in recs) == 10
