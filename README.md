# Hooxi-CMS (Carbon Fleet)

탄소감축 컨설팅사의 내부 CMS. 운수사·건물 고객사, 자산·연동, 감축사업·정산, 카카오 상담을 단일 콘솔에서 관리한다.

## 시스템 개요

- 대상: 컨설팅사 내부 실무자(STAFF)·매니저(MANAGER)·관리자(ADMIN).
- 성격: 데이터 테이블·폼 중심의 운영 콘솔. 고객사부터 자산 수집, 감축사업, 정산, 리포트 발송, 카카오 상담까지 업무 흐름 전반을 다룬다.
- 배포 형태: 프론트엔드(정적 번들)와 백엔드(API)를 단일 컨테이너로 빌드해 Cloud Run에서 서비스한다.

## 기술 스택

### 백엔드
- Python 3.9, FastAPI 0.115
- SQLAlchemy 2.0 (ORM), PostgreSQL 15 (운영) / SQLite (테스트)
- 인증: PyJWT 기반 JWT, bcrypt 비밀번호/PIN 해시
- 외부 연동: httpx(Solapi 알림톡·카카오 이벤트), smtplib(SMTP 메일), Dropbox SDK / GCS, Cloud SQL Admin API(백업)

### 프론트엔드
- React 19, TypeScript, Vite
- Tailwind CSS v4
- react-router-dom 7 (라우팅), @tanstack/react-query + axios (서버 상태·API)
- Phosphor Icons

### 인프라
- Docker 멀티스테이지 빌드(node:20-alpine 프론트 빌드 → python:3.9-slim 서빙)
- Cloud Build → Cloud Run (배포 정의는 `cloudbuild.yaml`)

## 주요 기능(화면)

라우팅은 `frontend/src/app/router.tsx` 기준. 모든 화면은 백엔드 `/api/v1` API에 실제 연동된다.

| 화면 | 경로 | 설명 |
|------|------|------|
| 통합 현황판 | `/dashboard` | 오늘의 액션 센터, 이달 보고서 진행, 최근 활동, 통계 집계 |
| 이슈 보드 | `/issues` | 계정 점검·연동 이슈 추적 및 코멘트 |
| 일정 | `/calendar` | 업무 일정 등록·완료 처리 |
| 고객사 | `/clients`, `/clients/:id` | 운수사·건물 고객사 마스터, 사업자번호 중복 검사 |
| 영업 활동 이력 | `/histories` | 활동 이력 등록·수정, 날짜 그룹·서버 검색 |
| 보고서 | `/reports` | 기간별 리포트 자동 생성·파일 업로드·발송·상태 관리 |
| 세그먼트 발송 | `/reports/segments` | 조건 기반 대상 선별 후 공통 파일 일괄 발송 |
| 문서 자산 | `/documents` | 문서 업로드/다운로드, 이미지·PDF 미리보기 |
| 자산 | `/assets` | 수집 대상 자산 관리, 접속정보 reveal 감사 |
| 수집 계정 관리 | `/accounts` | 연동 계정 점검(account-check) |
| 감축사업 | `/projects`, `/projects/:id` | 사업·고객사 매핑 관리 |
| 정산 현황 | `/settlements` | 정산 스냅샷·예상 금액 계산, 상태 변경 흐름 |
| 상담 | `/chat` | 하이브리드 챗(AI + 인간 담당자) 스레드·메시지 |
| 관제 지도 | `/map` | 고객사 위치 지도(구글/네이버 공급자 토글) |
| 환경 설정 | `/settings` | 공통 코드·연동·시스템 설정·백업·감사 로그(5개 탭) |
| 사용자 가이드 | `/guide` | 메뉴별 사용법·상태 흐름·FAQ (전 역할) |
| 로그인 | `/login` | 이메일+PIN 로그인, 네이버웍스 SSO |

## 인증 및 권한

- JWT: access 8시간 / refresh 7일(HS256). 프론트는 401 응답 시 refresh 토큰으로 1회 자동 재발급한다.
- 로그인 수단: 이메일+비밀번호(bcrypt) + PIN, 네이버웍스 OAuth(OIDC) SSO. 개발 편의를 위한 dev-login은 `ENABLE_DEV_LOGIN`으로 게이트한다.
- 권한(RBAC): STAFF · MANAGER · ADMIN 3단계. `require_role`/`require_permission` 의존성과 권한 매트릭스로 판정하며, 권한 판정은 토큰이 아닌 DB(`token_version` 재조회) 기준이다.
- 감사 로그: 주요 변경·민감정보 열람(reveal)을 기록한다. 감사 로그에는 비밀값을 저장하지 않는다.

## API

- 공통 프리픽스: `/api/v1`
- 라우터: `backend/routers/`의 20개 라우터(auth, users, clients, assets, projects, settlements, reports, segments, histories, schedules, documents, chat, kakao, imports, config, codes, backups, dashboard, audit, integrations, batch)가 모두 실제 DB 연동으로 구현되어 있다.
- 상세 스키마: 서버 기동 후 `/docs`(Swagger UI) 참조.

## 데이터베이스

- ORM 모델: `backend/models.py` (테이블 25종, `tb_` 접두 규약).
- 공통 분류·상태값은 공통 코드 마스터(`tb_code`)로 관리한다(하드코딩 금지).
- 스키마 정합: 앱 기동 시 `ensure_schema()`가 `create_all`을 보완해 누락 컬럼·인덱스·유니크 제약을 멱등적으로 보강한다. 배포 테이블에 컬럼을 추가할 때는 `ensure_schema`에 반영한다.
- `db_init.sql`은 초기 참고용 SQL이며, 운영 스키마의 기준은 SQLAlchemy 모델 + `ensure_schema`다.

## 로컬 개발

### Docker Compose
```bash
docker-compose up -d
```
- 프론트엔드: http://localhost:5173
- 백엔드 API: http://localhost:8000/api/v1
- 데이터베이스: localhost:5432 (PostgreSQL)

### 환경 변수
`.env.example`를 복사해 `.env`를 만든 뒤 값을 채운다.
```bash
cp .env.example .env
```
핵심 변수와 연동 시크릿 관리 방식은 [SECURITY.md](SECURITY.md)를 참고한다.

## 테스트 및 빌드

```bash
# 백엔드 테스트
cd backend && python -m pytest

# 프론트엔드 빌드(타입체크 포함)
cd frontend && NODE_OPTIONS= npm run build
```
- 백엔드 테스트: `backend/tests/` 31개 파일, 334개 테스트 함수.

## 배포

- main 브랜치에 push하면 Cloud Build가 트리거되어 컨테이너를 빌드하고 Cloud Run(서비스 `hooxi-cms`)에 배포한다.
- 배포 리전 등 파라미터의 기준은 `cloudbuild.yaml`이다.
- 프로덕션 환경 변수는 Cloud Run 서비스 설정으로 주입한다.

```bash
gcloud run services update hooxi-cms \
  --set-env-vars="DATABASE_URL=postgresql://user:pass@host:5432/dbname"
```

## 문서

- [FUNCTIONAL_REQUIREMENTS.md](FUNCTIONAL_REQUIREMENTS.md) — 기능 구현 현황
- [DESIGN.md](DESIGN.md) — 디자인 시스템 레퍼런스
- [SECURITY.md](SECURITY.md) — 보안 및 시크릿 관리
- [CLAUDE.md](CLAUDE.md) — 개발 규약 및 작업 도리
- `Docs/USER_GUIDE.html` — 실무자 업무 가이드
