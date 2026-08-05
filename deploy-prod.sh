#!/usr/bin/env bash
# 운영 배포 (hooxi-cms-503308) — 사용자가 "배포"라고 명시할 때만 로컬에서 실행.
# 빌드는 Cloud Build로, 배포는 사용자 계정(roles/editor)으로 수행한다.
# (Cloud Build 기본 SA엔 Cloud Run 배포 권한이 없고, 소유자 IAM 부여가 불가하므로 배포를 분리)
#
# 사전 요구(owner가 1회 부여):
#   - 런타임 SA(608475832839-compute@developer.gserviceaccount.com):
#       roles/cloudsql.client, roles/secretmanager.secretAccessor
#   - 서비스 공개: run.services allUsers → roles/run.invoker
# 사전 요구(인프라): Cloud SQL 인스턴스 hooxi-cms-db(RUNNABLE) + DB hooxi_cms,
#   Secret Manager: hooxi-database-url / hooxi-jwt-secret / hooxi-asset-enc-key
set -euo pipefail

PROJECT=hooxi-cms-503308
REGION=asia-northeast1
SERVICE=hooxi-cms
IMAGE="gcr.io/${PROJECT}/hooxi-cms:latest"
SQL_CONN="${PROJECT}:${REGION}:hooxi-cms-db"

echo "▶ 1/2 Cloud Build 이미지 빌드+push …"
gcloud builds submit --project="$PROJECT" --config=cloudbuild.yaml .

echo "▶ 2/2 Cloud Run 배포 …"
# 시크릿은 Secret Manager로 주입(감사로그 비밀값 금지 R2-E6 준수). DB는 Cloud SQL 유닉스소켓.
# SEED_ADMIN_EMAIL: 최초(사용자 0명) 부트스트랩 ADMIN. 첫 email-login 시 PIN(4~6자리) 설정.
gcloud run deploy "$SERVICE" \
  --project="$PROJECT" --region="$REGION" \
  --image="$IMAGE" --platform=managed \
  --add-cloudsql-instances="$SQL_CONN" \
  --set-secrets="DATABASE_URL=hooxi-database-url:latest,JWT_SECRET=hooxi-jwt-secret:latest,ASSET_ENC_KEY=hooxi-asset-enc-key:latest,KAKAO_WEBHOOK_SECRET=hooxi-kakao-webhook-secret:latest" \
  --set-env-vars="SEED_ADMIN_EMAIL=hooxi12345@hooxipartners.com,GCP_PROJECT=hooxi-cms-503308,CLOUDSQL_INSTANCE=hooxi-cms-db"
# 공개 접근(allUsers invoker)은 서비스 레벨에 이미 부여돼 리비전 간 유지되므로 --allow-unauthenticated 생략.
