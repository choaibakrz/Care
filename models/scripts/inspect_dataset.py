"""Validate a downloaded dataset, print its classes and a taxonomy skeleton."""
import argparse
from _common import *  # noqa: F401,F403
from medsort.data import Taxonomy
from medsort.training import get_export

p = argparse.ArgumentParser()
p.add_argument("dataset", choices=["hospital_consumables", "biosafety_ppe"])
a = p.parse_args()

exp = get_export(a.dataset)
print(f"classes: {exp.names}")
problems = exp.validate()
print(f"{len(problems)} problem(s)")
for pr in problems[:50]:
    print("  ", pr)
try:
    Taxonomy.load().check(a.dataset, exp.names)
    print("taxonomy.yaml matches this dataset")
except Exception as e:
    print(f"taxonomy mismatch: {e}\nSkeleton to paste under datasets.{a.dataset}:")
    for n in exp.names:
        print(f"    {n}: {{group: ???, fine: {n.replace('-', '_')}}}")
