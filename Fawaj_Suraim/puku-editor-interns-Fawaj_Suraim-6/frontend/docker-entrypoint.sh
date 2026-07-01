#!/bin/sh
# Frontend entrypoint.
# Renders ${BACKEND_URL} into /etc/nginx/conf.d/default.conf (idempotent
# — safe to re-run) and then execs whatever CMD was passed (normally
# `nginx -g daemon off;` from the Dockerfile).

set -eu

CONF=/etc/nginx/conf.d/default.conf

# Only substitute if the placeholder is actually present. The file
# produced by the build always contains `${BACKEND_URL}`; if you've
# hardcoded a value you can ignore this script.
if grep -q '\${BACKEND_URL}' "$CONF" 2>/dev/null; then
  envsubst '${BACKEND_URL}' < "$CONF" > "$CONF.tmp"
  mv "$CONF.tmp" "$CONF"
fi

exec "$@"
