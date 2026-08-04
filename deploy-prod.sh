#!/usr/bin/env bash
# 운영 배포 (hooxi-cms-503308) — 사용자가 "배포"라고 명시할 때만 로컬에서 실행.
# 빌드는 Cloud Build로, 배포는 사용자 계정(roles/editor)으로 수행한다.
# (Cloud Build 기본 SA엔 Cloud Run 배포 권한이 없고, 소유자 IAM 부여가 불가하므로 배포를 분리)
set -euo pipefail

PROJECT=hooxi-cms-503308
REGION=asia-northeast1
SERVICE=hooxi-cms
IMAGE="gcr.io/${PROJECT}/hooxi-cms:latest"

echo "▶ 1/2 Cloud Build 이미지 빌드+push …"
gcloud builds submit --project="$PROJECT" --config=cloudbuild.yaml .

echo "▶ 2/2 Cloud Run 배포 …"
# 운영 필수 값: Secret Manager에 JWT_SECRET / DATABASE_URL / ASSET_ENC_KEY 를 만든 뒤
# DEPLOY_SECRETS 로 주입한다. 미설정 시 앱이 기동을 거부하거나 DB 연결에 실패한다
# (backend/main.py require_secure_jwt_secret, backend/models.py DATABASE_URL).
#   예) export DEPLOY_SECRETS="JWT_SECRET=JWT_SECRET:latest,DATABASE_URL=DATABASE_URL:latest,ASSET_ENC_KEY=ASSET_ENC_KEY:latest"
SECRETS="${DEPLOY_SECRETS:-}"

ARGS=(run deploy "$SERVICE"
  --project="$PROJECT" --region="$REGION"
  --image="$IMAGE" --platform=managed --allow-unauthenticated)

if [[ -n "$SECRETS" ]]; then
  ARGS+=(--set-secrets="$SECRETS")
else
  echo "⚠ DEPLOY_SECRETS 미설정 — JWT_SECRET 등 없이 배포하면 기동이 실패할 수 있습니다."
fi

gcloud "${ARGS[@]}"
