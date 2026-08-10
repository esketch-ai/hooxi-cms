# Project & Finance 확장 설계서

> 상태: **설계 확정(구현 전)** · 작성일 2026-08-10 · 대상: 감축사업(Project) + 정산(Finance)
> 목적: 경영전략실이 프로젝트별 **매출(증권사 매각) · 지급(운수사) · 진행단계/지연**을 관찰·대응하고,
> 투자사에게 **프로젝트별 지정 공개** 페이지를 제공한다.
> 규약: 공통 분류/상태는 tb_code(하드코딩 금지), 배포 테이블 컬럼 추가 시 `ensure_schema` 반영,
> 감사 로그에 비밀값 금지(R2-E6), 금액·보수율은 보안모드 마스킹(SensitiveData).

---

## 0. 확정 결정사항 (2026-08-10)

| 항목 | 결정 |
|---|---|
| 자금 흐름 | **매출·지급 2원장 + 보수 = 매출−지급(차액)**. 기존 '성공보수 청구' 정산은 Phase 3에서 이 구조로 재편/대체 |
| 투자사 공개 | **프로젝트별 지정 공개** — 관리자가 투자사↔프로젝트·공개 항목을 지정 |
| 진행 단계 | **경량: 5단계 + 예정일/실제일** (마일스톤 다건 아님) |
| 착수 순서 | **Phase 1(단계·지연 관찰) → Phase 2(매출) → Phase 3(지급·보수 재편) → Phase 4(투자사/관찰자 권한)** |

---

## 1. 현행 구조 요약 (근거)

- **Project** `tb_project` (`backend/models.py:160-183`): `project_status`(문자열 1개, 공통코드 PROJECT_STATUS: 기획·등록완료·모니터링·검증·발급완료), `unit_price`(수기 단가), `expected_credits`, `issued_credits`, 각종 일자(reg/credit/mon/expected_issue). `price_source` default MANUAL(MARKET 예약, 미사용). `client_id`=묶음 사업 대표사.
- **ProjectClientMap** `tb_project_client_map` (`models.py:186-209`): 사업 참여 운수사 슬롯 = 정산 단위. `allocation_ratio`(배분율%), `success_fee_rate`(성공보수율%), `expected_amount`(서버계산), `settlement_status`(STANDBY→BILLED→COMPLETED), `billed_*`/`completed_*`/`paid_amount`/`payment_type`.
- **SettlementSnapshot** `tb_settlement_snapshot` (`models.py:437-460`): append-only 회차 이력, 5요소 동결(issued_credits·amount·unit_price·allocation_ratio·success_fee_rate), action(BILLED/REBILLED/REVERTED/COMPLETED).
- **정산 산식** `compute_expected_amount` (`backend/routers/common.py:184-198`):
  `예상정산액 = expected_credits × (allocation_ratio/100) × unit_price × (success_fee_rate/100)`
  → **성공보수율이 곱해지므로 = 후시가 운수사에게 청구하는 성공보수(수수료)**. 순수 배출권 매각대금이 아님.
- **상태 머신** (`backend/routers/settlements.py`): `_TRANSITIONS={STANDBY:BILLED, BILLED:COMPLETED}`, 청구취소 `BILLED→STANDBY`(ADMIN). 낙관적 동시성 조건부 UPDATE + 스냅샷 append + `AuditLogger.settlement_change`.
- **권한** (`backend/auth.py`): `ROLE_LEVEL={STAFF:1,MANAGER:2,ADMIN:3}`, `PERMISSION_MATRIX`(crm.read_write, master.write, settlement.change[MANAGER↑], client.delete[MANAGER↑], admin.users_config_backup[ADMIN], asset.reveal_auth[MANAGER↑]). 판정은 항상 DB의 user.role. **라우터 역할 가드 없음**(인증만) — 통제는 nav 노출 + 페이지 인라인 `user.role` 체크.
- **문서** `tb_document` (`models.py:327-351`): FK는 client/report/history/asset만. **project/map/거래 증빙 FK·엔드포인트 없음.**
- **결론(돈의 방향)**: 현행은 **운수사→후시(성공보수 수취) 단일 방향**. 증권사 매각 매출·후시→운수사 지급·단계 지연·투자사 권한은 **전무**.

**재사용 자산**: SettlementSnapshot append-only + 5요소 동결 패턴, `_TRANSITIONS` 상태전이 사전, `AuditLogger` 중앙 경로, `SensitiveData` 마스킹.

---

## 2. 목표 도메인 — 자금 흐름 3갈래

```
① 매출(INBOUND)   증권사 ──매각대금 R──▶ 후시     [세금계산서(후시 발행)·입금·매출인식]
② 지급(OUTBOUND)  후시   ──배분대금(net)─▶ 운수사   [지출세금계산서(운수사 발행)·송금·확인서]
③ 후시 보수        = R − Σ지급 = Σ(운수사 배분 × 보수율)
```

