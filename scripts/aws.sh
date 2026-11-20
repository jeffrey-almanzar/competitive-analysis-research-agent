#!/usr/bin/env bash
# Deploy the research agent to AWS (ECS Fargate + RDS), check on it, and tear it down.
#
#   scripts/aws.sh plan      # show what will be created; saves the plan for `apply`
#   scripts/aws.sh apply     # create exactly the saved plan, then build, push and start the app
#   scripts/aws.sh status    # URL and service health
#   scripts/aws.sh allow-ip  # your public IP changed? update the load balancer to allow the new one
#   scripts/aws.sh destroy   # delete everything (asks for confirmation)
#
# Reads ANTHROPIC_API_KEY and EXA_API_KEY from .env. The load balancer only accepts
# traffic from your current public IP. Optional: BUDGET_EMAIL=you@example.com for a
# monthly cost alert.
set -euo pipefail
cd "$(dirname "$0")/.."

TF_DIR=infra/aws
REGION="${AWS_REGION:-us-east-2}"
TF="terraform -chdir=$TF_DIR"

env_value() { grep -E "^$1=" .env | tail -1 | cut -d= -f2-; }

load_vars() {
  [ -f .env ] || { echo ".env not found"; exit 1; }
  export TF_VAR_region="$REGION"
  TF_VAR_anthropic_api_key="$(env_value ANTHROPIC_API_KEY)"
  TF_VAR_exa_api_key="$(env_value EXA_API_KEY)"
  export TF_VAR_anthropic_api_key TF_VAR_exa_api_key
  [ -n "$TF_VAR_anthropic_api_key" ] && [ -n "$TF_VAR_exa_api_key" ] || {
    echo "ANTHROPIC_API_KEY and EXA_API_KEY must be set in .env"; exit 1; }

  local ip
  ip="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')"
  export TF_VAR_allowed_cidrs="[\"${ip}/32\"]"

  local tag
  tag="$(git rev-parse --short HEAD)"
  [ -z "$(git status --porcelain -- src web)" ] || tag="${tag}-dirty"
  export TF_VAR_image_tag="$tag"

  export TF_VAR_budget_email="${BUDGET_EMAIL:-}"
  echo "region=$REGION  allowed=${ip}/32  image_tag=$tag  budget_email=${BUDGET_EMAIL:-<none>}"
}

push_images() {
  local api_repo web_repo api_url registry
  api_repo="$($TF output -raw api_repository)"
  web_repo="$($TF output -raw web_repository)"
  api_url="$($TF output -raw api_url_internal)"
  registry="${api_repo%%/*}"

  aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$registry"

  echo "Building and pushing api image ($TF_VAR_image_tag)..."
  docker buildx build --platform linux/arm64 -t "$api_repo:$TF_VAR_image_tag" --push src
  echo "Building and pushing web image ($TF_VAR_image_tag)..."
  docker buildx build --platform linux/arm64 -f web/Dockerfile.prod \
    --build-arg "API_URL=$api_url" -t "$web_repo:$TF_VAR_image_tag" --push web
}

restart_services() {
  local cluster
  cluster="$($TF output -raw cluster)"
  for svc in redis api worker web; do
    aws ecs update-service --region "$REGION" --cluster "$cluster" --service "$svc" \
      --force-new-deployment --query 'service.serviceName' --output text >/dev/null
  done
  echo "Waiting for services to become stable (a few minutes)..."
  aws ecs wait services-stable --region "$REGION" --cluster "$cluster" --services redis api worker web
}

status() {
  local cluster
  cluster="$($TF output -raw cluster)"
  aws ecs describe-services --region "$REGION" --cluster "$cluster" --services redis api worker web \
    --query 'services[].[serviceName,status,runningCount,desiredCount]' --output table
  echo "URL: $($TF output -raw url)"
}

case "${1:-}" in
  plan)
    load_vars
    $TF init -input=false -upgrade >/dev/null
    $TF plan -input=false -out=tfplan
    echo; echo "Saved plan to $TF_DIR/tfplan. Run 'scripts/aws.sh apply' to create exactly this."
    ;;
  apply)
    load_vars
    [ -f "$TF_DIR/tfplan" ] || { echo "No saved plan. Run 'scripts/aws.sh plan' first."; exit 1; }
    $TF apply -input=false tfplan
    rm -f "$TF_DIR/tfplan"
    push_images
    restart_services
    status
    ;;
  status)
    status
    ;;
  allow-ip)
    load_vars
    $TF plan -input=false -target=aws_security_group.alb -out=tfplan-ip
    read -r -p "Apply this change? [y/N] " ok
    [ "$ok" = "y" ] && $TF apply -input=false tfplan-ip
    rm -f "$TF_DIR/tfplan-ip"
    ;;
  destroy)
    load_vars
    $TF destroy -input=false
    ;;
  *)
    sed -n '2,13p' "$0"
    exit 1
    ;;
esac
