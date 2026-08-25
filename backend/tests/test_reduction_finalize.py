"""최종 감축량 확정·배분(라이프사이클 P4) — issued_credits를 effective 비율로 배분·동결."""

import models

API = "/api/v1/projects/{0}/finalize-reductions"


def _clean(name="F사업"):
    db = models.SessionLocal()
    try:
        pids = [p.project_id for p in db.query(models.Project).filter(models.Project.project_name == name).all()]
        for pid in pids:
            db.query(models.ProjectVehicle).filter(models.ProjectVehicle.project_id == pid).delete(synchronize_session=False)
        db.query(models.Project).filter(models.Project.project_name == name).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_finalize_distributes_by_effective(client, staff_headers):
    _clean()
    db = models.SessionLocal()
    try:
        p = models.Project(project_name="F사업", project_status="발급완료", issued_credits=300)
        db.add(p); db.flush()
        # effective 비율 100:200 → 발급 300 배분 = 100:200
        db.add(models.ProjectVehicle(project_id=p.project_id, vehicle_no="V1", effective_reduction=100))
        db.add(models.ProjectVehicle(project_id=p.project_id, vehicle_no="V2", effective_reduction=200))
        db.commit()
        pid = p.project_id
    finally:
        db.close()

    r = client.post(API.format(pid), headers=staff_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["finalized"] == 2 and body["method"] == "effective"

    db = models.SessionLocal()
    try:
        vs = {v.vehicle_no: float(v.final_reduction) for v in
              db.query(models.ProjectVehicle).filter(models.ProjectVehicle.project_id == pid).all()}
        assert vs["V1"] == 100.0 and vs["V2"] == 200.0
        assert round(sum(vs.values()), 3) == 300.0  # 발급 총량 정합
    finally:
        db.close()
    _clean()


def test_finalize_requires_issued_status(client, staff_headers):
    _clean()
    db = models.SessionLocal()
    try:
        p = models.Project(project_name="F사업", project_status="모니터링", issued_credits=100)
        db.add(p); db.flush()
        db.add(models.ProjectVehicle(project_id=p.project_id, vehicle_no="V1", effective_reduction=100))
        db.commit(); pid = p.project_id
    finally:
        db.close()
    r = client.post(API.format(pid), headers=staff_headers)
    assert r.status_code == 422  # 발급완료 아님
    _clean()


def test_finalize_equal_split_when_no_weights(client, staff_headers):
    _clean()
    db = models.SessionLocal()
    try:
        p = models.Project(project_name="F사업", project_status="발급완료", issued_credits=100)
        db.add(p); db.flush()
        db.add(models.ProjectVehicle(project_id=p.project_id, vehicle_no="V1"))
        db.add(models.ProjectVehicle(project_id=p.project_id, vehicle_no="V2"))
        db.commit(); pid = p.project_id
    finally:
        db.close()
    body = client.post(API.format(pid), headers=staff_headers).json()
    assert body["method"] == "equal"
    db = models.SessionLocal()
    try:
        vs = sorted(float(v.final_reduction) for v in
                    db.query(models.ProjectVehicle).filter(models.ProjectVehicle.project_id == pid).all())
        assert round(sum(vs), 3) == 100.0  # 균등이라도 총량 보존
    finally:
        db.close()
    _clean()


def test_requires_auth(client):
    assert client.post(API.format("x")).status_code == 401
