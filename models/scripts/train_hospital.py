"""Phase 2: main fit on Hospital Consumables (+ PPE replay if downloaded)."""
from _common import *  # noqa: F401,F403
from medsort.training import run_phase

a = train_parser(__doc__).parse_args()
run_phase("hospital_main", a.backend, {"weights": a.weights}, {}, a.target, a.task,
          a.init, overrides(a), a.skip_validation)
