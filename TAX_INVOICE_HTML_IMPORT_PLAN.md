# 국세청 세금계산서 HTML 자동 반영 — 개발 계획서

> 목적: 국세청(홈택스)에서 발급/발행된 **매입·매출 전자세금계산서 HTML 파일**을 정산 폴더에서
> 파악하고 내부 값을 추출해 **감축사업 관리(정산)에 자동 반영**한다. 암호(대부분 사업자번호)가 걸린
> 파일은 시스템이 보관 중인 사업자번호(고객사/투자사/자사)로 자동 해제한다.
>
> 작성: 2026-08-20. 상태: **P1~P5 구현 완료(로컬 커밋, 미배포)** · pytest 731 · ON/OFF 빌드·vitest 100.
> 커밋: P1 e45b8aa · P2 ea97e72 · P3 b3267d5(원장 tb_tax_invoice) · P4 86b2267 · P5a e1f0b07(API) · P5b b78073e(화면 /tax-invoices).
> 실데이터 발견: 자사 복수(후시파트너스·후시제주랩), 매입 공급자 대부분 일반매입처→후시 전체 세금계산서 원장으로 수용, 수정취소=음수.
> 진행 중: P5c Dropbox 정산폴더 스캔. 사용 전 config company_biz_reg_no에 자사 사업자번호 전부 콤마 입력.
>
> ⚠️ 반전: 파일은 평문 HTML이 아니라 **홈택스 보안메일(암호화)** 이며, 계산서 데이터는
> 암호화된 **국세청 표준 전자세금계산서 XML 첨부**다. HTML 스크래핑이 아니라 복호화+XML 파싱.

---

## 0. 확정 결정 (사용자)

| 항목 | 결정 |
|---|---|
| 트리거(진입점) | **Dropbox 정산폴더 스캔 + 사업 상세 직접 업로드 (둘 다 지원)** |
| 반영 방식 | **미리보기 → 확인 후 적용** (즉시 자동 아님; 금액 데이터 안전) |
| 자사(후시파트너스) 사업자번호 저장처 | **앱설정 config 키 `company_biz_reg_no` 신설** |
| 매칭 실패(미등록 사업자번호) | **보류(미매칭)** — 자동 신규생성 안 함 |
| 폴더명 규칙 정합 | 기존 `{지역}_{회사명}_{분류}` 유지, Dropbox 루트=`/`(앱폴더) |

---

## 1. 현재 구조 (조사 결과, file:line)

### 1-A. 세금계산서 데이터 모델
- **매입** `PurchaseInvoice`/`tb_purchase_invoice` (`backend/models.py:372`, 스키마 `schemas.py:1321`)
  - `amount` Numeric(15,2) **필수** ← 파싱 핵심 · `issue_date` Date(=작성일자) · `payment_date` Date(입금일, nullable)
  - `project_id`(FK, NOT NULL) · `client_id`(FK→운수사, SET NULL) · `operator_name`(free text) · `region` · `memo`
  - 화이트리스트 `_INVOICE_FIELDS` (`routers/projects.py:1261`)
  - **공급자 사업자번호 컬럼 없음** → `Client.biz_reg_no` 매칭 필요
- **매출** = `ProjectSale`/`tb_project_sale` (`models.py:337`, 스키마 `schemas.py:1212`) — 별도 매출 인보이스 테이블 없음
  - `sale_invoice_amount` Numeric(15,2) ← 매출인식 기준(파싱 핵심) · `sale_invoice_date` Date · `sale_payment_date` Date(nullable)
  - `project_id`(FK, NOT NULL) · `buyer_id`(FK→투자사, SET NULL) · `buyer_name` · `is_hold`(Y/N, 매출인식 제외)

### 1-B. 사업자번호 보관처
| 주체 | 위치 | 상태 |
|---|---|---|
| 고객사(운수사) | `Client.biz_reg_no` (`models.py:98`) | ✅ 있음 |
| 투자사/매수자 | `Buyer.biz_reg_no` (`models.py:326`) | ✅ 있음 |
| **후시파트너스(자사)** | 없음 | ❌ **신규 필요 → config `company_biz_reg_no`** |
- 정규화: `normalize_biz_no` (`routers/common.py:120`) = 숫자만 추출(하이픈/공백 무시). 매칭은 정규화 기준.
- 형식 체크섬 검증기는 없음(문자열 저장).

### 1-C. 정산 폴더 (Dropbox)
- 폴더는 **고객사(Client)만** provisioning. `Client.dropbox_folder` (`models.py:114`). 투자사/자사 폴더 없음.
- 고객사 폴더 밑 서브폴더 카테고리(tb_code CLIENT_FOLDER, `main.py:201`)에 **SETTLEMENT "정산" 있음**.
- 파일 나열/열람: `dropbox_storage.list_folder`/`temporary_link`/`download` · mail-merge 해석 패턴 `client_folders.resolve_recipient_file` (`client_folders.py:56`, confinement 포함).