**통합 산식(신규)** — 매각 실적(R) 기준으로 재정의:
- 프로젝트 매출 `R = Σ 매각거래 금액` (증권사, 세금계산서/입금 기준).
- 운수사 i 배분(gross) = `R × allocation_ratio_i/100`.
- 후시 보수 i = `gross_i × success_fee_rate_i/100`.
- **운수사 i 지급액(net) = gross_i − 보수_i = R × ratio_i/100 × (1 − fee_i/100)**.
- **후시 총보수 = Σ보수_i = R − Σ지급액**.

→ 기존 `allocation_ratio`·`success_fee_rate`를 그대로 재사용. 차이는 "발행량×수기단가"가 아니라 **실제 매각대금 R**을 기준으로 삼는 것. 기존 `compute_expected_amount`(발행량×단가×보수율)는 **매각 전 예상치**로만 남기고, 확정은 매각 실적 기반으로 이관(Phase 3).

---

## 3. 데이터 모델 설계 (전 Phase)

> 모든 신규 테이블: PK는 UUID 문자열(gen_uuid), created_at/updated_at 포함, `ensure_schema` 반영, 상태값은 tb_code.

### 3.1 진행 단계 `tb_project_stage` (Phase 1)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| stage_id | PK | |
| project_id | FK→tb_project | |
| stage_code | String | PROJECT_STATUS 5값 재사용(기획…발급완료) |
| planned_date | Date? | 예정일(수기) |
| actual_date | Date? | 실제 도달일(상태 전이 시 자동 or 수기 소급) |
| sort_order | Int | 단계 순서 |

- 사업 생성 시 5행 자동 시드(예정일 비움).
- **지연 판정(파생)**: `planned_date < today AND actual_date IS NULL`.
- 신규 공통코드 불필요(PROJECT_STATUS 재사용). `USAGE_REFS` 영향 없음.

### 3.2 매각(매출) 원장 `tb_project_sale` + `tb_project_sale_snapshot` (Phase 2)
`tb_project_sale`: project_id FK, `buyer`(증권사명; 추후 거래처 마스터로 승격 가능), `sale_credits`(매각수량), `sale_unit_price`, `sale_amount`(=수량×단가, 서버계산·검증), `status`(공통코드 SALE_STATUS: 예정→세금계산서발행→입금완료), `tax_invoice_no`/`tax_invoice_date`, `deposit_date`/`deposit_amount`, `memo`.
- 상태 머신 `_TRANSITIONS` 패턴 재사용. 세금계산서 발행/입금 시점 동결 → snapshot(append-only, action=ISSUED/DEPOSITED/REVERTED).
- 증빙(세금계산서·입금확인) = §3.5 문서 연결.

### 3.3 지급 원장 `tb_project_payout` + `tb_project_payout_snapshot` (Phase 3)
`tb_project_payout`: project_id FK, `map_id` FK→tb_project_client_map(운수사), `gross_amount`(R×ratio), `fee_amount`(보수), `net_amount`(지급액), `status`(공통코드 PAYOUT_STATUS: 예정→세금계산서수취→송금완료), `expense_invoice_no`/`date`(운수사 발행 지출세금계산서), `remit_date`/`remit_amount`, `confirm_doc`(확인서), `memo`.
- 매출 원장(R)과 배분율에서 파생 계산. 확정 시 snapshot 동결.
- **기존 정산 재편**: `settlement_status`(성공보수 청구)를 이 지급/보수 구조로 흡수. 기존 데이터 마이그레이션 전략은 Phase 3 착수 시 별도 설계(스냅샷 보존).

### 3.4 투자사 접근 `tb_investor_access` (Phase 4)
| 컬럼 | 설명 |
|---|---|
| access_id PK | |
| investor_user_id FK→tb_user | 역할 INVESTOR 사용자 |
| project_id FK→tb_project | 공개 대상 프로젝트 |
| sections | 공개 항목 집합(예: progress/sales_summary/payout_summary/docs) |
| granted_by / granted_at | 부여 감사 |

- 투자사는 **부여된 프로젝트·항목만** 읽기 전용. 미부여 프로젝트는 목록에서도 비노출.

### 3.5 증빙 문서 연결 (Phase 2~3)
- `tb_document`에 `project_id`(+선택적 `sale_id`/`payout_id`) 연결 신설, 또는 경량 연결 테이블. `doc_type`에 TAX_INVOICE/DEPOSIT_PROOF/EXPENSE_INVOICE/REMIT_PROOF/CONFIRM 확장.
- 업로드/열람은 기존 Document·Dropbox 파이프라인 재사용. 폴더 분류(CLIENT_FOLDER)에 SETTLEMENT/정산 폴더 이미 존재.

---

## 4. 진행 단계·지연 관찰 (Phase 1 핵심)

