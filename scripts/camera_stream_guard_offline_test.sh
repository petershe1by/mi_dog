#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT
events="$temporary/events"

printf '%s\n' '#!/usr/bin/env bash' 'exit 0' >"$temporary/probe"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$1" >>"$MI_DOG_CAMERA_TEST_EVENTS"' >"$temporary/call"
chmod +x "$temporary/probe" "$temporary/call"

MI_DOG_CAMERA_MIN_UPTIME_SEC=0 \
MI_DOG_CAMERA_ACTIVE_WINDOW_SEC=1 \
MI_DOG_CAMERA_REST_WINDOW_SEC=0 \
MI_DOG_CAMERA_PROBE_INTERVAL_SEC=1 \
MI_DOG_CAMERA_MAX_CYCLES=2 \
MI_DOG_CAMERA_PROBE_COMMAND="$temporary/probe" \
MI_DOG_CAMERA_CALL_COMMAND="$temporary/call" \
MI_DOG_CAMERA_TEST_EVENTS="$events" \
  "$root/scripts/start_camera_when_stable.sh" >"$temporary/output"

expected=$'10\n9\n10\n9\n10'
actual="$(cat "$events")"
[[ "$actual" == "$expected" ]] || {
  printf 'unexpected camera command sequence:\n%s\n' "$actual" >&2
  exit 1
}
grep -q 'Head RGB guarded cycles completed cleanly.' "$temporary/output"

# The first two probes accept an inherited stream and the freshly started
# cycle. The third probe simulates a mid-window loss; the guard must fail and
# issue exactly one STOP for the active cycle.
failure_events="$temporary/failure_events"
failure_count="$temporary/failure_count"
printf '%s\n' '#!/usr/bin/env bash' \
  'count=0; [[ ! -f "$MI_DOG_CAMERA_TEST_COUNT" ]] || count="$(cat "$MI_DOG_CAMERA_TEST_COUNT")"' \
  'count=$((count + 1)); printf "%s" "$count" >"$MI_DOG_CAMERA_TEST_COUNT"' \
  '(( count <= 2 ))' >"$temporary/failing_probe"
chmod +x "$temporary/failing_probe"

if MI_DOG_CAMERA_MIN_UPTIME_SEC=0 \
  MI_DOG_CAMERA_ACTIVE_WINDOW_SEC=3 \
  MI_DOG_CAMERA_REST_WINDOW_SEC=0 \
  MI_DOG_CAMERA_PROBE_INTERVAL_SEC=1 \
  MI_DOG_CAMERA_MAX_CYCLES=1 \
  MI_DOG_CAMERA_PROBE_COMMAND="$temporary/failing_probe" \
  MI_DOG_CAMERA_CALL_COMMAND="$temporary/call" \
  MI_DOG_CAMERA_TEST_COUNT="$failure_count" \
  MI_DOG_CAMERA_TEST_EVENTS="$failure_events" \
    "$root/scripts/start_camera_when_stable.sh" >"$temporary/failure_output" 2>&1; then
  echo "camera guard unexpectedly accepted a stale stream" >&2
  exit 1
fi
[[ "$(cat "$failure_events")" == $'10\n9\n10' ]] || {
  echo "camera guard did not issue exactly one fail-safe STOP" >&2
  exit 1
}
grep -q 'image stream became stale' "$temporary/failure_output"
echo 'camera_stream_guard_offline_test=PASS'
