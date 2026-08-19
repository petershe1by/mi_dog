#!/usr/bin/env bash
set -euo pipefail

workspace="${MI_DOG_WORKSPACE:-/home/mi/mi_dog_ws}"
unit_file="${MI_DOG_UNIT_FILE:-/etc/systemd/system/mi-dog-real-sensor.service}"
source_commit="unknown"
output_dir="${MI_DOG_ROLLBACK_OUTPUT_DIR:-$workspace/state}"

usage() {
  echo "Usage: $0 --source-commit COMMIT [--workspace DIR] [--unit-file FILE] [--output-dir DIR]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source-commit) source_commit="${2:-}"; shift 2 ;;
    --workspace) workspace="${2:-}"; shift 2 ;;
    --unit-file) unit_file="${2:-}"; shift 2 ;;
    --output-dir) output_dir="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

[[ "$source_commit" =~ ^[0-9a-fA-F]{7,40}$ ]] || {
  echo "Rollback bundle refused: invalid source commit." >&2; exit 2; }
[[ "$workspace" == /* && "$output_dir" == /* && "$unit_file" == /* ]] || {
  echo "Rollback bundle refused: paths must be absolute." >&2; exit 2; }

source_tree="$workspace/src/mi_dog_real"
scripts_tree="$workspace/scripts"
install_tree="$workspace/install/mi_dog_real"
for required in "$source_tree" "$scripts_tree" "$install_tree" "$unit_file"; do
  [[ -e "$required" ]] || {
    echo "Rollback bundle refused: missing $required" >&2; exit 1; }
done

mkdir -p "$output_dir"
staging="$(mktemp -d "$output_dir/.rollback-staging.XXXXXX")"
cleanup() { rm -rf "$staging"; }
trap cleanup EXIT INT TERM

payload="$staging/payload"
mkdir -p "$payload/workspace/src" "$payload/workspace/install" "$payload/etc/systemd/system"
cp -a "$source_tree" "$payload/workspace/src/mi_dog_real"
cp -a "$scripts_tree" "$payload/workspace/scripts"
cp -a "$install_tree" "$payload/workspace/install/mi_dog_real"
cp -a "$unit_file" "$payload/etc/systemd/system/mi-dog-real-sensor.service"

# The allowlist above must never acquire runtime or credential artifacts.
if find "$payload" -type f \( \
     -name '*.pem' -o -name '*.key' -o -name 'id_rsa*' -o -name 'id_ed25519*' \
     -o -name '*.bag' -o -name '*.db3' -o -name '*.log' -o -name '.env' \
   \) -print -quit | grep -q .; then
  echo "Rollback bundle refused: sensitive or runtime artifact found." >&2
  exit 1
fi

cat >"$payload/METADATA.txt" <<EOF
schema=mi_dog_rollback_v1
source_commit=$source_commit
workspace=/home/mi/mi_dog_ws
service=mi-dog-real-sensor.service
default_required_mode=maintenance
default_required_state=DOWN_WAITING
default_required_run_allowed=false
EOF

(
  cd "$payload"
  find . -type f ! -name SHA256SUMS -print0 | LC_ALL=C sort -z |
    xargs -0 sha256sum >SHA256SUMS
)

archive="$output_dir/mi_dog_rollback_${source_commit}_$(date +%Y%m%dT%H%M%S%z).tar.gz"
tar --sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner \
  -C "$payload" -czf "$archive" .
sha256sum "$archive" >"$archive.sha256"
printf '%s\n' "$archive"
printf '%s\n' "$archive.sha256"
