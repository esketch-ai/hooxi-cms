"""운수사 감축 참여 라이프사이클 — 참여상태(기/현/미) 파생·요약(P3/P1)."""

import models

API = "/api/v1/clients/{0}/participation"


def _setup():
    db = models.SessionLocal()
    try:
        c = models.Client(client_type="TRANSPORT", company_name="참여테스트운수", region="강원")
        db.add(c); db.flush()
        cid = c.client_id
        # 보유 차량 3대(운행 2 EV + 폐차 1)
        db.add(models.ClientVehicle(client_id=cid, vehicle_no="강원70자1", fuel="전기", status="운행", model_name="일렉시티"))
        db.add(models.ClientVehicle(client_id=cid, vehicle_no="강원70자2", fuel="전기", status="운행", model_name="일렉시티"))
        db.add(models.ClientVehicle(client_id=cid, vehicle_no="강원70자9", fuel="경유", status="폐차"))
        # 발급완료 사업 + 참여차량(기참여)
        p1 = models.Project(project_name="A사업", project_status="발급완료")
        db.add(p1); db.flush()
        db.add(models.ProjectVehicle(project_id=p1.project_id, client_id=cid, vehicle_no="강원70자1",
                                     introduction_type="대체도입", total_reduction=200, effective_reduction=180))
        # 모니터링 사업 + 참여차량(참여중)
        p2 = models.Project(project_name="B사업", project_status="모니터링")
        db.add(p2); db.flush()
        db.add(models.ProjectVehicle(project_id=p2.project_id, client_id=cid, vehicle_no="강원70자2",
                                     introduction_type="신규도입", total_reduction=150))
        db.commit()
        return cid
    finally:
        db.close()


def _clean(cid):
    db = models.SessionLocal()
    try:
        db.query(models.ProjectVehicle).filter(models.ProjectVehicle.client_id == cid).delete(synchronize_session=False)
        db.query(models.ClientVehicle).filter(models.ClientVehicle.client_id == cid).delete(synchronize_session=False)
        db.query(models.Project).filter(models.Project.project_name.in_(["A사업", "B사업"])).delete(synchronize_session=False)
        db.query(models.Client).filter(models.Client.client_id == cid).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_participation_derivation(client, staff_headers):
    cid = _setup()
    try:
        r = client.get(API.format(cid), headers=staff_headers)
        assert r.status_code == 200, r.text
        s = r.json()["summary"]
        # 보유 2대(폐차 제외), 참여 2대(기1+현1), 미참여 0
        assert s["owned_count"] == 2
        assert s["participating_count"] == 2
        assert s["completed_count"] == 1 and s["ongoing_count"] == 1
        assert s["not_participated_count"] == 0
        assert s["participation_rate"] == 100.0
        # 예상 = 200+150, 최종 = 180(발급완료분만)
        assert s["expected_reduction_total"] == 350.0
        assert s["final_reduction_total"] == 180.0
        # 목록 상태
        parts = {p["vehicle_no"]: p for p in r.json()["participated"]}
        assert parts["강원70자1"]["participation_status"] == "COMPLETED"
        assert parts["강원70자1"]["final_reduction"] == 180.0
        assert parts["강원70자2"]["participation_status"] == "ONGOING"
        assert parts["강원70자2"]["final_reduction"] is None
    finally:
        _clean(cid)


def test_not_participated_candidates(client, staff_headers):
    cid = _setup()
    try:
        # 참여차량 삭제 → 보유 2대 모두 미참여(EV 후보)
        db = models.SessionLocal()
        db.query(models.ProjectVehicle).filter(models.ProjectVehicle.client_id == cid).delete(synchronize_session=False)
        db.commit(); db.close()
        s = client.get(API.format(cid), headers=staff_headers).json()
        assert s["summary"]["not_participated_count"] == 2
        assert s["summary"]["ev_candidate_count"] == 2
        assert s["summary"]["participation_rate"] == 0.0
        assert len(s["not_participated"]) == 2 and all(n["is_ev"] for n in s["not_participated"])
    finally:
        _clean(cid)


def test_requires_auth(client):
    assert client.get(API.format("x")).status_code == 401