### 1-D. 회계 반영 접점 (파싱값이 흘러갈 곳)
- `compute_accounting` (`services/accounting.py:20`): `product = Σ PurchaseInvoice.amount`, `sale_recognized = trunc(Σ trunc(sale_invoice_amount × payout_rate))`(is_hold 제외), `gross_profit = sale_recognized − product`.
- 배치 집계 `finance_query` (`services/finance_query.py:56`), 정산 요약 `settlement_summary.py`. **파싱으로 amount/sale_invoice_amount만 채우면 회계는 자동 재계산됨.**
- CRUD 접점: 매입 `routers/projects.py:1310/1343/1385/1439(엑셀)`, 매출 `:1141/1178`. 권한 `master.write`. 감사 `PURCHASE_INVOICE_*`.

### 1-E. 파싱 인프라
- **HTML 파서 라이브러리 없음** → `requirements.txt` 신규 추가 필요(bs4/lxml/표준 `html.parser` 중 샘플 보고 결정). `defusedxml==0.7.1` 있음.
- 참조 패턴: `services/excel_import.py` — `get_spec → build_template → parse_and_validate → ParseResult/valid_rows/to_preview` 3단계. HTML도 preview→commit 동형으로.
- 국세청/세금계산서/암호 HTML 관련 기존 코드 **전무**.

### 1-F. 엑셀 일괄등록과의 공존
- 매입은 엑셀 import 있음(`import_spec.py:173`, operator_name free text, client_id 없음). 매출은 엑셀 import 없음.
- **중복 방지 키 없음**(승인번호 컬럼 부재, project×운수사 다건 허용이 설계 전제) → HTML 반영 멱등 위해 **승인번호 고유키 신규 필요**.

---

## 2. 단계별 계획

### P1 — 기반 (포맷 무관, 선반영 가능)
- [ ] config 키 `company_biz_reg_no` 신설(환경설정 입력 UI + KNOWN_DEFAULTS). 자사 공급자/공급받는자 판정 기준.
- [ ] 계산서 **고유키(승인번호) 컬럼** — `tb_purchase_invoice.approval_no`, `tb_project_sale.sale_approval_no`(nullable String) 추가 + `ensure_schema` 반영. 재반영 멱등·중복 방지.
- [ ] HTML 파서 라이브러리 도입(샘플 보고 확정).

### P2 — 파서 (✅ 복호화 레시피 실증 완료 — 아래 부록)
- [ ] 홈택스 보안메일 복호화 서비스: 헤더 해독(base64→XOR 0x6b) → 알고리즘 판정 → `MD5(사업자번호)` 키 → SEED/AES-CBC(IV=0,PKCS7) 복호화.
- [ ] **비번 자동판별**: HashKey 검증 오라클로, 보관 중인 사업자번호(자사 config·`Client.biz_reg_no`·`Buyer.biz_reg_no`) 후보를 시도해 정답 키 선택.
- [ ] 첨부(`idCriAttachContents{n}`) 복호화 → base64 디코드 → **국세청 표준 TaxInvoice XML** 파싱.
- [ ] `parse_and_validate` 동형: 파일별 추출값 + 검증(오류/경고/보류).
- 라이브러리: `cryptography>=43`(`hazmat.decrepit.SEED`). ARIA(alg 3)는 향후 필요 시 추가.

### P3 — 매칭·매핑
- [ ] 사업자번호 → 자사(config)/고객사(`Client.biz_reg_no`)/투자사(`Buyer.biz_reg_no`) 판정 → **매입/매출 방향** 결정
  - (예: 공급받는자=자사 → 매입 / 공급자=자사 → 매출; 상대측 사업자번호로 Client/Buyer 매칭)
- [ ] `project_id` 결정: 업로드 경로면 URL 고정 / 스캔 경로면 폴더 소속으로 추론.
- [ ] 값→필드 매핑 확정: 공급가액/세액/합계 중 무엇을 `amount`/`sale_invoice_amount`에 넣을지(부가세 포함/제외) — 샘플로 확정.
- [ ] 미매칭 → 보류 리스트(사유 표기).

### P4 — 반영 파이프라인
- [ ] 미리보기: 파일별 {추출값, 매입/매출, 매칭상대, project, 중복(승인번호), 검증, 보류사유}.
- [ ] 확정: PurchaseInvoice/ProjectSale 생성·갱신(승인번호 멱등) + 감사(경로/승인번호, 비밀값 금지 R2-E6). 회계 자동 재계산.
- [ ] 엑셀 일괄등록과 중복 병합 규칙(승인번호 기준).

### P5 — 트리거/UI
- [ ] 사업 상세 HTML 업로드(UploadFile) → 미리보기 → 적용.
- [ ] Dropbox 정산폴더 스캔 → 미리보기 → 적용. (투자사/자사 폴더 체계 필요 여부는 매칭 설계에서 결정.)
- [ ] 재무 플래그 게이팅: 세금계산서는 사업상세(노출)지만 파생 회계는 은닉 대상 — 기존 예상지급액 게이팅과 정합.

### P6 — 검증
- [ ] 샘플 파일 e2e(매입·매출·평문·암호), 회계 정합(product/매출인식 반영), 매칭 실패 보류, 중복 재반영 멱등, 대량 스캔.

---

## 3. 미결/블로커

