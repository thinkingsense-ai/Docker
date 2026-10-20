#!/bin/bash
# A small local certificate authority for INTERNAL TESTING of the HTTPS option. Not for customers: a real deployment uses a
# certificate from a public authority (for example Let's Encrypt) or the customer's own. Browsers trust this CA only after you
# install it once (see local_ca_trust_hint), and then every test deployment it certifies shows a clean padlock.
#
#   . scripts/lib/local-ca.sh
#   local_ca_init                               # once: creates ~/.thinkingsense-ca (override with LOCAL_CA_DIR)
#   local_ca_issue_p12 <out.p12> <password> <ip-or-dns> [more ip-or-dns ...]
set -euo pipefail
LOCAL_CA_DIR=${LOCAL_CA_DIR:-$HOME/.thinkingsense-ca}

local_ca_init() {
  mkdir -p "$LOCAL_CA_DIR"; chmod 700 "$LOCAL_CA_DIR"
  [ -f "$LOCAL_CA_DIR/ca.pem" ] && return 0
  openssl genrsa -out "$LOCAL_CA_DIR/ca.key" 4096 2>/dev/null
  chmod 600 "$LOCAL_CA_DIR/ca.key"
  openssl req -x509 -new -key "$LOCAL_CA_DIR/ca.key" -sha256 -days 3650 -subj "/O=ThinkingSense internal testing/CN=ThinkingSense test CA" \
    -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" -out "$LOCAL_CA_DIR/ca.pem"
  echo "created local CA: $LOCAL_CA_DIR/ca.pem"
}

local_ca_trust_hint() {
  echo "To stop browser warnings, trust the CA once on this Mac (asks for your password):"
  echo "  sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain $LOCAL_CA_DIR/ca.pem"
}

# Issues a server certificate valid 365 days (browsers reject longer) for the given IPs and/or names, and writes a PKCS12 keystore
# with the CA chain, which is the format the app reads.
local_ca_issue_p12() {
  local out=$1 pass=$2; shift 2
  local d; d=$(mktemp -d); local san="" first=""
  for a in "$@"; do
    [ -z "$first" ] && first=$a
    if [[ $a =~ ^[0-9.]+$ ]] || [[ $a == *:* ]]; then san="$san${san:+,}IP:$a"; else san="$san${san:+,}DNS:$a"; fi
  done
  openssl genrsa -out "$d/s.key" 2048 2>/dev/null
  # A common name is limited to 64 characters (an AWS load balancer name is longer); the real names are in the subjectAltName either way.
  local cn=$first; [ ${#cn} -gt 64 ] && cn=omnigate
  openssl req -new -key "$d/s.key" -subj "/O=ThinkingSense internal testing/CN=$cn" -out "$d/s.csr"
  printf 'basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=%s\n' "$san" > "$d/ext"
  openssl x509 -req -in "$d/s.csr" -CA "$LOCAL_CA_DIR/ca.pem" -CAkey "$LOCAL_CA_DIR/ca.key" -CAcreateserial -days 365 -sha256 \
    -extfile "$d/ext" -out "$d/s.pem" 2>/dev/null
  # LOCAL_CA_NO_CHAIN=1 leaves the CA certificate out of the keystore (smaller: AWS CloudFormation limits a parameter to 4096 characters).
  local chain=(-certfile "$LOCAL_CA_DIR/ca.pem"); [ -n "${LOCAL_CA_NO_CHAIN:-}" ] && chain=()
  openssl pkcs12 -export -inkey "$d/s.key" -in "$d/s.pem" ${chain[@]+"${chain[@]}"} -name omnigate -passout "pass:$pass" -out "$out"
  rm -rf "$d"
}
