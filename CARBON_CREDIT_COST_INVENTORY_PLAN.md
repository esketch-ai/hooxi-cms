# 탄소배출권 원가·재고·매출 정밀화 — 설계서

> 목적: 감축사업의 **탄소배출권 수량·가격·원가·매출·손익**을 프로젝트 생애주기(신청중/승인)에
> 맞춰 일관 추적한다. 카본크레딧실 실무 엑셀(`Docs/재고자산 및 미착품 관리_26.08.06_V.01`)을
> 정본으로 삼아 현행 회계 모델을 정밀화한다.
>
> 작성: 2026-08-20. 상태: **설계 정리(구현 전, 사용자 '나중' 선택)**.
> 관련: [매출·지급 2원장] `PROJECT_FINANCE_EXPANSION_PLAN.md` · [세금계산서 HTML] `TAX_INVOICE_HTML_IMPORT_PLAN.md`

---

## 0. 확정 결정 (사용자)
| 항목 | 결정 |
|---|---|
| 원가(cost) 정의 | **운수사 지급액 기준**(= 시스템 `expected_payout` 산식). 매입세금계산서 발행액 합이 아님. |
| 승인시점 가격 | **승인 시 시세 스냅샷(잠금)**. 신청중=6개월 평균가, 승인=잠금가로 산식 분기. |
| 보유(재고자산) | **미매각분**(엑셀 L열 = 후시가 확보했으나 아직 증권사/투자사에 안 판 분량). |
| 정리 방식 | 본 설계서로 통합 정리. 개발 착수는 사용자 지시 시. |

---

## 1. 실무 엑셀 모델 (정본, `26.07.31_배출권 관리` 시트)

**단가 2종(상단 고정)**: 기준단가(매출) **20,000원/톤** · 원가단가 **13,888원/톤**

**사업번호별 컬럼**
| 열 | 의미 | 시스템 대응 |
|---|---|---|
| B | 사업번호(NWK001…) | Project |
| C/D | 신청일 / 사업승인일 | (승인일=상태전이 기준) |
| E | 진행경과(사업승인·타당성 평가·환경부 협의…) | approval/project status |
| F | 계약업체(현대차증권·이에스지카본…) | 매각처(투자사/증권사) = Buyer |
| G | 계약내용(**100% 매각·89% 매각·100% 후시 보유·수익쉐어 예정**) | **매각률(신규)** |
| H | 차량대수 | vehicle_count |
| I | 사업승인 감축량(10년) | 확정 감축량 |
| J | 잔여차령 | remaining_age |
| K | **잔여차령 반영 총 감축량** | `effective_reduction` |
| L / M | 배출권 소유량 = **후시 보유** / **계약업체(매각)** | 매각률로 분할(신규) |
| N | **매출** = 매각분 실매각액 / 후시보유분은 보유량×원가단가(재고평가) | sale/재고평가 |
| O | **원가**(운수사가 받을 돈, 부가세 미포함) = `((K/H)/240)×(J/8)×H×200만` | **= `expected_payout` 산식(일치)** |

**하단 분류**: 사업승인 = **재고자산**(후시 보유분 L 평가), 미승인/타당성평가 = **미착품**(예상), 선급금 별도, 총계.

**핵심 등식**
- 원가 O = 운수사 지급액 = `max_payment(200만) × (effective_reduction/기준감축량240) × (잔여차령/8)` — 시스템 `expected_payout`와 동일.
- 소유량 K = 후시보유(L) + 매각(M). 매각률(G)로 분할(100%매각→M=K,L=0 / 89%매각→M=0.89K / 100%보유→L=K).
- 매출 = 매각분(M) 실매각액. 재고자산 평가 = 후시보유분(L) × 원가단가.

---

## 2. 현행 시스템 정합 & 갭

**이미 있음(재사용)**
- ✅ 원가 산식 = `expected_payout`(`routers/projects.py::_expected_payout`). 원가=지급액 정의와 일치.
- ✅ 미착품(미승인)/재고자산(승인) 분류 = `compute_accounting`가 `approval_status`로 wip/inventory 분기(`services/accounting.py:52-55`).
- ✅ 잔여차령 반영 감축량 = `effective_reduction`. 6개월 평균가 = `trailing_avg_rate`(예상수익에 사용).

