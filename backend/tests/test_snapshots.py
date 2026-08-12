"""변동 이력 스냅샷 2종(append-only) — Phase 4 INC-3 / 부록 N.8 D5.

파생값은 제자리 계산을 유지(불변)하고, 변동 시점에만 스냅샷을 append한다.
직전 스냅샷과 값이 같으면 기록하지 않는다(dedup). 스냅샷 카운트는 DB 직접 조회.
"""

import models

API = "/api/v1"
PROJECTS = API + "/projects"


def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers, json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _participation_rows(project_id):
    """(project) 참여 스냅샷 목록(captured_at 오름차순) — DB 직접 조회."""
    db = models.SessionLocal()
    try:
        return (
            db.query(models.ProjectParticipationSnapshot)
            .filter(models.ProjectParticipationSnapshot.project_id == project_id)
            .order_by(models.ProjectParticipationSnapshot.captured_at.asc())
            .all()
        )
    finally:
        db.close()


def _sale_rows(project_id):
    """(project) 거래계약 스냅샷 목록(captured_at 오름차순) — DB 직접 조회."""
    db = models.SessionLocal()
    try:
        return (
            db.query(models.ProjectSaleSnapshot)
            .filter(models.ProjectSaleSnapshot.project_id == project_id)
            .order_by(models.ProjectSaleSnapshot.captured_at.asc())
            .all()
        )
    finally:
        db.close()


def _capped_vehicle(reduction_per_year):
    """잔여차령 8 캡 노후차 페이로드 — y1..y8 동일값(y9·y10 가중 0). 등록 2016-01-01."""
    p = {"registered_at": "2016-01-01"}
    for i in range(1, 9):
        p[f"reduction_y{i}"] = reduction_per_year
    return p


def test_participation_snapshot_append_and_dedup(client, staff_headers):
    """차량 등록(vehicle_cud) → payout-params(값 변동) → 재적용(dedup) → 차량 수정(변동)."""
    pid = _mk_project(client, staff_headers, "참여스냅샷검증")

    # 차량 등록 — 승인일 미설정이라 예상지급액 파생 불가(eff sum=0, pay=None), 스냅샷 1행
    v = client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=_capped_vehicle(10)).json()
    vid = v["vehicle_id"]
    rows = _participation_rows(pid)
    assert len(rows) == 1
    assert rows[0].trigger == "vehicle_cud"
    assert float(rows[0].effective_reduction_sum) == 0.0
    assert rows[0].expected_payout_sum is None

    # 지급 파라미터 입력 → 예상지급액 파생(값 변동) → 새 스냅샷 append
    r = client.put(
        f"{PROJECTS}/{pid}/payout-params",
        headers=staff_headers,
        json={"max_payment": 2000000, "approved_at": "2016-02-01"},
    )
    assert r.status_code == 200, r.text
    rows = _participation_rows(pid)
    assert len(rows) == 2
    latest = rows[-1]
    assert latest.trigger == "payout_params"
    assert float(latest.effective_reduction_sum) == 80.0  # MIN(240, y1..y8 전액 80)
    assert float(latest.expected_payout_sum) == 666666  # TRUNC(2,000,000 × 80/240 × 8/8)

    # 동일 파라미터 재적용(값 무변) → dedup, 행 미증가
    r = client.put(
        f"{PROJECTS}/{pid}/payout-params",
        headers=staff_headers,
        json={"max_payment": 2000000, "approved_at": "2016-02-01"},
    )
    assert r.status_code == 200, r.text
    assert len(_participation_rows(pid)) == 2  # dedup

    # 감축량 바뀌는 차량 수정 → 예상지급액 재계산(값 변동) → 새 스냅샷 append
    r = client.put(
        f"{PROJECTS}/{pid}/vehicles/{vid}", headers=staff_headers, json={"reduction_y1": 20}
    )
    assert r.status_code == 200, r.text
    rows = _participation_rows(pid)
    assert len(rows) == 3
    assert rows[-1].trigger == "vehicle_cud"
    assert float(rows[-1].effective_reduction_sum) == 90.0  # 20 + 10×7


def test_sale_snapshot_append_and_dedup(client, staff_headers):
    """거래계약 생성(sale_cud) → 동일 재저장(dedup) → 실발행액/수량 변경(변동)."""
    pid = _mk_project(client, staff_headers, "거래스냅샷검증")

    # 거래계약 생성 → 스냅샷 append (gross = 단가×수량, 실발행액 미입력)
    s = client.post(
        f"{PROJECTS}/{pid}/sales",
        headers=staff_headers,
        json={"buyer_name": "증권X", "sale_unit_price": 15000, "quantity": 3000},
    ).json()
    sid = s["sale_id"]
    rows = _sale_rows(pid)
    assert len(rows) == 1
    assert rows[0].trigger == "sale_cud"
    assert float(rows[0].quantity) == 3000.0
    assert float(rows[0].gross_revenue) == 45000000.0  # 15000 × 3000

    # 동일 값 재저장 → dedup, 행 미증가
    r = client.put(
        f"{PROJECTS}/{pid}/sales/{sid}", headers=staff_headers, json={"quantity": 3000}
    )
    assert r.status_code == 200, r.text
    assert len(_sale_rows(pid)) == 1  # dedup

    # 실발행액 입력 → gross가 실발행액 우선으로 전환(값 변동) → 새 스냅샷
    r = client.put(
        f"{PROJECTS}/{pid}/sales/{sid}",
        headers=staff_headers,
        json={"sale_invoice_amount": 50000000},
    )
    assert r.status_code == 200, r.text
    rows = _sale_rows(pid)
    assert len(rows) == 2
    assert float(rows[-1].gross_revenue) == 50000000.0  # 실발행액 우선

    # 수량 변경(값 변동) → 새 스냅샷
    r = client.put(
        f"{PROJECTS}/{pid}/sales/{sid}", headers=staff_headers, json={"quantity": 3500}
    )
    assert r.status_code == 200, r.text
    rows = _sale_rows(pid)
    assert len(rows) == 3
    assert float(rows[-1].quantity) == 3500.0
