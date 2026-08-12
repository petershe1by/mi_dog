#!/usr/bin/env bash
set -euo pipefail

target="${MI_DOG_TARGET:-mi@192.168.44.1}"
identity="${MI_DOG_SSH_IDENTITY:-${HOME}/.ssh/mi_dog_competition_ed25519}"

mkdir -p "$(dirname "$identity")"
chmod 0700 "$(dirname "$identity")"
if [[ ! -f "$identity" ]]; then
  ssh-keygen -q -t ed25519 -N '' -C 'mi-dog-competition-ui' -f "$identity"
  chmod 0600 "$identity"
fi

echo "Installing the dedicated public key on $target. Enter the robot password once."
ssh-copy-id -i "${identity}.pub" "$target"
echo "SSH key ready: $identity"
echo "Test with: MI_DOG_SSH_IDENTITY='$identity' ./scripts/connect_robot.sh"
