#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT
mkdir -p "$temporary/bin"

printf '%s\n' \
  '#!/usr/bin/env bash' \
  'set -euo pipefail' \
  ': "${MI_DOG_TEST_SSH_ARGS:?}"' \
  'printf "%s\n" "$@" >"$MI_DOG_TEST_SSH_ARGS"' \
  'cat >/dev/null' \
  >"$temporary/bin/ssh"
chmod +x "$temporary/bin/ssh"

export PATH="$temporary/bin:$PATH"
export MI_DOG_TEST_SSH_ARGS="$temporary/args"
export MI_DOG_FAST_EVENT=1
export MI_DOG_SSH_BATCH_MODE=1

"$root/scripts/competition_control.sh" pause
mapfile -t args <"$temporary/args"
[[ "${args[*]}" == *"bash -s -- PAUSE NONE 1"* ]]

"$root/scripts/competition_control.sh" status
mapfile -t args <"$temporary/args"
[[ "${args[*]}" == *"bash -s -- NONE NONE 1"* ]]

"$root/scripts/competition_control.sh" --stage 4 continue-stage
mapfile -t args <"$temporary/args"
[[ "${args[*]}" == *"bash -s -- CONTINUE 4 1"* ]]

echo "competition_control_transport_offline=PASS"
