"""The ONLY file the rest of the project needs to import.

It defines what a vision system can do (analyze an image, learn a product,
fine-tune) without saying anything about *how*. Concrete models live in
`medsort/backends/` and register themselves under a name:

    from medsort.api import create_backend
    vision = create_backend("yolo", weights="runs/hospital/best.pt")
    result = vision.analyze("drawer.jpg")

Swapping the model = changing the backend name/config. Callers do not change.
"""
from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Union

import numpy as np

from .errors import BackendError, CapabilityError, DataError

# --------------------------------------------------------------------------- #
# Data types (plain, serialisable: this is the "JSON out" of the service)
# --------------------------------------------------------------------------- #

ImageLike = Union[str, Path, np.ndarray]  # path, or HxWx3 uint8 RGB array


class Status(str, Enum):
    OK = "ok"
    UNKNOWN = "unknown"            # item found, but not recognised: never guess
    LOW_CONFIDENCE = "low_confidence"
    ERROR = "error"


class Capability(str, Enum):
    DETECT = "detect"              # finds items + coarse group
    RECOGNIZE = "recognize"        # names items finely (or says unknown)
    ORIENTATION = "orientation"    # fills angle_deg
    SCALE = "scale"                # fills mm_per_pixel / size_mm
    ADD_PRODUCT = "add_product"    # learn a new product from photos, no retrain
    FINE_TUNE = "fine_tune"


@dataclass(frozen=True)
class Box:
    """Axis-aligned box in pixels, x1<x2, y1<y2."""
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)

    @property
    def size(self) -> tuple[float, float]:
        return (self.x2 - self.x1, self.y2 - self.y1)


@dataclass
class ItemResult:
    box: Box
    group: str                       # coarse: marker | pack | box | tray | ppe
    label: str                       # fine name, or == group if the model can't name finer, or "unknown"
    confidence: float                # 0..1
    status: Status = Status.OK
    angle_deg: float | None = None   # in-plane rotation, None if the backend can't tell
    size_mm: tuple[float, float] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    items: list[ItemResult]
    image_size: tuple[int, int]      # (width, height)
    backend: str
    mm_per_pixel: float | None = None
    status: Status = Status.OK
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return _jsonable(asdict(self))


def _jsonable(o):
    if isinstance(o, Enum):
        return o.value
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    return o


@dataclass(frozen=True)
class PreparedDataset:
    """What training scripts hand to a backend: a ready, validated dataset."""
    root: Path
    config_path: Path                # backend-readable description (YOLO data.yaml)
    class_names: tuple[str, ...]
    task: str                        # "detect" | "segment"
    counts: dict[str, int]           # images per split


@dataclass
class TrainRequest:
    dataset: PreparedDataset
    output_dir: Path
    init_from: str | None = None     # checkpoint or pretrained name; None = backend default
    epochs: int = 100
    image_size: int = 640
    batch_size: int = -1             # -1 = backend picks
    learning_rate: float | None = None
    freeze_layers: int = 0
    seed: int = 0
    device: str | None = None        # None = auto
    # anything backend-specific (augmentation, patience...) goes here untouched
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrainReport:
    checkpoint: Path
    metrics: dict[str, float]
    output_dir: Path


# --------------------------------------------------------------------------- #
# The abstract system
# --------------------------------------------------------------------------- #

class VisionBackend(ABC):
    """Everything robot code is allowed to call. Subclass this to add a model."""

    name: str = "abstract"

    # ---- must implement ---------------------------------------------------
    @abstractmethod
    def capabilities(self) -> set[Capability]: ...

    @abstractmethod
    def analyze(self, image: ImageLike) -> AnalysisResult:
        """Find and name every item. Must not raise on 'nothing found'
        (return empty items); raise BackendError only for real failures."""

    @abstractmethod
    def known_products(self) -> list[str]:
        """Fine labels this backend can currently output."""

    # ---- optional: default = clear 'not supported' ------------------------
    def add_product(self, label: str, images: Iterable[ImageLike]) -> None:
        raise CapabilityError(f"{self.name}: add_product not supported")

    def remove_product(self, label: str) -> None:
        raise CapabilityError(f"{self.name}: remove_product not supported")

    def fine_tune(self, request: TrainRequest) -> TrainReport:
        raise CapabilityError(f"{self.name}: fine_tune not supported")

    def evaluate(self, dataset: PreparedDataset, split: str = "val",
                 **options: Any) -> dict[str, float]:
        raise CapabilityError(f"{self.name}: evaluate not supported")

    def health(self) -> dict[str, Any]:
        return {"backend": self.name, "capabilities": sorted(c.value for c in self.capabilities())}

    # ---- helpers ----------------------------------------------------------
    def supports(self, cap: Capability) -> bool:
        return cap in self.capabilities()


# --------------------------------------------------------------------------- #
# Registry: backends are chosen by name, so callers never import a model class
# --------------------------------------------------------------------------- #

_REGISTRY: dict[str, Callable[..., VisionBackend]] = {}
# name -> module that registers it, imported lazily so heavy libs load only if used
_BUILTIN = {"yolo": "medsort.backends.yolo_backend", "composite": "medsort.backends.composite"}


def register_backend(name: str):
    def deco(factory):
        _REGISTRY[name] = factory
        return factory
    return deco


def create_backend(name: str, **config: Any) -> VisionBackend:
    if name not in _REGISTRY and name in _BUILTIN:
        importlib.import_module(_BUILTIN[name])
    if name not in _REGISTRY:
        raise BackendError(f"unknown backend '{name}'. known: {sorted(set(_REGISTRY) | set(_BUILTIN))}")
    return _REGISTRY[name](**config)


def load_image(image: ImageLike) -> np.ndarray:
    """Any accepted input -> HxWx3 uint8 RGB. Raises DataError on bad input."""
    if isinstance(image, np.ndarray):
        if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
            raise DataError(f"expected HxWx3 uint8 array, got {image.shape} {image.dtype}")
        return image
    from PIL import Image
    try:
        with Image.open(image) as im:
            return np.asarray(im.convert("RGB"))
    except Exception as e:  # noqa: BLE001 - re-raised with the file name
        raise DataError(f"cannot read image {image}: {e}") from e
