# DB 아키텍처 검토 보고서 (DBA 관점)

> 대상: hooxi-cms · SQLAlchemy 선언형 · PostgreSQL(운영)/SQLite(테스트) · **35 테이블**
> 스키마 관리: `create_all` + `models.ensure_schema()`(런타임 additive) + Alembic(수동)
> 작성: 2026-08-20. 근거: models.py 스키마 전수 덤프 + FK 그래프 + ensure_schema 인덱스/유니크 목록.

---

## 0. 총평
정규화·명명 규칙(tb_ 접두·snake_case)이 일관되고 도메인 분리가 명확하다. 스냅샷 테이블로
이력을 동결하는 설계도 합리적. 리스크는 **스키마 관리 이원화**와 **최근 급증 기능의 인덱스 공백·
도메인 중복**에 집중된다.

## 1. 🔴 P0 — 스키마 관리 이원화 (FK ondelete)
- 컬럼·인덱스·유니크는 `ensure_schema()`가 런타임 idempotent 보강 → **de-facto 정본**.
- **FK ondelete는 모델 정의로만** 반영(create_all)되고, `ensure_schema`는 **기존 FK를 교정하지 않음**.
- 모델에는 삭제-정합 핵심 FK 13개의 ondelete가 **이미 정의됨**(0002 10개 + 0004 3개):
  - CASCADE: project_vehicle/sale/stage/purchase_invoice.project_id
  - SET NULL: *_.client_id/asset_id/client_vehicle_id, project_sale.buyer_id, user.client_id/buyer_id
- 따라서 **새로 만든 DB(create_all)는 정상**. 문제는 **이 규칙 추가 이전에 생성된 구 운영 DB**의
  기존 FK가 `NO ACTION`으로 남아, 사업/차량 삭제 시 CASCADE·SET NULL이 미동작할 수 있다는 것.
- 그 외 다수 FK(`tb_document.client_id`·`tb_project.client_id`·`tb_settlement.client_id` 등)의
  `ondelete=None`은 **의도된 설계**다 — 앱이 `_CLIENT_DEP_CHECKS`로 고객사 삭제를 사전 차단하므로
  NO ACTION이 "종속 있으면 삭제 불가" 정책과 합치(고객사는 삭제하지 않는다).
- **조치(P0)**: `ensure_schema`에 **FK ondelete 멱등 교정**(PostgreSQL 한정, 현재 ondelete를
  inspector로 확인해 불일치 시에만 DROP+재생성)을 추가 → 구 운영 DB도 배포 시 자동 정합.
  SQLite는 ALTER FK 불가라 no-op. (Alembic 0002/0004와 동일 정책표.)

## 2. 🟠 P1 — 인덱스 공백 (신규 테이블)
`ensure_schema`가 조회 인덱스 20여개를 잘 깔지만 최근 테이블·upsert 경로에 공백:
| 대상 | 문제 | 조치(P1) |
|---|---|---|
| `tb_tax_invoice` | approval_no UNIQUE만 있고 조회/조인 인덱스 없음 | direction·issue_date·matched_client_id·matched_buyer_id·project_id 인덱스 |
| `tb_client.biz_reg_no` | 대기/정식·중복매칭·upsert 후보축소 풀스캔 | biz_reg_no 인덱스 |
| `tb_client.company_name` | upsert 회사명 매칭 풀스캔 | company_name 인덱스 |
| `tb_settlement` | client/project 조회 인덱스 없음 | client_id·project_id 인덱스 |

→ 모두 `ensure_schema` 인덱스 목록에 추가(additive·idempotent, CREATE INDEX IF NOT EXISTS).

## 3. 🟠 도메인 중복 (정리 대상, 별건)
1. **고객사 import 다중 spec**: clients·transport·transport_roster·transport_info 4종이 모두
   `tb_client`에 씀. **transport(표준)로 단일화** 결정됨 → roster/info는 은퇴(deprecate) 표시 권장.
2. **매입 세금계산서 2계층**: `tb_purchase_invoice`(사업×운수사 지급, 회계 product) vs
   `tb_tax_invoice`(홈택스 원장, direction 매입 포함). 승인번호로 연결 안 됨 → 매핑/승격 관계 정의 필요.
3. **정산·회계 다축**: `tb_settlement`(P4 상태머신) / `compute_accounting`(무저장 파생) /
   `tb_project_*_snapshot`(동결). 정본 관계를 ERD·문서로 명시 필요.

## 4. 🟡 관찰(경미)
- **레거시 잔존**: Alembic 0003이 지운 `tb_project_client_map` 등이 ensure_schema 미DROP → 구
  운영 DB에 죽은 테이블/컬럼 잔존 가능(무해·혼란).
- **reg_status 파생**: 컬럼 없이 biz_reg_no 유무로 파생(깔끔). 대량 "대기만" 필터가 필요해지면
  부분 인덱스(`WHERE biz_reg_no IS NULL`)나 생성 컬럼 고려.
- **감사로그**: created_at·actor_id 인덱스 존재(양호). 증가 시 파티셔닝 검토.
- **PK=UUID(String50)**: 조인 다수라 물리 크기 큼. 현 규모(수천~수만)에선 무해.

## 5. 우선순위
| 순위 | 항목 | 상태 |
|---|---|---|
| P0 | FK ondelete 멱등 교정(ensure_schema, PG) | **본 작업에서 구현** |
| P1 | 신규 테이블 인덱스 | **본 작업에서 구현** |
| P2 | 도메인 중복 정리(transport 단일화·tax↔purchase 관계) | 별건 |
| P3 | 레거시 DROP·정산/회계 ERD 문서화 | 별건 |

## 6. FK ondelete 정책표(정본)
```
CASCADE  : project_vehicle.project_id, project_sale.project_id,
           purchase_invoice.project_id, project_stage.project_id
SET NULL : project_vehicle.{client_id,asset_id,client_vehicle_id},
           purchase_invoice.client_id, client_vehicle.{client_id,asset_id},
           project_sale.buyer_id, user.{client_id,buyer_id}
NO ACTION(의도): 그 외 client/project 참조(앱이 _CLIENT_DEP_CHECKS로 삭제 차단)
```
