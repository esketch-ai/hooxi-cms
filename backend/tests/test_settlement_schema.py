"""P4 정산 재건 증분 1 — 정산 헤더(tb_settlement)·스냅샷 additive·코드값 스모크.

이 증분은 스키마/모델/코드값 + 부팅 정합까지(라우터·전이 로직 없음). 검증 대상:
(a) 부팅/init_db 후 tb_settlement 조회 무오류, (b) Settlement insert/select 왕복,
(c) SETTLEMENT_STATUS에 CONFIRMED 코드 seed, (d) snapshot 신규 컬럼 존재,
(e) ensure_schema required/unique 목록에 신규 컬럼·유니크 등록(배포 PG additive 보강 근거).
"""

from sqlalchemy import inspect as _inspect

import models


def test_tb_settlement_query_no_error(client):
    """부팅(client fixture = 앱 startup/init_db) 후 tb_settlement 조회가 무오류."""
    db = models.SessionLocal()
    try:
        # SELECT 자체가 스키마 정합(컬럼 존재)을 확인한다. 세션 공유 DB라 다른 모듈(P4 확정·전이)이
        # 정산 행을 적재할 수 있으므로 개수는 검사하지 않는다(쿼리 무오류만 확인).
        assert db.query(models.Settlement).count() >= 0
    finally:
        db.close()


def test_settlement_insert_select_roundtrip(client):
    """Settlement insert/select 왕복 — 상태 default CONFIRMED·동결 지표 보존."""
    db = models.SessionLocal()
    try:
        c = models.Client(client_type="TRANSPORT", company_name="정산테스트운수")
        db.add(c)
        db.flush()
        p = models.Project(
            client_id=c.client_id, project_name="정산테스트사업", project_status="발급완료"
        )
        db.add(p)
        db.flush()

        s = models.Settlement(
            client_id=c.client_id,
            project_id=p.project_id,
            period="2026-08",
            confirmed_amount=1000000,
            vehicle_count=12,
            effective_reduction=34.567,
        )
        db.add(s)
        db.commit()
        sid = s.settlement_id

        got = db.query(models.Settlement).filter_by(settlement_id=sid).one()
        assert got.status == "CONFIRMED"  # default
        assert got.vehicle_count == 12
        assert float(got.effective_reduction) == 34.567
        assert got.period == "2026-08"
    finally:
        db.close()


def test_settlement_status_confirmed_seeded(client):
    """SETTLEMENT_STATUS에 CONFIRMED 코드가 seed되어 있다(하드코딩 금지 근거)."""
    db = models.SessionLocal()
    try:
        row = (
            db.query(models.Code)
            .filter(models.Code.category == "SETTLEMENT_STATUS", models.Code.code == "CONFIRMED")
            .first()
        )
        assert row is not None
        assert row.label == "확정"
        assert row.active == "Y"
    finally:
        db.close()


def test_snapshot_additive_columns_exist(client):
    """tb_settlement_snapshot에 P4 additive 컬럼(vehicle_count·effective_reduction) 존재."""
    insp = _inspect(models.engine)
    cols = {c["name"] for c in insp.get_columns("tb_settlement_snapshot")}
    assert "vehicle_count" in cols
    assert "effective_reduction" in cols


def test_ensure_schema_registers_new_columns():
    """배포 PG additive 보강 근거 — required 목록에 snapshot 신규 컬럼·unique 등록(정적)."""
    import inspect as _pyinspect

    src = _pyinspect.getsource(models.ensure_schema)
    assert '("tb_settlement_snapshot", "vehicle_count", "INTEGER")' in src
    assert '("tb_settlement_snapshot", "effective_reduction", "NUMERIC(14,3)")' in src
    assert "uq_settlement_client_project_period" in src
