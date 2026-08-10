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

---

# 부록 — 실무 엑셀 `배출권관리시스템_v19.3_final_260806.xlsx` 정본 분석

> 출처: `Docs/배출권관리시스템_v19.3_final_260806.xlsx` (v19.3, 최종 2025-01-23). 10탭·차량 5,220대·운수사 189·프로젝트 17.
> **주의(사용자 지적)**: 이 엑셀은 만들어졌으나 실무자가 거의 안 씀 — 10탭 5,000행+이 VLOOKUP/SUMIF로 상호 참조돼 **참조 밀림 오류·검증 부재·권한/통제 부재**로 컨트롤이 안 됨(검수 이력에 실제 참조 밀림 버그 다수). CMS는 **이 산식을 정합성 정본으로만 채택**하고, **UX는 이벤트 입력+자동 계산+통제**로 완전히 새로 설계한다.

## A. 엔티티·자금 방향 (정본)
```
차량(감축량·예상지급액) → 프로젝트 → [프로젝트-계약 배분(소유권비율)] → 거래계약(구매자: 증권사 등)
운수사 ── 매입세금계산서(운수사→후시 발행) ──▶ 후시  = 후시의 '매입/원가' = 운수사 지급(제품)
후시   ── 매출세금계산서(후시→구매자 발행) ──▶ 구매자 = 매출
```
- **매입세금계산서 = 운수사 지급(원가/제품)**. **매출세금계산서 = 매각 매출.** (내 초안의 지급원장=매입세금계산서, 매출원장=매출세금계산서).
- **거래계약(구매자)** = 판매비율·단가·리스크프리미엄율·할인율을 가진 판매 계약. 실측 예: 현대차증권1차(단가 25,000, 프리미엄 5%, 할인 9%), 에쓰오일(60%, 14,382), 이에스지카본(89%, 22,500). **HXI001=후시파트너스(미확정/후시보유)** = 아직 안 판 잔량 슬롯.

## B. 회계 로직 정본 (셀 수식 근거 — 서버가 자동 계산할 것)
| 값 | 산식(엑셀) | 의미 |
|---|---|---|
| 미착품(1) | 승인 전 → 예상지급액, 아니면 0 | 승인 전 잠정 지급의무 |
| 미착품(2) | 승인 후 → `예상지급액 − 매입세금계산서`, 아니면 0 | 승인 후 남은 지급의무 |
| 부채 | 미착품(1)+미착품(2) | |
| 제품 | 매입세금계산서금액 | 확정 원가(=운수사 지급 실행분) |
| 재고자산 | 부채+제품 | (≈ 예상지급액 총액) |
| **지급률** | `제품 ÷ 예상지급액` | 운수사 지급 진행률 |
| **매출인식** | `매출세금계산서 × 지급률` | 지급 진행률만큼만 매출 인식(매칭 원칙) |
| 매출이익 | `매출인식 − 제품(매입)` | (내 초안 '보수=매출−지급'의 정확형) |
| 이익률 | 매출이익 ÷ 매출인식 | |

- **차량별 예상지급액**: 연차감축량(1~10년차) → `10년총감축량=SUM`, `잔여차령=MIN(기준차령, (차령만료일−승인일)/365)`, `잔여반영감축량=MIN(기준감축량 240톤, Σ 연차감축량×잔여차령가중)`, `예상지급액 = MIN(감축량기반, 최대지급액 200만원)`. 기준값(기준감축량/기준차령/최대지급액)은 **프로젝트별 설정**.
- **월별 재무(7_월별현황)**: 발행일 기준 월 버킷. `누적지급률 = 누적매입 ÷ 총예상지급액`. 월손익 = 월매출인식 − 월매출원가(제품).
- **롤업(대시보드)**: 미인식 매출(=총매출세금계산서−총매출인식), 미지급(=총예상지급액−총매입), 재고자산, 매출이익률, **거래계약별 매출 현황표**.

