"""Executable form of ARCHITECTURE_REQUIREMENTS.md. Any backend must pass:

    from medsort.api import create_backend
    from medsort.conformance import check_backend
    problems = check_backend(create_backend("mine", ...), "some_photo.jpg")
    assert not problems, problems

or from the shell:  python scripts/check_backend.py mine --image photo.jpg --config '{"weights": "x.pt"}'
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from .api import (AnalysisResult, Capability, ImageLike, Status, VisionBackend, load_image)
from .errors import CapabilityError, PipelineError


def check_backend(backend: VisionBackend, image: ImageLike, tol_px: float = 1.5) -> list[str]:
    """Return a list of violations (empty = conforms)."""
    bad: list[str] = []

    def fail(msg: str):
        bad.append(msg)

    if not isinstance(backend, VisionBackend):
        return ["not a VisionBackend subclass"]
    caps = backend.capabilities()
    if not caps or not all(isinstance(c, Capability) for c in caps):
        fail("capabilities() must return a non-empty set of Capability")
    if Capability.DETECT not in caps:
        fail("every backend must support Capability.DETECT")
    products = backend.known_products()
    if not isinstance(products, list) or not all(isinstance(p, str) for p in products):
        fail("known_products() must return list[str]")
    if not isinstance(backend.health(), dict):
        fail("health() must return a dict")

    arr = load_image(image)
    h, w = arr.shape[:2]
    res_arr = _run(backend, arr, "ndarray input", fail)
    res_path = _run(backend, image, "path input", fail) if not isinstance(image, np.ndarray) else None

    for tag, res in (("ndarray", res_arr), ("path", res_path)):
        if res is None:
            continue
        if res.image_size != (w, h):
            fail(f"{tag}: image_size {res.image_size} != (width,height) {(w, h)}")
        for i, it in enumerate(res.items):
            where = f"{tag} item {i}"
            b = it.box
            if not (b.x1 < b.x2 and b.y1 < b.y2):
                fail(f"{where}: degenerate box {b}")
            if b.x1 < -tol_px or b.y1 < -tol_px or b.x2 > w + tol_px or b.y2 > h + tol_px:
                fail(f"{where}: box outside image (pixel coordinates of the ORIGINAL image expected): {b}")
            if not (0.0 <= it.confidence <= 1.0):
                fail(f"{where}: confidence {it.confidence} not in [0,1]")
            if not isinstance(it.status, Status):
                fail(f"{where}: status must be a Status")
            if not it.group or not it.label:
                fail(f"{where}: group and label must be non-empty")
            if it.angle_deg is not None and not math.isfinite(it.angle_deg):
                fail(f"{where}: angle_deg not finite")
            if it.status == Status.UNKNOWN and it.label != "unknown":
                fail(f"{where}: status UNKNOWN requires label 'unknown'")
            if it.angle_deg is not None and Capability.ORIENTATION not in caps:
                fail(f"{where}: angle_deg set but ORIENTATION not declared")
        try:
            json.dumps(res.to_dict())
        except Exception as e:  # noqa: BLE001
            fail(f"{tag}: to_dict() not JSON-serialisable: {e}")

    # determinism
    again = _run(backend, arr, "second call", fail)
    if res_arr and again:
        a = [(i.label, round(i.box.x1), round(i.box.y1)) for i in res_arr.items]
        b = [(i.label, round(i.box.x1), round(i.box.y1)) for i in again.items]
        if sorted(a) != sorted(b):
            fail("not deterministic: two calls on the same image differ")

    # robustness: blank and noise images must not raise
    rng = np.random.default_rng(0)
    for tag, img in (("blank", np.zeros((h, w, 3), np.uint8)),
                     ("noise", rng.integers(0, 255, (h, w, 3), dtype=np.uint8))):
        _run(backend, img, f"{tag} image", fail)

    # errors must be PipelineError, never a raw library exception
    for tag, bad_in in (("missing file", "does_not_exist.jpg"), ("float array", np.zeros((8, 8, 3), np.float32))):
        try:
            backend.analyze(bad_in)
            fail(f"{tag}: should raise a PipelineError")
        except PipelineError:
            pass
        except Exception as e:  # noqa: BLE001
            fail(f"{tag}: raised {type(e).__name__}, must be a PipelineError")

    # undeclared capabilities must say so cleanly
    if Capability.ADD_PRODUCT not in caps:
        try:
            backend.add_product("x", [arr])
            fail("add_product not declared yet did not raise CapabilityError")
        except CapabilityError:
            pass
        except Exception as e:  # noqa: BLE001
            fail(f"add_product raised {type(e).__name__}, expected CapabilityError")
    return bad


def _run(backend: VisionBackend, img, tag: str, fail) -> AnalysisResult | None:
    try:
        res = backend.analyze(img)
    except Exception as e:  # noqa: BLE001
        fail(f"{tag}: analyze raised {type(e).__name__}: {e}")
        return None
    if not isinstance(res, AnalysisResult):
        fail(f"{tag}: analyze must return AnalysisResult")
        return None
    if not isinstance(res.items, list):
        fail(f"{tag}: items must be a list")
        return None
    return res
