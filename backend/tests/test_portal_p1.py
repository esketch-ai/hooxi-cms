"""포털 P1 — 운수사(PARTNER) 계약대수·보고서·정산 (스코프·역할 게이트)."""

import models
from auth import create_access_token


def _external_user(user_id, email, role, **extra):
    db = models.SessionLocal()
    try:
        u = db.get(models.User, user_id)
        if u is None:
            u = models.User(user_id=user_id, email=email, name=email.split("@")[0])
            db.add(u)
        u.role = role
        u.status = "ACTIVE"
        for k, v in extra.items():
            setattr(u, k, v)
        db.commit()
        db.refresh(u)
        db.expunge(u)
        return u
    finally:
        db.close()


def _h(user):
    return {"Authorization": "Bearer " + create_access_token(user)}


def _cleanup(db):
    db.query(models.Settlement).filter(
        models.Settlement.client_id.in_(
            db.query(models.Client.client_id).filter(
                models.Client.company_name.like("TESTP1%"))
        )).delete(synchronize_session=False)
    db.query(models.ReportDelivery).filter(
        models.ReportDelivery.client_id.in_(
            db.query(models.Client.client_id).filter(
                models.Client.company_name.like("TESTP1%"))
        )).delete(synchronize_session=False)
    db.query(models.FleetStatus).filter(
        models.FleetStatus.company_name.like("TESTP1%")).delete(synchronize_session=False)
    db.query(models.Project).filter(
        models.Project.project_name.like("TESTP1%")).delete(synchronize_session=False)
    db.query(models.User).filter(
        models.User.user_id.like("t-p1-%")).delete(synchronize_session=False)
    db.query(models.Client).filter(
        models.Client.company_name.like("TESTP1%")).delete(synchronize_session=False)
    db.commit()


def _setup(db):
    a = models.Client(client_type="TRANSPORT", company_name="TESTP1운수A", region="서울",
                      biz_reg_no="890-11-11111")
    b = models.Client(client_type="TRANSPORT", company_name="TESTP1운수B", region="부산",
                      biz_reg_no="890-22-22222")
    db.add_all([a, b]); db.commit()
    prj = models.Project(project_name="TESTP1사업", project_status="추진")
    db.add(prj); db.commit()
    db.add_all([
        models.FleetStatus(client_id=a.client_id, region="서울", industry="CITY",
                           company_name="TESTP1운수A", period="2026-06",
                           license_count=80, total_count=80, electric=20),
        models.FleetStatus(client_id=b.client_id, region="부산", industry="CITY",
                           company_name="TESTP1운수B", period="2026-06",
                           license_count=40, total_count=40, electric=5),
        models.ReportDelivery(client_id=a.client_id, period="2026-06",
                              report_type="MONTHLY", status="SENT"),
        models.ReportDelivery(client_id=a.client_id, period="2026-07",
                              report_type="MONTHLY", status="WRITING"),  # 내부 상태 — 비노출
        models.Settlement(client_id=a.client_id, project_id=prj.project_id,
                          period="2026-06", status="CONFIRMED", confirmed_amount=1234000,
                          vehicle_count=10),
        models.Settlement(client_id=b.client_id, project_id=prj.project_id,
                          period="2026-06", status="CONFIRMED", confirmed_amount=999000),
    ])
    db.commit()
    return a.client_id, b.client_id


