#!/usr/bin/env bash
# Lint canary: proves the lint wall rejects forbidden constructs.
# Writes a deliberately bad file, runs clippy, asserts every lint fires, always cleans up.
set -u
cd "$(dirname "$0")/.."
CANARY="crates/domain/src/bin/canary.rs"
OUT="$(mktemp)"
cleanup() {
  rm -f "$CANARY" "$OUT"
  rmdir crates/domain/src/bin 2>/dev/null || true
}
trap cleanup EXIT
mkdir -p crates/domain/src/bin
cat > "$CANARY" <<'RS'
//! Canary: must never compile cleanly.
fn main() {
    let v = vec![1, 2, 3];
    let a: Option<i32> = Some(1);
    let _x = a.unwrap();
    let _y = a.expect("boom");
    let _z = v[0];
    let _p = unsafe { std::mem::zeroed::<u8>() };
    panic!("no");
}
RS
cargo clippy -p domain --all-targets -- -D warnings >"$OUT" 2>&1
code=$?
fail=0
if [ "$code" -eq 0 ]; then echo "CANARY FAIL: clippy exited 0"; fail=1; fi
for lint in unwrap_used expect_used panic indexing_slicing unsafe-code; do
  if ! grep -q "$lint" "$OUT"; then echo "CANARY FAIL: lint '$lint' not reported"; fail=1; fi
done
if [ "$fail" -ne 0 ]; then tail -n 40 "$OUT"; exit 1; fi
echo "CANARY OK: clippy rejected unwrap, expect, panic, indexing and unsafe"
