"""Medical specialist + general detector, merged. Needs no retraining, forgets nothing.

  primary   = the medical model (our fine-tuned detector, or any VisionBackend)
  secondary = a general model that still knows everyday objects (COCO yolov8s.pt)

Special attention to medical items:
  * primary runs with a LOW threshold (recall first), secondary with a HIGH one;
  * wherever both see something, the primary wins: a secondary box that overlaps a
    primary box (IoU or containment) is dropped;
  * secondary results are tagged group="other", extra["source"]="general", so the
    robot can ignore or log them; they never masquerade as medical items.

Config example:
    create_backend("composite",
        primary={"name": "yolo", "weights": "runs/medical/weights/best.pt", "conf": 0.15},
        secondary={"name": "yolo", "weights": "yolov8s.pt", "conf": 0.45},
        deny=["person"])      # general classes to drop (or use allow=[...])
"""
from __future__ import annotations

from typing import Any, Iterable

from ..api import (AnalysisResult, Box, Capability, ImageLike, ItemResult, Status,
                   VisionBackend, create_backend, load_image, register_backend)
from ..errors import ConfigError

OTHER_GROUP = "other"


def _overlap(a: Box, b: Box) -> tuple[float, float]:
    """(IoU, fraction of b covered by a)"""
    ix = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    inter = ix * iy
    area_a = (a.x2 - a.x1) * (a.y2 - a.y1)
    area_b = (b.x2 - b.x1) * (b.y2 - b.y1)
    union = area_a + area_b - inter
    return (inter / union if union else 0.0, inter / area_b if area_b else 0.0)


@register_backend("composite")
class CompositeBackend(VisionBackend):
    name = "composite"

    def __init__(self, primary: dict | VisionBackend, secondary: dict | VisionBackend,
                 allow: Iterable[str] | None = None, deny: Iterable[str] | None = None,
                 iou_suppress: float = 0.5, contain_suppress: float = 0.7,
                 secondary_min_conf: float = 0.45):
        if allow and deny:
            raise ConfigError("use allow or deny, not both")
        self.primary = primary if isinstance(primary, VisionBackend) else _make(primary)
        self.secondary = secondary if isinstance(secondary, VisionBackend) else _make(secondary)
        self.allow, self.deny = set(allow or ()), set(deny or ())
        self.iou_suppress, self.contain_suppress = iou_suppress, contain_suppress
        self.secondary_min_conf = secondary_min_conf

    def capabilities(self) -> set[Capability]:
        return self.primary.capabilities() | {Capability.DETECT}

    def known_products(self) -> list[str]:
        return self.primary.known_products()

    def analyze(self, image: ImageLike) -> AnalysisResult:
        arr = load_image(image)                      # decode once, share
        med = self.primary.analyze(arr)
        gen = self.secondary.analyze(arr)
        items = list(med.items)
        dropped = 0
        for it in gen.items:
            if it.confidence < self.secondary_min_conf:
                continue
            if (self.allow and it.label not in self.allow) or it.label in self.deny:
                continue
            if any(_covered(m.box, it.box, self.iou_suppress, self.contain_suppress) for m in med.items):
                dropped += 1
                continue
            items.append(ItemResult(it.box, OTHER_GROUP, it.label, it.confidence, it.status,
                                    extra={**it.extra, "source": "general"}))
        for it in items[: len(med.items)]:
            it.extra.setdefault("source", "medical")
        warnings = med.warnings + gen.warnings
        return AnalysisResult(items, med.image_size, self.name, med.mm_per_pixel, med.status, warnings)

    # training goes to the medical model only: the general one stays untouched on purpose
    def fine_tune(self, request):
        return self.primary.fine_tune(request)

    def evaluate(self, dataset, split="val", **options):
        return self.primary.evaluate(dataset, split, **options)

    def add_product(self, label, images):
        return self.primary.add_product(label, images)

    def remove_product(self, label):
        return self.primary.remove_product(label)


def _covered(m: Box, g: Box, iou_t: float, contain_t: float) -> bool:
    iou, frac_g_inside_m = _overlap(m, g)
    return iou >= iou_t or frac_g_inside_m >= contain_t


def _make(cfg: dict[str, Any]) -> VisionBackend:
    cfg = dict(cfg)
    try:
        name = cfg.pop("name")
    except KeyError as e:
        raise ConfigError("backend config needs a 'name'") from e
    return create_backend(name, **cfg)
