#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT
workspace="$temporary/workspace"
mkdir -p "$workspace/src/mi_dog_real" "$workspace/scripts" \
  "$workspace/install/mi_dog_real" "$temporary/etc" "$temporary/output"
printf 'source\n' >"$workspace/src/mi_dog_real/file.cpp"
printf 'script\n' >"$workspace/scripts/tool.sh"
printf 'binary\n' >"$workspace/install/mi_dog_real/node"
printf 'unit\n' >"$temporary/etc/mi-dog-real-sensor.service"

mapfile -t outputs < <(
  bash "$root/scripts/create_rollback_bundle.sh" \
    --source-commit 200215e \
    --workspace "$workspace" \
    --unit-file "$temporary/etc/mi-dog-real-sensor.service" \
    --output-dir "$temporary/output"
)
[[ ${#outputs[@]} -eq 2 ]]
archive="${outputs[0]}"
sidecar="${outputs[1]}"
[[ -f "$archive" && -f "$sidecar" ]]
(cd "$(dirname "$archive")" && sha256sum -c "$(basename "$sidecar")") >/dev/null
mkdir "$temporary/unpacked"
tar -xzf "$archive" -C "$temporary/unpacked"
(cd "$temporary/unpacked" && sha256sum -c SHA256SUMS) >/dev/null
grep -q '^source_commit=200215e$' "$temporary/unpacked/METADATA.txt"
[[ -f "$temporary/unpacked/workspace/src/mi_dog_real/file.cpp" ]]
[[ -f "$temporary/unpacked/workspace/scripts/tool.sh" ]]
[[ -f "$temporary/unpacked/workspace/install/mi_dog_real/node" ]]
[[ -f "$temporary/unpacked/etc/systemd/system/mi-dog-real-sensor.service" ]]
echo 'create_rollback_bundle_offline_test=PASS'