- **단계 타임라인**: 사업 상세에 5단계 예정/실제/지연 배지.
- **지연 판정**: §3.1. 프로젝트 지연 = 지연 단계 ≥ 1.
- **관찰 대시보드 위젯**(신규): (a) 지연 단계 보유 사업 목록, (b) 임박(D-임박) 단계, (c) 향후 재무 요약(Phase 2~3에서 매출/미입금/미지급 추가).
- Phase 1에선 MANAGER/ADMIN이 관찰. 전용 OBSERVER/INVESTOR 역할은 Phase 4.

---

## 5. 권한/역할 설계 (Phase 4)

- 신규 역할:
  - **OBSERVER(경영전략실)** — 전 프로젝트 **읽기전용 관찰**(진행·지연·재무 요약 대시보드). 편집 불가.
  - **INVESTOR(투자사)** — `tb_investor_access`로 **지정된 프로젝트·항목만** 읽기전용.
- 손대야 할 지점:
  - 백엔드: `auth.py` `ROLE_LEVEL`·`PERMISSION_MATRIX`에 신규 역할·읽기전용 권한키(예: `project.observe`, `investor.read`) 추가. JIT 가입 기본 STAFF 유지, 승인 시 역할 부여.
  - **라우터 역할 가드 신설**(현재 없음): `frontend/src/app/router.tsx`에 역할 기반 가드 도입(현재는 인증만). 페이지 인라인 체크로는 신규 외부 역할 통제 불충분.
  - 프론트: `types/index.ts` `UserRole` 확장, `nav.ts` roles·`Sidebar.tsx` 필터, `SettingsPage` 역할 드롭다운.
- **보안**: 투자사/관찰자 응답에서 운수사 지급 상세·보수율 등 내부 원가는 접근 항목(sections)에 없으면 서버가 제외(마스킹이 아니라 미포함). R2-E6 준수.

---

## 6. Phase별 착수 정의

### Phase 1 — 단계·지연 관찰 (착수 대상)
**성공 기준**
1. 각 사업 5단계에 예정일 입력 가능.
2. 상태 전이 시 실제일 자동 기록(과거 단계 소급 입력 허용).
3. 예정일 경과 & 미도달 → 지연 자동 판정, 상세·목록·대시보드 위젯 표시.
4. pytest(지연 판정·시드) + 프론트 빌드 통과.

**작업**: `tb_project_stage` 모델 + ensure_schema + 5행 시드 → 사업 상세 응답 확장·`PUT /projects/{id}/stages` → 상태전이 시 actual_date 자동 → 대시보드 집계 API → 프론트 3화면(사업상세 타임라인·목록 표식·대시보드 위젯).

**규약 체크**: PROJECT_STATUS 재사용(신규 코드 없음), ensure_schema 반영, 감사(단계 예정일 변경 audit), 보안(단계 정보는 비민감).

### Phase 2 — 매출 원장
매각거래 CRUD + 상태 머신 + 스냅샷 + 세금계산서/입금 증빙 첨부. 대시보드 재무요약에 매출·미입금 추가. 신규 코드 SALE_STATUS.

### Phase 3 — 지급 원장 + 보수 재편
매출 R 기반 배분/보수/지급 계산 + 지급거래 상태 머신 + 지출세금계산서/송금/확인서. **기존 성공보수 정산 흡수·마이그레이션**(스냅샷 보존). 신규 코드 PAYOUT_STATUS.

### Phase 4 — 투자사/관찰자 권한 페이지
역할 2종 + 라우터 가드 + `tb_investor_access` + 투자사 전용 읽기 페이지(지정 프로젝트·항목). 관찰자 대시보드 정식화.

---

## 7. 추후 확정 필요(Phase 착수 시 상세화)
- Phase 2: 증권사를 단순 문자열 vs **거래처 마스터** 승격 여부. 매출 인식 시점(세금계산서 vs 입금).
- Phase 3: 기존 `ProjectClientMap.settlement_status`/스냅샷 **마이그레이션 전략**(기존 청구/입금 데이터의 신모델 매핑). 부분 매각·다회 매각 시 지급 재계산 규칙.
- Phase 4: 투자사 계정 발급/온보딩 흐름(외부인 로그인·PIN 정책), 감사 로그에 투자사 열람 이력 기록 범위.
- 공통: 통화/부가세(VAT) 처리, 반올림 규칙, 금액 상한(Numeric(15,2)) 재검토.

---

## 8. 재사용 체크리스트 (개발 시)
- 상태 머신: `_TRANSITIONS` 사전 + 낙관적 동시성 조건부 UPDATE (`settlements.py:225-238`).
- 이력: append-only 스냅샷 + 요소 동결 (`SettlementSnapshot`).
- 감사: `AuditLogger` 중앙 경로(금액 원문 미기록).
- 마스킹: 프론트 `SensitiveData`(rate/money).
- 문서: Document + Dropbox 폴더 파이프라인.
