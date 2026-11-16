"""Phase 1: warm-up on BioSafety PPE (optional, ablate it)."""
from _common import *  # noqa: F401,F403
from medsort.training import run_phase

a = train_parser(__doc__).parse_args()
run_phase("ppe_warmup", a.backend, {"weights": a.weights}, {}, a.target, a.task,
          a.init, overrides(a), a.skip_validation)