**갭(신규 필요)**
1. **매각률(%) 기반 소유량 분할** — 현재 매각은 `ProjectSale.is_hold`(Y/N)·`ownership_pct`만. 후시 보유량(L)/매각량(M)을 매각률로 산출·표시하는 축 신규.
2. **단가 2종(기준단가 20,000 / 원가단가 13,888)** 을 설정값으로 — 현재 시세 1종(`market_rate`)만. 원가단가는 `expected_payout`의 max_payment/기준값(tb_config project_base_params)에 해당하나, 매출 기준단가는 별도.
3. **승인시점 가격 잠금** — `current_market_rate`(최신)·`trailing_avg_rate`(6개월)만 존재, 승인시 스냅샷 없음. 신규: `Project.approved_unit_price`(+ 승인 전이 시 캡처).
4. **2상태 산식 분기** — 현재 손익식(payout_rate·sale_recognized·gross_profit)은 승인 무관 동일. 신청중=예상(6개월평균)·승인=확정(잠금가)로 평가기준 분기 신규.
5. **예상↔확정 수량 잠금** — effective_reduction 항상 live. 승인 시 확정수량 스냅샷(회계 경로 반영) 신규.
6. (선택) **실지급 추적** — expected_payout=예상원가 vs 실제 지급액. 세금계산서(매입) = 실지급 증빙. `TAX_INVOICE_HTML_IMPORT_PLAN.md`와 연결.

---

## 3. 설계 방향 (초안)

### 3.1 데이터 모델
- `Project`: `approved_unit_price`(승인시점 매출 기준단가 스냅샷, nullable), `approved_reduction`(승인시 확정수량 스냅샷, nullable) 추가.
- 매각률/소유량: `ProjectSale`에 매각비율 또는 사업 단위 매각률로 후시보유(L)/매각(M) 산출. (is_hold 이진 → 비율 축으로 확장 검토)
- 단가 2종: tb_config에 `sale_base_unit_price`(기준단가)·원가단가는 project_base_params 재사용. (승인가 잠금은 Project 스냅샷 우선)

### 3.2 산식 (compute_accounting 확장)
- 입력에 **rate 파라미터** 추가(현재 rate 미입력). 상태별:
  - 신청중: 평가 = 예상수량(effective_reduction) × **6개월 평균가**(trailing_avg_rate)
  - 승인: 평가 = 확정수량(approved_reduction 스냅샷) × **승인시점 잠금가**(approved_unit_price)
- 원가 = expected_payout(그대로). 재고자산 = 후시보유분(L) 평가. 미착품 = 미승인 예상.
- 매출 = 매각분 실매각액(sale_invoice_amount, 세금계산서 기반). 손익 = 매출인식 − 원가.

### 3.3 상태 전이
- 승인 전이(현재 payout-params 입력에 묶인 approved_at) 시점에 `approved_unit_price`·`approved_reduction` 캡처. 명시적 '승인' 액션 검토.

### 3.4 화면
- 사업상세·재무원장·자산관리보고·전기버스·정산에 후시보유/매각·재고자산/미착품·2상태 평가 노출. 재무 플래그 게이팅 유지(운영 은닉).

---

## 4. 단계(초안, 개발 착수 시)
- C1: 단가 2종 설정 + 승인시점가/확정수량 스냅샷 컬럼(+ensure_schema) + 승인 전이 캡처.
- C2: 매각률 기반 후시보유/매각 소유량 분할 + 재고자산/미착품 산출. ✅ **구현(dev)** —
  `Project.sale_ratio`(%) + `services/carbon_credit.compute_ownership`: 소유량 K(승인 확정수량
  approved_reduction 우선, 없으면 Σeff)를 매각 M=K×율·후시보유 L=K−M 분할, L×원가단가(13,888)=재고자산.
  ProjectDetailOut.carbon_ownership(비영속) + 사업상세 매각률 인라인 편집·소유량 표시. compute_accounting 무변경.
- C3: compute_accounting 2상태 분기(rate 입력·예상/확정 평가) — finance_query·화면 동시.
- C4: (선택) 실지급 추적 + 세금계산서 연결(TAX_INVOICE 플랜).
- 각 단계 4원칙 루프(planner→implementer→verifier→reviewer), 회계 정합 테스트 필수(기존 16/16 회귀 0).

## 5. 미결(착수 시 확정)
- 매각률 grain: 사업 단위 vs 매각계약(ProjectSale) 단위 vs 투자사별.
- 재고평가 단가: 원가단가(13,888) vs 시세 — 엑셀은 후시보유분을 원가단가로 평가.
- '승인' 전이를 명시 액션으로 분리할지(현재 payout-params 입력에 묶임).
- 실지급 추적(C4) 포함 범위.
- 투자사별 손익 분해 필요 범위(현재 사업 단일 스칼라).

## 부록 A — 엑셀 실측(발췌)
- 단가: 기준단가 20,000 / 원가단가 13,888(O1/O2).
- NWK001(100% 매각): K=7628.38, M=7628.38(전량 매각), N(매출)=127,070,000, O(원가)=66,000,000.
- NWK003(89% 매각): K=13722.39, M=12212.92(89%), 후시보유 L=1509.46(11%), 보유 매출평가 N=20,963,415(=L×13,888), O=5,205,352.
- 미승인 예시(row28): L=K×1(100% 보유), N=L×원가단가, O=expected_payout 산식. → 미착품.
- 총계: 대수 4211, 감축량 868,107, 후시보유 249,422 / 매각 324,862, 매출 107.99억, 원가 61.49억.
