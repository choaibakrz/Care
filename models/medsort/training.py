"""Backend-agnostic phase runner used by the scripts. Knows datasets and
phases, not models: it only talks to `VisionBackend`."""
from __future__ import annotations

from pathlib import Path

import yaml

from .api import TrainReport, TrainRequest, create_backend
from .data import CONFIG_DIR, SourceSpec, Taxonomy, YoloExport, acquire, build_training_set
from .errors import ConfigError, DataError

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
BUILT_DIR = ROOT / "data" / "built"
RUNS_DIR = ROOT / "runs"


def load_phases() -> dict:
    return yaml.safe_load((CONFIG_DIR / "phases.yaml").read_text())


def get_export(dataset: str, source: str | None = None) -> YoloExport:
    """Use `source` if given, else reuse an earlier download in data/raw/<dataset>."""
    dest = RAW_DIR / dataset
    if source is None:
        source = (load_phases().get("datasets", {}).get(dataset) or {}).get("source")
    if source:
        root = acquire(source, dest)
    elif dest.exists():
        root = acquire(str(dest), dest)
    else:
        raise DataError(
            f"no data for '{dataset}'. Download the YOLO-format zip from Roboflow Universe "
            f"(no API key needed in the web UI) and run:\n"
            f"  python scripts/fetch_dataset.py {dataset} --source <path-or-url-or-hf:repo>")
    return YoloExport(root, dataset)


def run_phase(phase: str, backend: str, backend_config: dict, sources: dict[str, str | None],
              target: str = "group", task: str = "detect", init_from: str | None = None,
              overrides: dict | None = None, skip_validation: bool = False) -> TrainReport:
    phases = load_phases()["phases"]
    if phase not in phases:
        raise ConfigError(f"unknown phase '{phase}', known: {sorted(phases)}")
    cfg = {**phases[phase], **(overrides or {})}
    tax = Taxonomy.load()

    specs = []
    wanted = [(cfg["primary"], 1.0, True)] + [(n, f, False) for n, f in (cfg.get("replay") or {}).items()]
    for name, frac, eval_flag in wanted:
        try:
            exp = get_export(name, sources.get(name))
        except DataError:
            if eval_flag:
                raise          # the primary dataset is mandatory
            print(f"[warn] replay dataset '{name}' unavailable, continuing without it")
            continue
        if not skip_validation:
            problems = exp.validate()
            if problems:
                shown = "\n  ".join(problems[:20])
                raise DataError(f"{name}: {len(problems)} problem(s):\n  {shown}"
                                + ("\n  ..." if len(problems) > 20 else ""))
        specs.append(SourceSpec(name, exp, frac, eval_flag))

    built = build_training_set(specs, tax, BUILT_DIR / phase, target=target, task=task,
                               seed=cfg.get("seed", 0))
    print(f"[data] {phase}: {built.counts} classes={list(built.class_names)}")

    be = create_backend(backend, **backend_config)
    req = TrainRequest(
        dataset=built, output_dir=RUNS_DIR / phase, init_from=init_from,
        epochs=cfg.get("epochs", 100), image_size=cfg.get("image_size", 640),
        batch_size=cfg.get("batch_size", -1), learning_rate=cfg.get("learning_rate"),
        freeze_layers=cfg.get("freeze_layers", 0), seed=cfg.get("seed", 0),
        device=cfg.get("device"), options=cfg.get("options", {}))
    report = be.fine_tune(req)
    print(f"[done] checkpoint: {report.checkpoint}")
    return report
