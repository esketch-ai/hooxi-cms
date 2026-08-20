"""운수사 계약대수 현황 모델(F1) — round-trip·유니크·수작업 분리·코드 시드."""

import pytest

import models


def _cleanup(db):
    db.query(models.FleetStatus).filter(
        models.FleetStatus.company_name.like("TESTFLEET%")
    ).delete(synchronize_session=False)
    db.commit()


def test_fleet_status_roundtrip_and_unique(client):
    db = models.SessionLocal()
    cid = None
    try:
        _cleanup(db)
        c = models.Client(client_type="TRANSPORT", company_name="TESTFLEET경성사",
                          biz_reg_no="992-99-99992")
        db.add(c)
        db.commit()
        cid = c.client_id
        fs = models.FleetStatus(
            client_id=cid, region="서울", industry="CITY", company_name="TESTFLEET경성",
            period="2026-06", license_count=83, total_count=83,
            diesel=0, cng=51, hybrid=0, electric=24, hydrogen=0, source="EXCEL",
        )
        db.add(fs)
        db.commit()
        got = db.query(models.FleetStatus).filter_by(company_name="TESTFLEET경성").first()
        assert got is not None and got.electric == 24 and got.period == "2026-06"

        # 매칭 건(client_id 有)의 (client_id, period, company_name) 재적재 → unique 위반.
        # 미매칭(client_id NULL)은 SQL상 NULL≠NULL이라 앱 레벨 dedup 필요(F2 파서에서 처리).
        dup = models.FleetStatus(client_id=cid, company_name="TESTFLEET경성", period="2026-06")
        db.add(dup)
        with pytest.raises(Exception):
            db.commit()
        db.rollback()
    finally:
        _cleanup(db)
        if cid:
            db.query(models.Client).filter_by(client_id=cid).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_fleet_mgmt_separate_from_status(client):
    """수작업 관리(tb_fleet_mgmt)는 고객사 1:1, 대수(status)와 분리."""
    db = models.SessionLocal()
    cid = None
    try:
        c = models.Client(client_type="TRANSPORT", company_name="TESTFLEET관리운수",
                          biz_reg_no="991-99-99991")
        db.add(c)
        db.commit()
        cid = c.client_id
        m = models.FleetMgmt(client_id=cid, target_type="BIZ", contract_yn="Y",
                            union_contract="N", regulated_yn="N", memo="테스트")
        db.add(m)
        db.commit()
        got = db.get(models.FleetMgmt, cid)
        assert got.target_type == "BIZ" and got.contract_yn == "Y"
    finally:
        if cid:
            db.query(models.FleetMgmt).filter_by(client_id=cid).delete(synchronize_session=False)
            db.query(models.Client).filter_by(client_id=cid).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_fleet_code_categories_seeded(client):
    """FLEET_TARGET·FLEET_INDUSTRY 공통코드 시드 확인(하드코딩 금지 규약)."""
    db = models.SessionLocal()
    try:
        targets = {c.code for c in db.query(models.Code).filter(
            models.Code.category == "FLEET_TARGET").all()}
        inds = {c.code for c in db.query(models.Code).filter(
            models.Code.category == "FLEET_INDUSTRY").all()}
        assert {"BIZ", "REG"} <= targets
        assert {"CITY", "RURAL", "INTERCITY"} <= inds
    finally:
        db.close()
