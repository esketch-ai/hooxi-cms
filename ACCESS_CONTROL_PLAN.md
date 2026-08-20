# 접근권한 재편 계획 — 외부(고객사·투자사) 포털 + 내부 그룹(부서·경영진) 메뉴 권한

> 목적: ① 고객사(운수사)·투자사가 로그인하면 **자기 전용 페이지로 자동 진입**하고 허용된
> 것만 보게 한다. ② 내부 사용자는 **부서 그룹·경영진 그룹**에 따라 **허용된 메뉴만**
> 보이고 접근되게 재편한다.
>
> 작성: 2026-08-21. 상태: **설계 검토안(구현 전)**. 관련: 부록 N.8(외부 포털),
> observerAccess.ts(OBSERVER 격리), auth.PERMISSION_MATRIX.

---

## 0. 현행 실사 (2026-08-21 코드 기준)

### 이미 있는 것 (재사용 대상 — 새로 만들지 않음)
| 요소 | 현행 | 위치 |
|---|---|---|
| **외부 포털** | PARTNER(운수사)·INVESTOR(투자사) 역할, 완전 격리(EXTERNAL_ROLES — 내부 API 전면 차단, 내부역할은 포털 API 차단) | auth.py, routers/portal.py |
| **외부 로그인·자동 뷰** | 매직링크(`/portal/login?token=`) → 검증 → `/portal` 자동 랜딩. 이메일(주)+알림톡(폴백) 발송 | external_accounts.py, PortalLoginPage |
| **외부 페이지** | 프로젝트 목록/상세/감축량 타임라인. PARTNER=자기 운수사 것만(예상지급액 포함), INVESTOR=자기 매수 프로젝트(감축량만, 지급액·타사 미노출) | PortalProjectsPage 등 |
| **발급 UI** | /portal-accounts(ADMIN·MANAGER): 계정 생성·링크 재발급·비활성 | portal-admin |
| **내부 역할(직급)** | STAFF(1)<MANAGER(2)<ADMIN(3) + 기능키 PERMISSION_MATRIX(master.write 등 6종) | auth.py |
| **OBSERVER(경영전략실)** | 경로 화이트리스트 격리(프론트 observerAccess.ts + 백엔드 OBSERVER_SCOPE) — "그룹형 접근제어"의 선행 사례 | auth.py·AppShell |
| **메뉴 레지스트리** | NAV_GROUPS(약 24메뉴) — 항목별 `roles` 필터 이미 지원 | AppShell/nav.ts |
| **로그인 홈 분기** | RoleHome: OBSERVER→/observe, 그 외→/dashboard | app/router.tsx |

### 없는 것 (이번에 만드는 것)
- **부서/경영진 "그룹" 축** — 현행 role은 직급이지 부서가 아님. 메뉴↔그룹 매핑 없음.
- 그룹 관리·메뉴 배정 **관리 화면**.
- 그룹 기준 **백엔드 API 강제**(현재는 OBSERVER만 경로 격리).
- 외부 포털의 **콘텐츠 확장**(계약대수·보고서 등 — §3).

### 설계 원칙 (검토 결론)
1. **두 축 분리**: `role(직급)` = 행위 권한(쓰기·삭제·승인) 유지, `group(부서)` = **메뉴(화면) 접근** 담당. 직급 매트릭스는 손대지 않는다(회귀 0).
2. **외부는 현행 격리 구조 유지** — PARTNER/INVestor에 그룹 개념을 섞지 않는다(격리 상수 불변).
3. **fail-safe**: ADMIN은 그룹과 무관하게 전체 접근(락아웃 방지). 그룹 미배정 내부 사용자는 '전사(기본)' 그룹.
4. **점진 적용**: `enforce 모드 3단계(off→monitor→enforce)` — 배포 즉시 아무도 안 막히고, 모니터로 검증 후 강제.
5. 메뉴 키는 **nav.ts 경로 = 단일 원천**. 백엔드는 menu_key→API 프리픽스 매핑 1곳(OBSERVER_SCOPE 일반화).

---

## 1. 데이터 모델 (신규 — G1)

