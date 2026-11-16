#!/usr/bin/env bash
# The one command every task runs before committing.
# Task 6 adds: cargo sqlx prepare --check
set -euo pipefail
cd "$(dirname "$0")/.."
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
cargo deny check
echo "CHECK OK"
