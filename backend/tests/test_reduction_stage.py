"""3단계 감축량 스냅샷·비교(D6 P5) — 예상/모니터링/최종 + 달성률."""

import models

SAVE = "/api/v1/reduction-stages/{0}"
COMPARE = "/api/v1/reduction-stages/compare"


def _seed_input(project_distance):
    db = models.SessionLocal()
    try:
        db.query(models.ReductionStage).delete(synchronize_session=False)
        db.query(models.VehicleCalcInput).delete(synchronize_session=False)
        db.add(models.VehicleCalcInput(
            vehicle_no="강원70자1088", operator_name="춘천시민버스", region="강원", fuel="CNG",
            baseline_distance=73218.33636363636, baseline_fuel=48344.80124954544,
            project_distance=project_distance, project_kwh=83636.09999999999,
            ev_reg_year=2023, private_ratio=0.4))
        db.commit()
    finally:
        db.close()


def _clean():
    db = models.SessionLocal()
    try:
        db.query(models.ReductionStage).delete(synchronize_session=False)
        db.query(models.VehicleCalcInput).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_stage_snapshot_and_compare(client, staff_headers):
    # 예상 저장(계획 주행)
    _seed_input(69399.53571428571)
    r = client.post(SAVE.format("PLANNED"), headers=staff_headers)
    assert r.status_code == 200, r.text
    assert r.json()["saved"] == 1 and r.json()["stage"] == "PLANNED"

    # 실측으로 project 갱신 후 모니터링 저장(주행 감소 → 감축량 변화)
    _seed_input(60000.0)
    # 예상 스냅샷은 유지되고 모니터링만 새로 — 입력 재시드해도 스냅샷 테이블은 위에서 안 지움
    # (여기선 _seed_input이 스냅샷을 지우므로 재구성: 예상 다시 저장 안 하고 직접 확인)
    db = models.SessionLocal()
    try:
        db.add(models.ReductionStage(vehicle_no="강원70자1088", stage="PLANNED",
                                     operator_name="춘천시민버스", region="강원",
                                     total_reduction=100.0))
        db.commit()
    finally:
        db.close()
    r2 = client.post(SAVE.format("MONITORING"), headers=staff_headers)
    assert r2.json()["saved"] == 1

    comp = client.get(COMPARE, headers=staff_headers).json()
    assert comp["vehicle_count"] == 1
    item = comp["items"][0]
    assert item["planned"] == 100.0
    assert item["monitoring"] is not None and item["monitoring"] > 0
    # 달성률 = 모니터링/예상 × 100
    assert abs(item["ach_monitoring"] - item["monitoring"] / 100.0 * 100) < 0.2
    assert item["final"] is None and item["ach_final"] is None
    _clean()


def test_unknown_stage_422(client, staff_headers):
    r = client.post(SAVE.format("BOGUS"), headers=staff_headers)
    assert r.status_code == 422


def test_compare_requires_auth(client):
    assert client.get(COMPARE).status_code == 401
