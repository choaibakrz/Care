import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from medsort.api import (AnalysisResult, Box, Capability, ItemResult, Status, VisionBackend,
                         create_backend, register_backend)
from medsort.conformance import check_backend
from medsort.errors import DataError
from medsort.api import load_image


class Fixed(VisionBackend):
    def __init__(self, items, name="fixed"):
        self.name, self._items = name, items

    def capabilities(self): return {Capability.DETECT}
    def known_products(self): return sorted({i[1] for i in self._items})

    def analyze(self, image):
        a = load_image(image)
        return AnalysisResult([ItemResult(Box(*b), "pack", lab, c) for b, lab, c in self._items],
                              (a.shape[1], a.shape[0]), self.name)


IMG = np.zeros((100, 100, 3), np.uint8)


def test_composite_medical_wins_and_general_is_tagged():
    med = Fixed([((10, 10, 50, 50), "syringe", 0.9)])
    gen = Fixed([((12, 12, 48, 48), "bottle", 0.9),      # same object -> dropped
                 ((60, 60, 90, 90), "cup", 0.8),         # new -> kept as 'other'
                 ((60, 5, 90, 30), "cup", 0.2),          # too weak -> dropped
                 ((0, 60, 20, 90), "person", 0.9)])      # denied
    comp = create_backend("composite", primary=med, secondary=gen, deny=["person"])
    out = comp.analyze(IMG)
    assert [(i.group, i.label, i.extra["source"]) for i in out.items] == \
           [("pack", "syringe", "medical"), ("other", "cup", "general")]


def test_composite_allow_list_and_exclusive_options():
    gen = Fixed([((60, 60, 90, 90), "cup", 0.8), ((0, 0, 20, 20), "book", 0.8)])
    comp = create_backend("composite", primary=Fixed([]), secondary=gen, allow=["book"])
    assert [i.label for i in comp.analyze(IMG).items] == ["book"]
    with pytest.raises(Exception):
        create_backend("composite", primary=Fixed([]), secondary=gen, allow=["a"], deny=["b"])


def test_conformance_accepts_good_backend_and_rejects_bad_ones():
    assert check_backend(Fixed([((10, 10, 50, 50), "syringe", 0.9)]), IMG) == []
    assert any("outside image" in p for p in check_backend(Fixed([((10, 10, 500, 50), "x", 0.9)]), IMG))
    assert any("confidence" in p for p in check_backend(Fixed([((10, 10, 50, 50), "x", 1.7)]), IMG))

    class Raw(Fixed):
        def analyze(self, image):
            if isinstance(image, str):
                raise FileNotFoundError(image)           # raw exception: must be a PipelineError
            return super().analyze(image)
    assert any("must be a PipelineError" in p for p in check_backend(Raw([]), IMG))