### 1.1 `tb_access_group` — 접근 그룹(부서·경영진)
- `group_id`(PK) · `name`(예: 경영진, 경영전략실, 자산관리, 정산·재무, 사업운영, 시스템관리)
- `home_path`(로그인 랜딩, 예: /dashboard, /observe) · `is_default`(전사 기본 여부)
- `memo` · `created_at/updated_at`

### 1.2 `tb_group_menu` — 그룹 × 메뉴 허용
- `group_id`(FK CASCADE) + `menu_key`(nav 경로: '/clients', '/settlements' …) 복합 PK
- menu_key 유효성은 MENU_REGISTRY로 검증(오타 방지)

### 1.3 `tb_user_group` — 사용자 × 그룹 (N:M)
- `user_id`(FK CASCADE) + `group_id`(FK CASCADE) 복합 PK
- **N:M 채택 이유**: 겸직(부서+경영진)·전환기 이중 소속이 현실적으로 존재. 허용 메뉴는 소속 그룹의 **합집합**.

### 1.4 시드(ensure_schema + seed)
- '전사' 그룹(is_default) = 전 메뉴 허용, **기존 내부 사용자 전원 자동 배정** → 배포 직후 화면 변화 0(회귀 0).
- '경영진' 그룹 프리셋: 통합 현황판·경영 관찰·재무 원장·자산관리 보고·전기버스 자산·감축 사업(읽기) — §5 결정 후 확정.
- tb_config `access_control_mode` = off(기본) → monitor → enforce.

---

## 2. 내부 그룹 접근제어 — 단계(G)

### G1. 모델·시드 (백엔드)
위 3테이블 + ensure_schema + 시드. `GET /users/me` 응답에 `groups[]`·`allowed_menus[]`·`home_path` 포함(프론트 단일 소스). 테스트: 시드·합집합·기본그룹.

### G2. 백엔드 강제 (OBSERVER 가드 일반화)
- `MENU_REGISTRY = { '/clients': ['/api/v1/clients', '/api/v1/imports/…'], … }` — 메뉴키→API 프리픽스 단일 원천(공통 API `/users/me`·`/codes`·`/auth` 등은 전역 허용 목록).
- get_current_user 이후 훅: `mode=enforce`일 때 내부 사용자(비ADMIN)의 요청 경로가 소속 그룹 허용 메뉴의 API 집합 밖이면 403. `mode=monitor`면 차단 없이 감사 로그(`ACCESS_DENY_WOULD`)만.
- OBSERVER는 **현행 그대로**(전환기) — 추후 '경영전략실' 그룹으로 이관하는 별도 단계(G6, 선택).
- 테스트: 역할×그룹×모드 매트릭스, 외부역할 격리 불변 회귀.

### G3. 관리 UI (설정 화면 확장 — 새 메뉴 없음)
- /settings에 '접근 그룹' 탭(ADMIN): 그룹 CRUD + **메뉴 체크박스 매트릭스**(nav 그룹별) + 홈 경로 지정.
- 사용자 관리 탭에 그룹 배정 멀티셀렉트 추가. 모드 전환(off/monitor/enforce) 스위치 + monitor 히트 요약.

### G4. 프론트 메뉴·라우트 가드
- Sidebar: `visibleNavGroups()`에 allowed_menus 필터 추가(기존 roles 필터와 AND).
- 라우트 가드: 허용 밖 경로 진입 시 그룹 home_path로 리다이렉트(OBSERVER 가드와 같은 관용구).
- **로그인 자동 뷰**: RoleHome 확장 — 외부(기존 /portal), OBSERVER(기존 /observe), 내부는 `home_path`(소속 그룹 중 우선순위 최상, 기본 /dashboard).
- nav.test 확장(그룹 필터), 가드 단위 테스트.

### G5. 경영진 그룹 적용
- '경영진' 프리셋 그룹 시드 + 실제 임원 계정 배정(사용자 작업) + monitor 1주 → enforce.
- (§5-Q3에 따라) 경영진이 쓰기까지 가능하면 직급 MANAGER/ADMIN 부여로 해결(그룹은 메뉴만).

