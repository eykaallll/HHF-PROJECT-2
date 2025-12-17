#!/usr/bin/env bash

set -euo pipefail

CONFIG_FILE="/etc/openvpn/ovpn_env.sh"
SERVER_CERT="/etc/openvpn/pki/issued/server.crt"
OVPN_PORT="${OPENVPN_PORT:-1194}"
VPN_SUBNET="${OPENVPN_VPN_SUBNET:-10.99.0.0/24}"
ROUTE_SUBNETS="${OPENVPN_ROUTE_SUBNETS:-${CTF_NET_SUBNET:-}}"
DISABLE_BLOCK_DNS="${OPENVPN_DISABLE_PUSH_BLOCK_DNS:-1}"
DISABLE_DEFAULT_ROUTE="${OPENVPN_DISABLE_DEFAULT_ROUTE:-1}"
ENABLE_NAT="${OPENVPN_ENABLE_NAT:-1}"
FORCE_REGEN="${OPENVPN_FORCE_REGEN:-0}"

# Prefer an explicit OpenVPN URL, otherwise fall back to a sensible default
DESIRED_OVPN_SERVER_URL="${OPENVPN_SERVER_URL:-udp://127.0.0.1:${OVPN_PORT}}"

# We mutate this later, so keep track of the final value we want in the env file.
OVPN_SERVER_URL="${DESIRED_OVPN_SERVER_URL}"

REGEN_CONFIG=0
if [[ ! -f "${CONFIG_FILE}" ]]; then
  REGEN_CONFIG=1
else
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
  CURRENT_URL="${OVPN_SERVER_URL:-}"
  CURRENT_SUBNET="${OVPN_SERVER:-}"
  CURRENT_DEFROUTE="${OVPN_DEFROUTE:-}"
  CURRENT_BLOCK_DNS="${OVPN_DISABLE_PUSH_BLOCK_DNS:-}"
  CURRENT_ROUTES=""
  if declare -p OVPN_ROUTES 2>/dev/null | grep -q 'declare -a'; then
    CURRENT_ROUTES="$(printf "%s," "${OVPN_ROUTES[@]}")"
    CURRENT_ROUTES="${CURRENT_ROUTES%,}"
  fi
  if [[ "${CURRENT_URL}" != "${DESIRED_OVPN_SERVER_URL}" ]]; then
    echo "[bootstrap-openvpn] Detected server URL change (${CURRENT_URL} -> ${DESIRED_OVPN_SERVER_URL}), regenerating config" >&2
    REGEN_CONFIG=1
  fi
  if [[ -n "${CURRENT_SUBNET}" && "${CURRENT_SUBNET}" != "${VPN_SUBNET}" ]]; then
    echo "[bootstrap-openvpn] Detected VPN subnet change (${CURRENT_SUBNET} -> ${VPN_SUBNET}), regenerating config" >&2
    REGEN_CONFIG=1
  fi
  if [[ -n "${ROUTE_SUBNETS}" && "${CURRENT_ROUTES}" != "${ROUTE_SUBNETS}" ]]; then
    echo "[bootstrap-openvpn] Detected route set change (${CURRENT_ROUTES} -> ${ROUTE_SUBNETS}), regenerating config" >&2
    REGEN_CONFIG=1
  fi
  if [[ "${DISABLE_BLOCK_DNS}" == "1" && "${CURRENT_BLOCK_DNS}" != "1" ]]; then
    echo "[bootstrap-openvpn] Enabling -b (disable block-outside-dns); regenerating config" >&2
    REGEN_CONFIG=1
  fi
  if [[ "${DISABLE_DEFAULT_ROUTE}" == "1" && "${CURRENT_DEFROUTE}" != "0" ]]; then
    echo "[bootstrap-openvpn] Disabling default-route push; regenerating config" >&2
    REGEN_CONFIG=1
  fi
fi
[[ "${FORCE_REGEN}" == "1" ]] && REGEN_CONFIG=1