def test_partner_fleet_reports_settlements_scoped(client):
    db = models.SessionLocal()
    try:
        _cleanup(db)
        a_id, b_id = _setup(db)
    finally:
        db.close()
    partner = _external_user("t-p1-partner", "p1p@ext.kr", "PARTNER", client_id=a_id)
    h = _h(partner)
    # 계약대수 — 자기 회사(A)만
    r = client.get("/api/v1/portal/fleet-status", headers=h)
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1 and items[0]["license_count"] == 80
    # 보고서 — 발송 완료분만(WRITING 비노출)
    r2 = client.get("/api/v1/portal/reports", headers=h)
    periods = [x["period"] for x in r2.json()]
    assert periods == ["2026-06"]
    assert r2.json()[0]["has_file"] is False
    # 파일 없는 보고서 다운로드 → 404
    rid = r2.json()[0]["report_id"]
    assert client.get(f"/api/v1/portal/reports/{rid}/download", headers=h).status_code == 404
    # 정산 — 자기 회사(A)만
    r3 = client.get("/api/v1/portal/settlements", headers=h)
    assert r3.status_code == 200
    assert len(r3.json()) == 1 and r3.json()[0]["confirmed_amount"] == 1234000.0
    db = models.SessionLocal()
    try:
        _cleanup(db)
    finally:
        db.close()


def test_p1_role_gates(client, admin_headers):
    db = models.SessionLocal()
    try:
        _cleanup(db)
        a_id, _ = _setup(db)
    finally:
        db.close()
    investor = _external_user("t-p1-inv", "p1i@ext.kr", "INVESTOR")
    for path in ("/api/v1/portal/fleet-status", "/api/v1/portal/reports",
                 "/api/v1/portal/settlements"):
        # INVESTOR — 운수사 전용이라 403
        assert client.get(path, headers=_h(investor)).status_code == 403
        # 내부 역할 — 포털 경로 403(격리 불변)
        assert client.get(path, headers=admin_headers).status_code == 403
    # client_id 미연결 PARTNER → 403
    orphan = _external_user("t-p1-orphan", "p1o@ext.kr", "PARTNER", client_id=None)
    assert client.get("/api/v1/portal/fleet-status", headers=_h(orphan)).status_code == 403
    db = models.SessionLocal()
    try:
        _cleanup(db)
    finally:
        db.close()


def test_external_account_preview(client, admin_headers):
    """발급 전 미리보기 — 관리자에게 그 계정의 포털 데이터 그대로 + 경고. 스코프·격리 유지."""
    db = models.SessionLocal()
    try:
        _cleanup(db)
        a_id, _ = _setup(db)
    finally:
        db.close()
    partner = _external_user("t-p1-pv", "p1pv@ext.kr", "PARTNER", client_id=a_id)
    r = client.get(f"/api/v1/external-accounts/{partner.user_id}/preview", headers=admin_headers)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["role"] == "PARTNER" and d["org_name"] == "TESTP1운수A"
    assert len(d["fleet_status"]) == 1 and d["fleet_status"][0]["license_count"] == 80
    assert [x["period"] for x in d["reports"]] == ["2026-06"]  # 발송 완료분만
    assert len(d["settlements"]) == 1
    assert d["warnings"] == []
    # 미연결 PARTNER — 경고 + 빈 목록(403 아님: 관리자 검증용)
    orphan = _external_user("t-p1-pv2", "p1pv2@ext.kr", "PARTNER", client_id=None)
    r2 = client.get(f"/api/v1/external-accounts/{orphan.user_id}/preview", headers=admin_headers)
    assert r2.status_code == 200
    assert r2.json()["warnings"] and r2.json()["projects"] == []
    # 내부 계정 미리보기 → 404 (외부 계정 전용)
    db = models.SessionLocal()
    try:
        internal = db.query(models.User).filter(models.User.role == "ADMIN").first()
        r3 = client.get(f"/api/v1/external-accounts/{internal.user_id}/preview",
                        headers=admin_headers)
        assert r3.status_code == 404
        # 감사 로그 PORTAL_PREVIEW 기록
        log = (db.query(models.AuditLog)
               .filter_by(action="PORTAL_PREVIEW", target_id=partner.user_id).first())
        assert log is not None
        db.query(models.AuditLog).filter_by(action="PORTAL_PREVIEW").delete(synchronize_session=False)
        db.commit()
        _cleanup(db)
    finally:
        db.close()
