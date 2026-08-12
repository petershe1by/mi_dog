#!/usr/bin/env bash
set -euo pipefail

target="${MI_DOG_TARGET:-mi@192.168.44.1}"
identity="${MI_DOG_SSH_IDENTITY:-${HOME}/.ssh/mi_dog_competition_ed25519}"
options=(-o StrictHostKeyChecking=accept-new)
if [[ -f "$identity" ]]; then
  options+=(-o IdentitiesOnly=yes -i "$identity")
fi

exec ssh "${options[@]}" "$target" "$@"