### (선택) G6. OBSERVER → 그룹 이관
경영전략실 그룹으로 화이트리스트 대체, OBSERVER role 은퇴. 위험 낮추려 마지막에.

---

## 3. 외부 포털 확장 — 단계(P)

> 로그인·자동 뷰·격리·발급은 **이미 완성**. 이번 범위는 "보여줄 내용"의 확장이다.

### P1. 운수사(PARTNER) 페이지 확장 — 후보(§5-Q4에서 확정)
- **계약대수 현황**(자기 회사): 월별 대수·차종 추이(tb_fleet_status 재사용, F3 화면 포털판).
- **월간 보고서 열람**: 발송된 보고서 파일 열람(기존 reports 산출물, PORTAL_VIEW 감사).
- **정산 내역**: 확정 정산 요약(예상지급액은 현행 포털에 이미 노출 중).
- 구현: portal.py에 read-only 라우트 추가(자기 client_id 필터 필수), PortalShell 메뉴 확장.

### P2. 투자사(INVESTOR) 페이지 확장 — 후보
- 프로젝트 진행 단계(tb_project_stage 재사용)·감축량 추이(현행 유지).
- **매입/보유 현황 요약** — ⚠ 미결: total_contract_revenue 교차추론 이슈(부록 N.8 미결)와 탄소배출권 원가·재고 정밀화(CARBON_CREDIT_COST_INVENTORY_PLAN) 확정 후 노출 범위 결정.

### P3. 로그인 방식(§5-Q5)
현행 = 매직링크(무비밀번호). 대안 = ID/PW 추가. **권고: 매직링크 유지**(비밀번호 관리·유출 리스크 제거, 이미 알림톡/이메일 발송 연동 완료). 필요 시 링크 유효기간·재발급 UX만 보강.

---

## 4. 보안 검토 체크리스트 (구현 시 검증 항목)
1. 외부 격리 불변: EXTERNAL_ROLES ↔ 내부 API 상호 차단 회귀 테스트(기존 스위트 유지).
2. 그룹 판정은 **DB 기준**(JWT에 그룹 미포함 — 배정 변경 즉시 반영, token_version 불필요).
3. ADMIN 락아웃 방지: ADMIN 전역 우회 + '전사' 기본그룹 삭제 금지 가드.
4. enforce 전환 전 monitor 로그로 오차단 0 확인(감사 로그에 경로만, 비밀값 금지 R2-E6).
5. 메뉴 숨김 ≠ 보안 아님 — G2 백엔드 강제가 본질(프론트는 UX).
6. 포털 신규 라우트는 전부 자기 스코프 필터(client_id/buyer_id) 강제 + PORTAL_VIEW 감사.

## 5. 결정 필요 (착수 전 확인)
| # | 질문 | 권고안 |
|---|---|---|
| Q1 | 부서 그룹 구성(이름·수) — 초기 시드? | 전사(기본)·경영진·경영전략실·자산관리·정산재무·사업운영·시스템관리 7종 시드 후 관리 UI에서 조정 |
| Q2 | 1인 다그룹 허용? | **허용(N:M)** — 겸직 현실 반영, 허용 메뉴는 합집합 |
| Q3 | 경영진 그룹 성격 | **메뉴만 그룹으로, 쓰기는 직급으로**(현행 매트릭스 유지) — 읽기전용이 필요하면 OBSERVER 사례처럼 별도 |
| Q4 | 포털 확장 콘텐츠 우선순위 | P1 운수사: 계약대수 현황 → 보고서 열람 → 정산 順 |
| Q5 | 외부 로그인 방식 | **매직링크 유지** |
| Q6 | enforce 시점 | 배포 후 monitor 최소 3일, ADMIN 확인 후 전환 |

## 6. 실행 순서·검증(4원칙)
- 각 단계 성공 기준: pytest(가드 매트릭스·시드·회귀) + 프론트 빌드·vitest + dev 스모크.
- 순서: **G1→G2(monitor)→G3→G4→(사용자 그룹 배정)→enforce→G5** 후 **P1→P2**. P는 G와 독립이라 병행 가능.
- 배포: dev에서 monitor 검증 후 운영 반영(운영 배포는 사용자 "배포" 명시 시).
