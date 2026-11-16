#!/usr/bin/env bash
# Counts todo!( per crate and #[ignore = "todo( per test file.
cd "$(dirname "$0")/.."
printf '%-28s %8s\n' "location" "todo!"
total=0
for d in src crates/*; do
  n=$( (grep -rE 'todo!\(' --include='*.rs' "$d" 2>/dev/null || true) | wc -l)
  printf '%-28s %8s\n' "$d" "$n"; total=$((total + n))
done
printf '%-28s %8s\n' "TOTAL todo!" "$total"
echo
printf '%-44s %8s\n' "test file" "ignored"
itotal=0
while IFS= read -r f; do
  n=$(grep -cE '#\[ignore = "todo\(' "$f")
  [ "$n" -gt 0 ] && { printf '%-44s %8s\n' "$f" "$n"; itotal=$((itotal + n)); }
done < <(find src crates tests -name '*.rs' 2>/dev/null)
printf '%-44s %8s\n' "TOTAL ignored" "$itotal"
