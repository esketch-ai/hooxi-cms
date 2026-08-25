"""운수사별 참여 크로스 집계(라이프사이클 보) — 참여율·상태별·3단계 오차."""

import models

API = "/api/v1/clients/participation-overview"


def _clean():
    db = models.SessionLocal()
    try:
        cids = [c.client_id for c in db.query(models.Client).filter(
            models.Client.company_name.in_(["오버뷰운수A", "오버뷰운수B"])).all()]
        for cid in cids:
            db.query(models.ProjectVehicle).filter(models.ProjectVehicle.client_id == cid).delete(synchronize_session=False)
            db.query(models.ClientVehicle).filter(models.ClientVehicle.client_id == cid).delete(synchronize_session=False)
        db.query(models.Project).filter(models.Project.project_name == "OV사업").delete(synchronize_session=False)
        db.query(models.Client).filter(models.Client.company_name.in_(["오버뷰운수A", "오버뷰운수B"])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_overview_aggregates_operators(client, staff_headers):
    _clean()
    db = models.SessionLocal()
    try:
        a = models.Client(client_type="TRANSPORT", company_name="오버뷰운수A", region="강원")
        b = models.Client(client_type="TRANSPORT", company_name="오버뷰운수B", region="강원")
        db.add_all([a, b]); db.flush()
        # A: 보유 2대, 참여 1(발급완료, 예상100/모니터링90/최종=final 95)
        db.add(models.ClientVehicle(client_id=a.client_id, vehicle_no="A1", status="운행"))
        db.add(models.ClientVehicle(client_id=a.client_id, vehicle_no="A2", status="운행"))
        p = models.Project(project_name="OV사업", project_status="발급완료", issued_credits=95)
        db.add(p); db.flush()
        db.add(models.ProjectVehicle(project_id=p.project_id, client_id=a.client_id, vehicle_no="A1",
                                     total_reduction=100, monitoring_reduction=90, final_reduction=95))
        # B: 보유 1대, 참여 0
        db.add(models.ClientVehicle(client_id=b.client_id, vehicle_no="B1", status="운행"))
        db.commit()
        aid, bid = a.client_id, b.client_id
    finally:
        db.close()

    r = client.get(API, headers=staff_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    rows = {x["client_id"]: x for x in body["items"]}
    assert aid in rows and bid in rows
    ra = rows[aid]
    assert ra["owned_count"] == 2 and ra["participating_count"] == 1
    assert ra["completed_count"] == 1 and ra["not_participated_count"] == 1
    assert ra["participation_rate"] == 50.0
    assert ra["expected_reduction"] == 100.0 and ra["monitoring_reduction"] == 90.0
    assert ra["final_reduction"] == 95.0
    assert ra["ach_monitoring"] == 90.0 and ra["ach_final"] == 95.0
    # B: 참여율 0(참여율 낮아 정렬상 A 뒤)
    assert rows[bid]["participation_rate"] == 0.0
    # A가 B보다 앞(참여율 내림차순)
    order = [x["client_id"] for x in body["items"]]
    assert order.index(aid) < order.index(bid)
    _clean()


def test_region_filter(client, staff_headers):
    _clean()
    db = models.SessionLocal()
    try:
        a = models.Client(client_type="TRANSPORT", company_name="오버뷰운수A", region="강원")
        db.add(a); db.flush()
        db.add(models.ClientVehicle(client_id=a.client_id, vehicle_no="A1", status="운행"))
        db.commit()
    finally:
        db.close()
    # 다른 권역 필터 → 제외
    body = client.get(API, headers=staff_headers, params={"region": "제주"}).json()
    assert all(x["operator_name"] != "오버뷰운수A" for x in body["items"])
    _clean()


def test_requires_auth(client):
    assert client.get(API).status_code == 401
