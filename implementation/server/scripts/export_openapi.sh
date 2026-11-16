#!/usr/bin/env bash
# Writes docs/openapi.yaml from the code (`clinic-server --print-openapi`).
# JSON is valid YAML; the test `committed_openapi_yaml_matches_generated` fails when the
# committed file differs from the generated document, so run this after any schema change.
set -euo pipefail
cd "$(dirname "$0")/.."
cargo run --quiet --bin clinic-server -- --print-openapi > docs/openapi.yaml.tmp
mv docs/openapi.yaml.tmp docs/openapi.yaml
echo "docs/openapi.yaml written"
