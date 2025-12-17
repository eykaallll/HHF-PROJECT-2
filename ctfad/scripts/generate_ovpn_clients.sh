#!/usr/bin/env bash
set -euo pipefail

# Generate OpenVPN client profiles for one or more teams.
# Usage: ./scripts/generate_ovpn_clients.sh [team01 team02 ...]

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f docker-compose.yml ]]; then
    echo "Run this script from the ctfad/ repository root." >&2
    exit 1
fi

if ! docker compose ps openvpn >/dev/null 2>&1; then
    echo "OpenVPN container is not running. Start it with: docker compose up -d openvpn" >&2
    exit 1
fi

if [[ $# -gt 0 ]]; then
    clients=("$@")
else
    clients=(team01 team02 team03 team04 team05 team06 team07 team08 team09 team10)
fi

mkdir -p vpn-config

for name in "${clients[@]}"; do
    echo "[*] building profile for ${name}"
    docker compose exec -T openvpn easyrsa build-client-full "$name" nopass >/dev/null
    outfile="vpn-config/${name}.ovpn"
    echo "    exporting ${outfile}"
    docker compose exec -T openvpn ovpn_getclient "$name" >"$outfile"
done

echo "[+] Generated ${#clients[@]} client profiles in vpn-config/"