- ✅ **[해소] HTML 샘플·암호 메커니즘·값→필드 매핑** — 샘플 9건 확보(`Docs/세금계산서(html)/`), 복호화 실증 완료(부록 A). 홈택스 보안메일 SEED-CBC, 키=MD5(사업자번호), 데이터=표준 TaxInvoice XML 첨부. 매입/매출 방향·필드 매핑 확정.
- 남은 결정(구현 중 확정 가능):
  1. ✅ **금액 매핑 확정**: 매입 `amount` ← **공급가액(부가세 제외, `ChargeTotalAmount`)**, 매출 `sale_invoice_amount` ← 동일 기준(공급가액). (합계 GrandTotalAmount 아님)
  2. **project 매칭(스캔 경로)**: 정산 폴더가 고객사 폴더 밑이면 사업↔고객사 다대다에서 project 추론 단서 필요(승인번호·품목·기간·수동 지정 중).
  3. 투자사/자사 Dropbox 폴더 체계 신설 여부(매출/자사 파일 위치). 업로드 경로는 무관.
  4. ARIA(alg 3) 파일 등장 시 복호화 경로 추가(현재 샘플 전부 SEED).

---

## 4. 부수 신규 필요 항목 요약
- HTML 파서 라이브러리(requirements) · 자사 사업자번호 config 키 · 계산서 승인번호 고유키 컬럼(멱등) · (선택) 투자사/자사 폴더 체계 · 매출 HTML 파이프라인(엑셀 미존재).

---

## 5. 다음 액션
1. ✅ 샘플 확보·복호화 실증 완료(부록 A).
2. 개발 착수: **P1(cryptography>=43 업그레이드 · config `company_biz_reg_no` · 승인번호 고유키 컬럼+ensure_schema)** → P2 복호화·XML 파서 → P3 매칭 → P4 미리보기/적용 → P5 트리거/UI → P6 검증. 4원칙 루프, 각 증분 로컬 커밋. 배포는 "배포" 명시 시.

---

## 부록 A — 복호화 실증(POC) 결과 (2026-08-20)

샘플 `Docs/세금계산서(html)/` 9건 = **홈택스 보안메일**(암호화 이메일). 외부스크립트 `srtk.hometax.go.kr`의 seed.js/aes.js/md5.js/cri_ems_nt.js(CryptoJS). 전 파일 SEED(alg 2).

**복호화 절차(파이썬 재현 확인)**:
1. `<input id="idCriHeader" value="B">` → `base64decode(B)`의 각 바이트 `^ 0x6b` → 헤더텍스트(`\r\n`→`||`). `키:값` 파싱: `ContentEncryptionAlgorithm`(1=AES/2=SEED/3=ARIA), `HashKey`, `AttachFileName`, `AttachFileTagID`, `AttachFileSize`.
2. `key = MD5(비밀번호)` (16B). 비밀번호 = **사업자등록번호(숫자 10자리)**. IV = 16×0x00. 모드 CBC, 패딩 PKCS7.
3. **비번 검증 오라클**: `SEED_decrypt(base64decode(HashKey), key, iv)` 의 UTF-8 문자열 == `key.hex()` 이면 정답. → 보관 사업자번호(자사·Client·Buyer) 후보를 순회 시도해 자동 선택.
4. 본문/첨부: `<input id="idCriAttachContents0" value="C">` → `SEED_decrypt(base64decode(C), key, iv)` → 결과가 **다시 base64** → 디코드하면 **표준 TaxInvoice XML**(`urn:kr:or:kec:standard:Tax:...`).

**XML 필드 매핑(KEC 표준)**:
| 논리 | XML 리프 | 비고 |
|---|---|---|
| 공급자 사업자번호 | 첫 party `ID` (Invoicer) | 자사면 매출 |
| 공급받는자 사업자번호 | 둘째 party `ID` (Invoicee) | 자사면 매입 |
| 상호 | `NameText`(party 순서) | |
| 작성일자 | `IssueDateTime`(YYYYMMDDHHMMSS) | → issue_date/sale_invoice_date |
| **승인번호(고유키)** | `IssueID` | → 중복방지/멱등 신규 컬럼 |
| 공급가액 | `ChargeTotalAmount` | |
| 세액 | `TaxTotalAmount` | |
| 합계 | `GrandTotalAmount` = 공급가액+세액 | |
| 종류/용도 | `TypeCode`(0101 일반), `PurposeCode`(02 청구 등) | 수정취소 판별 검토 |
| 품목 | 명세 `NameText`/`CalculatedAmount` | |

**검증 실값**(리빌벨류→후시파트너스, 매입, 비번 후시 5298102298): 공급자 3541601931 / 공급받는자 5298102298 / 작성 20260708215746 / 승인 202607081026070896455535 / 공급가액 16,200,000 / 세액 1,620,000 / 합계 17,820,000. 매입 4건 동일 방식 성공. HashKey 검증 True.

**주의**: 파일명(`공급자 → 공급받는자`)은 사용자 라벨일 뿐, 방향·값은 XML 내부로 판정. 수정/취소분(`(수정취소)`) 별도 처리 필요(TypeCode/PurposeCode로).