## C. 엣지케이스 (설계 시 반드시 반영)
1. **다계약 배분**: 한 프로젝트를 여러 거래계약에 **소유권비율**로 배분(합계 100%). 미판매분은 **HXI001(후시보유)** 슬롯에 귀속. (예: 후시003 = 에쓰오일1차 60% + 후시보유 40%).
2. **부분 매각**: 거래계약 판매비율<100% → 나머지 후시보유. 매출세금계산서는 판 만큼만.
3. **부분 지급/분할지급**: 매입세금계산서가 예상지급액 미만이거나 여러 건(분할) → **지급률<100% → 매출인식도 비례 축소**. (예: NWK002 매출 6.06억 × 지급률 67.8% = 매출인식 4.11억).
4. **매출세금계산서 = 실제 발행액 수기입력**(단가·프리미엄·할인은 **참고/제안값**, 자동 확정 아님). CMS는 `배분감축량×단가×(1+프리미엄)×(1−할인)`을 **제안값으로 자동 계산**해 보여주되 실입력을 우선.
5. **승인 상태 전환**: 신청→승인 시 미착품(1)→(2) 전환. 상태가 회계에 직접 영향.
6. **차량 대량 데이터**: 5,000행+ → 수기 불가. **엑셀 업로드(기존 imports 파이프라인 확장)** + 서버 감축량/예상지급액 산식.

## D. UX 설계 원칙 (핵심 — "실무자가 실제로 쓰게")
엑셀 실패 원인(복잡·비통제)을 뒤집는다.

- **① 이벤트만 입력, 나머지는 자동**: 실무자는 4가지 이벤트만 입력 —
  (a) 프로젝트 신청/승인(상태 전이), (b) **매입세금계산서**(운수사 지급) 등록, (c) **매출세금계산서**(매각) 등록, (d) 차량 데이터 업로드.
  → 미착품·부채·제품·지급률·매출인식·이익은 **서버가 전부 자동 계산·저장**. 사용자는 수식/참조를 절대 만지지 않음.
- **② 계산 근거 투명화**: 각 자동값 옆에 "왜 이 값인가"(지급률 67.8% = 매입 4.1억 ÷ 예상 6.1억) 툴팁/드릴다운.
- **③ 통제(엑셀엔 없던 것)**: 상태 머신(신청→승인→매입발행→매출발행) + **배분 합계 100% 검증**·지급률 0~100%·금액 상한·**권한**·**감사 로그**·낙관적 동시성. "참조 밀림" 류 오류 원천 제거.
- **④ 관찰 중심 화면**: 대시보드/월별현황을 **읽기 화면**으로 재현 — 미인식 매출·미지급·재고자산·월별 손익·거래계약별 현황을 경영전략실이 한눈에(Phase 4 관찰자/투자사 뷰의 토대).
- **⑤ 프로젝트 1화면 통합**: 프로젝트 상세에서 [단계/지연] · [운수사 지급(매입세금계산서)] · [매각(거래계약·매출세금계산서)] · [회계 요약(재고자산·지급률·매출인식·이익)]을 탭으로. 10개 시트를 오갈 필요 없음.

## E. Phase 스펙 정밀화 + 순서 재검토
**엑셀→CMS 데이터 모델 매핑**
| 엑셀 | CMS 모델(§3) |
|---|---|
| 4_거래계약DB | 신규 `tb_sale_contract`(구매자·판매비율·단가·프리미엄·할인) |
| 프로젝트-계약매핑 | 신규 `tb_project_sale_alloc`(프로젝트×거래계약 소유권비율) — §3.2 tb_project_sale를 이 구조로 확장 |
| 매출세금계산서(매핑 O/N) | `tb_project_sale`의 매출 인보이스(발행일·금액) |
| 매입세금계산서DB | §3.3 `tb_project_payout`(프로젝트×운수사 지급 인보이스, 분할 지원) |
| 1_차량DB | 신규 `tb_project_vehicle`(감축량·예상지급액) + 엑셀 업로드 |
| 3_프로젝트DB 집계 | 서버 파생(저장 or 뷰): 미착품/부채/제품/지급률/매출인식/이익 |
| 6_대시보드·7_월별현황 | 관찰 대시보드 API |

**⚠️ 회계 의존성으로 인한 Phase 순서 재검토(중요)**:
매출인식 = 매출 × **지급률**, 지급률 = 매입 ÷ **예상지급액**(차량 기반). 즉 **매출인식은 [차량·예상지급액]→[매입세금계산서(지급)]가 선행돼야 성립**한다. 따라서 초안의 "Phase 2 매출 먼저 → Phase 3 지급"은 회계적으로 역순. **권고 조정**:
- Phase 1 = 단계·지연(변경 없음, 재무 독립).
- **Phase 2 = 원가/지급 축**(차량 업로드+예상지급액 → 매입세금계산서(운수사 지급) → 미착품·제품·부채·지급률).
- **Phase 3 = 매출 축**(거래계약·배분 → 매출세금계산서 → 매출인식=매출×지급률 → 이익) + 월별/대시보드 재무.
- Phase 4 = 투자사/관찰자 권한(변경 없음).

이 조정은 착수 시 사용자 확인 후 확정한다.
