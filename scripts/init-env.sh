#!/usr/bin/env bash
# Fill in random local secrets for the self-hosted Langfuse stack in .env.
# Safe to re-run: existing non-empty values are kept.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || cp .env.example .env

set_if_empty() {
  local key="$1" value="$2"
  if grep -qE "^${key}=.+" .env; then
    return
  elif grep -qE "^${key}=" .env; then
    # Key present but empty: fill it in place.
    sed -i.bak "s|^${key}=.*|${key}=${value}|" .env && rm -f .env.bak
  else
    echo "${key}=${value}" >> .env
  fi
}

rand() { openssl rand -hex "${1:-24}"; }

set_if_empty LANGFUSE_HOST "http://langfuse-web:3000"
set_if_empty LANGFUSE_PUBLIC_KEY "pk-lf-local-$(rand 8)"
set_if_empty LANGFUSE_SECRET_KEY "sk-lf-local-$(rand 16)"
set_if_empty LANGFUSE_INIT_USER_EMAIL "admin@local.dev"
set_if_empty LANGFUSE_INIT_USER_PASSWORD "$(rand 12)"
set_if_empty LANGFUSE_SALT "$(rand 16)"
set_if_empty LANGFUSE_ENCRYPTION_KEY "$(rand 32)"
set_if_empty LANGFUSE_NEXTAUTH_SECRET "$(rand 24)"
set_if_empty LANGFUSE_POSTGRES_PASSWORD "$(rand 16)"
set_if_empty LANGFUSE_CLICKHOUSE_PASSWORD "$(rand 16)"
set_if_empty LANGFUSE_REDIS_PASSWORD "$(rand 16)"
set_if_empty LANGFUSE_MINIO_PASSWORD "$(rand 16)"

echo "Local Langfuse secrets are set in .env."
echo "Langfuse login: $(grep '^LANGFUSE_INIT_USER_EMAIL=' .env | cut -d= -f2) (password: LANGFUSE_INIT_USER_PASSWORD in .env)"
