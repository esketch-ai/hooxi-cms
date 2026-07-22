# 보안 가이드

Hooxi-CMS의 인증·권한·시크릿 관리 및 배포 보안 지침을 정의한다.

## 인증 및 권한

- 인증: JWT(HS256). access 8시간 / refresh 7일. 서명 키는 `JWT_SECRET` 환경 변수로 주입하며 절대 커밋하지 않는다.
- 비밀번호·PIN: bcrypt 해시로만 저장한다. 평문 저장·로그 출력 금지.
- 권한(RBAC): STAFF / MANAGER / ADMIN 3단계. 권한 판정은 토큰 payload가 아니라 DB(`token_version` 재조회) 기준으로 수행한다. 토큰의 role은 화면 표시용이다.
- 세션 무효화: 사용자 상태 변경·강제 로그아웃은 `token_version` 증가로 기존 토큰을 무효화한다.
- 감사 로그: 주요 변경과 민감정보 열람(reveal)을 기록한다. 감사 로그에는 비밀값(비밀번호·토큰·API 키 등)을 저장하지 않는다.

## 시크릿 관리

### 커밋 금지 대상
다음 파일·값은 절대 저장소에 커밋하지 않는다.

- `.env` — 데이터베이스 자격증명 및 애플리케이션 시크릿
- `*.pem`, `*.key` — 인증서 및 개인 키
- 비밀번호, API 키, 토큰이 포함된 모든 파일

`.gitignore`에 위 항목이 포함되어 있는지 항상 확인한다.

### 환경 변수(인프라)
핵심 인프라 설정은 환경 변수로 주입한다. 로컬은 `.env`, 운영은 Cloud Run 서비스 설정을 사용한다.

| 변수 | 용도 |
|------|------|
| `JWT_SECRET` | JWT 서명 키(운영에서 반드시 강한 임의값으로 설정) |
| `DB_HOST` `DB_PORT` `DB_NAME` `DB_USER` `DB_PASSWORD` | 데이터베이스 접속 |
| `CORS_ORIGINS` `FRONTEND_ORIGIN` | 허용 출처(CORS) |
| `APP_BASE_URL` | 링크·토큰 생성 기준 URL |
| `BATCH_SECRET` | 배치 엔드포인트 호출 인증 |
| `ALLOWED_EMAIL_DOMAIN` | 로그인 허용 이메일 도메인 |
| `ENABLE_DEV_LOGIN` | dev-login 활성화 여부(운영에서는 비활성) |
| `SEED_ADMIN_EMAIL` | 초기 관리자 시드 |
| `GCP_PROJECT` `CLOUDSQL_INSTANCE` | Cloud SQL 백업 대상 |
| `GCS_BUCKET` `UPLOAD_DIR` | 파일 스토리지 |

### 연동 시크릿(설정 저장소)
외부 연동 시크릿은 환경 변수가 아니라 애플리케이션 설정 저장소(`tb_config`, 환경 설정 화면의 연동 탭)에서 관리한다. 대상 연동은 다음과 같다.

- 카카오/알림톡: Solapi API 키·시크릿·발신 정보, 카카오 봇/템플릿/webhook 시크릿
- 이메일: SMTP 접속 정보
- 파일 스토리지: Dropbox 앱 키·시크릿·리프레시 토큰
- SSO: 네이버웍스 OAuth 클라이언트 정보

연동 시크릿은 저장 시 별도로 보호되며 감사 로그·API 응답에 평문으로 노출되지 않는다. 미설정 연동은 비활성(501/503 게이트)으로 동작하며 앱 기동에는 영향을 주지 않는다.

## 로컬 설정 절차

1. 환경 템플릿 복사
   ```bash
   cp .env.example .env
   ```
2. `.env`에 자격증명 입력. 데이터베이스 비밀번호는 12자 이상의 강한 값을 사용한다.
3. `.env.example`만 커밋하고 `.env`는 커밋하지 않는다.

데이터베이스 접속 문자열 형식:
```
postgresql://user:password@host:port/database_name
```

## 운영 배포 보안

- 시크릿은 Cloud Run 서비스 환경 변수(또는 Secret Manager 연동)로 주입한다.
```bash
gcloud run services update hooxi-cms \
  --set-env-vars="DB_PASSWORD=...,JWT_SECRET=...,DEBUG=false"
```
- 운영에서 `ENABLE_DEV_LOGIN`은 비활성으로 둔다.
- HTTPS를 강제하고 `CORS_ORIGINS`를 실제 프론트 출처로 제한한다.
- 의존성을 최신으로 유지하고 정기적으로 자격증명을 교체한다.

## 보안 사고 대응

보안 침해가 의심되면 다음 순서로 대응한다.

1. 모든 자격증명(`JWT_SECRET` 포함) 즉시 교체
2. 노출된 API 키·연동 시크릿 폐기 및 재발급
3. 감사 로그 및 접근 로그 검토
4. 필요 시 `token_version` 일괄 증가로 기존 세션 강제 만료
5. 사고 내용을 기록하고 재발 방지 조치를 반영
