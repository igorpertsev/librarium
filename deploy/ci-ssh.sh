#!/usr/bin/env bash
# Run deploy/update.sh on a server over SSH (from .github/workflows/deploy.yml).
#
#   SSH_KEY=… KNOWN_HOSTS=… deploy/ci-ssh.sh user@host /home/user/librarium [--no-backup] <commit>
#
# The key and the server's host key come from the environment (GitHub secrets); the host key is
# pinned, so the connection fails instead of trusting an unknown server.
set -euo pipefail
target="${1:?user@host}"
dir="${2:?directory of the checkout on the server}"
shift 2
: "${SSH_KEY:?set SSH_KEY}" "${KNOWN_HOSTS:?set KNOWN_HOSTS}"

for arg in "$@"; do
  [[ "$arg" == "--no-backup" || "$arg" =~ ^[0-9a-f]{7,40}$ ]] || { echo "bad argument: $arg" >&2; exit 2; }
done
[[ "$dir" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "bad directory: $dir" >&2; exit 2; }

keydir="$(mktemp -d)"
trap 'rm -rf "$keydir"' EXIT
printf '%s\n' "$SSH_KEY" > "$keydir/key"
printf '%s\n' "$KNOWN_HOSTS" > "$keydir/known_hosts"
chmod 600 "$keydir/key"

ssh -i "$keydir/key" \
  -o IdentitiesOnly=yes \
  -o UserKnownHostsFile="$keydir/known_hosts" \
  -o StrictHostKeyChecking=yes \
  -o BatchMode=yes \
  -o ConnectTimeout=20 \
  "$target" "$dir/deploy/update.sh $*"