# Restore the desired value so downstream commands run with the latest intent.
OVPN_SERVER_URL="${DESIRED_OVPN_SERVER_URL}"

cidr_to_mask() {
  case "$1" in
    0) echo "0.0.0.0" ;;
    8) echo "255.0.0.0" ;;
    16) echo "255.255.0.0" ;;
    24) echo "255.255.255.0" ;;
    25) echo "255.255.255.128" ;;
    26) echo "255.255.255.192" ;;
    27) echo "255.255.255.224" ;;
    28) echo "255.255.255.240" ;;
    29) echo "255.255.255.248" ;;
    30) echo "255.255.255.252" ;;
    31) echo "255.255.255.254" ;;
    32) echo "255.255.255.255" ;;
    *) echo "" ;;
  esac
}

if [[ ${REGEN_CONFIG} -eq 1 ]]; then
  echo "[bootstrap-openvpn] Generating OpenVPN config at ${CONFIG_FILE} for ${DESIRED_OVPN_SERVER_URL}" >&2
  GEN_ARGS=(-u "${DESIRED_OVPN_SERVER_URL}" -s "${VPN_SUBNET}")
  if [[ -n "${ROUTE_SUBNETS}" ]]; then
    IFS=',' read -ra ROUTES <<<"${ROUTE_SUBNETS}"
    for net in "${ROUTES[@]}"; do
      route_net="${net}"
      route_mask=""
      if [[ "${net}" == */* ]]; then
        route_net="${net%%/*}"
        cidr="${net##*/}"
        route_mask="$(cidr_to_mask "${cidr}")"
      fi
      if [[ -n "${route_mask}" ]]; then
        GEN_ARGS+=(-p "route ${route_net} ${route_mask}")
      else
        GEN_ARGS+=(-p "route ${route_net}")
      fi
    done
  fi
  if [[ "${DISABLE_BLOCK_DNS}" == "1" ]]; then
    GEN_ARGS+=(-b)
  fi
  if [[ "${DISABLE_DEFAULT_ROUTE}" == "1" ]]; then
    GEN_ARGS+=(-d)
  fi
  if [[ "${ENABLE_NAT}" == "1" ]]; then
    GEN_ARGS+=(-N)
  fi
  ovpn_genconfig "${GEN_ARGS[@]}"
fi

if [[ ! -f "${SERVER_CERT}" ]]; then
  echo "[bootstrap-openvpn] Initializing PKI (non-interactive)" >&2
  export EASYRSA_BATCH=1
  export EASYRSA_REQ_CN="${OPENVPN_REQ_CN:-ctfad-vpn-ca}"
  ovpn_initpki nopass >/dev/null
fi

# Ensure IPv4 forwarding is enabled inside the container (needed for NAT to 10.10.0.0/24).
if ! sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1; then
  echo "[bootstrap-openvpn] Warning: unable to set net.ipv4.ip_forward (read-only FS?)" >&2
fi

# If NAT is enabled, make sure a MASQUERADE rule exists for VPN traffic leaving eth0.
if [[ "${ENABLE_NAT}" == "1" ]]; then
  if command -v iptables >/dev/null 2>&1; then
    if ! iptables -t nat -C POSTROUTING -s "${VPN_SUBNET}" -o eth0 -j MASQUERADE >/dev/null 2>&1; then
      if ! iptables -t nat -A POSTROUTING -s "${VPN_SUBNET}" -o eth0 -j MASQUERADE >/dev/null 2>&1; then
        echo "[bootstrap-openvpn] Warning: unable to add MASQUERADE rule; check container privileges" >&2
      fi
    fi
    if ! iptables -t nat -C POSTROUTING -s "${VPN_SUBNET}" -j MASQUERADE >/dev/null 2>&1; then
      iptables -t nat -A POSTROUTING -s "${VPN_SUBNET}" -j MASQUERADE >/dev/null 2>&1 || true
    fi
  else
    echo "[bootstrap-openvpn] Warning: iptables not found; NAT rule not applied" >&2
  fi
fi

exec ovpn_run
