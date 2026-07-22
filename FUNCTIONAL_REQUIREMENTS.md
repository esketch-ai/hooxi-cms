# Hooxi-CMS 기능 구현 현황

본 문서는 실제 코드베이스를 기준으로 한 기능 구현 현황이다. 화면 목록은 `frontend/src/app/router.tsx`, API는 `backend/routers/`, 데이터 모델은 `backend/models.py`를 근거로 한다.

## 요약

- 백엔드: 20개 라우터 전부 실제 DB 연동으로 구현. 인증·RBAC·감사 로그 완비. 테이블 25종, 테스트 31개 파일 / 334개 함수.
- 프론트엔드: 18개 기능 화면 전부 `/api/v1` 백엔드에 실연동. 하드코딩 목업 없음. 타입체크 포함 빌드 통과.
- 미완결 항목: 네이버웍스 OAuth SSO(프론트 완성, 백엔드 연동 대기), CI 테스트 게이트 부재.

## 인증 및 계정

- [x] JWT 발급/검증 — access 8시간 / refresh 7일, 401 시 refresh 자동 재발급
- [x] 이메일 + 비밀번호(bcrypt) 로그인
- [x] PIN(bcrypt) 설정/검증 — 미팅 모드·민감정보 reveal 게이트
- [x] RBAC — STAFF/MANAGER/ADMIN 3단계, 권한 매트릭스, DB(`token_version`) 기준 판정
- [x] 사용자 관리 — 등록/수정/상태 변경, 사용자 감사
- [x] 개발용 dev-login — `ENABLE_DEV_LOGIN` 게이트
- [~] 네이버웍스 OAuth SSO — 프론트 흐름 완성. 백엔드 미설정 시 501 → "연동 준비 중" 폴백

## 고객사 및 활동

- [x] 고객사 마스터 CRUD — 운수사·건물 유형, 사업자번호 중복 검사, 상세 화면
- [x] 영업 활동 이력 — 등록/수정, 날짜 그룹, 서버 검색
- [x] 이슈 보드 — 계정 점검·연동 이슈 추적, 코멘트
- [x] 일정 — 등록·완료 처리
- [x] 상담(하이브리드 챗) — 스레드/메시지, 대기 컨택 처리

## 자산 및 감축사업

- [x] 자산 관리 CRUD — 사진·스펙 모달, 접속정보 reveal 감사
- [x] 수집 계정 관리 — 계정 점검(account-check), 동시 실행 중복 차단
- [x] 감축사업 관리 — 사업 CRUD, 고객사 매핑
- [x] 정산 현황 — 정산 스냅샷, 예상 금액 계산, 상태 변경 흐름, 확정(freeze)
- [x] 관제 지도 — 고객사 위치 표시, 구글/네이버 지도 공급자 토글

## 보고서 및 문서

- [x] 보고서 — 기간별 자동 생성, 파일 업로드, 발송, 상태 관리, 승인/PIN
- [x] 세그먼트 발송 — 조건 기반 대상 선별, 실시간 미리보기, 공통 파일 일괄 발송
- [x] 문서 자산 — 업로드/다운로드, 이미지·PDF 미리보기
- [x] 리포트 알림톡 발송 — 템플릿 렌더링, 수신자 해석, 조회 토큰

## 데이터 및 연동

- [x] 공통 코드 마스터(`tb_code`) — 분류/상태값 CRUD, 하드코딩 금지 규약
- [x] 엑셀 일괄 등록 — 고객사·자산 spec/template/preview/commit
- [x] 카카오 연동 — Solapi 알림톡, 카카오 오픈빌더 이벤트 webhook, 컨택
- [x] 이메일(SMTP) 발송
- [x] 파일 스토리지 — GCS / Dropbox 라우팅, 임시 다운로드 링크
- [x] 데이터베이스 백업 — Cloud SQL Admin API 연동(미설정 시 503 게이트)
- [x] 배치 — 계정 점검·보고서 일괄 발송(`BATCH_SECRET` 인증)
- [x] 감사 로그 — 주요 변경·reveal 기록, 비밀값 미저장

## 대시보드 및 설정

- [x] 통합 현황판 — 오늘의 액션 센터, 이달 보고서 진행, 최근 활동, 통계 집계
- [x] 환경 설정(5개 탭) — 공통 코드 / 연동 / 시스템 설정 / 백업 / 감사 로그
- [x] 사용자 가이드(인앱) — 메뉴별 사용법·상태 흐름·FAQ

## 데이터 정합성

- [x] `ensure_schema()` — 기동 시 누락 컬럼·인덱스·유니크 제약 멱등 보강
- [x] 상태 머신·시간대(KST) 규약 정합
- [x] 동시 실행 중복 차단 — 결정적 PK(uuid5) + savepoint
- [x] 코드 길이 정합·매핑 유니크·조회 인덱스

## 미완결 및 개선 후보

- [ ] 네이버웍스 OAuth SSO 백엔드 연동 완료(현재 501 폴백)
- [ ] CI 파이프라인에 pytest 게이트 추가(테스트 존재, 자동 실행 없음)
- [ ] 프론트 번들 코드 스플리팅(단일 청크 약 1MB)
- [ ] `frontend/src/features/placeholder/` 미사용 컴포넌트 정리
- [ ] `db_init.sql`를 현행 모델(25종)에 맞게 갱신하거나 참고용임을 명확화

## 기술 스택

- 프론트엔드: React 19 + TypeScript + Vite + Tailwind CSS v4, react-router-dom 7, @tanstack/react-query, axios, Phosphor Icons
- 백엔드: Python 3.9 + FastAPI 0.115 + SQLAlchemy 2.0, PostgreSQL 15(운영) / SQLite(테스트)
- 인프라: Docker 멀티스테이지 빌드, Cloud Build → Cloud Run
