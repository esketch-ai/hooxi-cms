"""감축 사업 기준값 리졸버(P0-2 증분1) — tb_config project_base_params 승격.

회귀 0이 최우선: 설정 미저장 시 base_params()가 현행 코드 기본값(240/8/108/2000000)을
그대로 반환해 기존 계산이 비트 동일해야 한다. 설정 저장 시 재계산 파생값이 새 기준으로
바뀌고, 부분 저장 시 나머지 키는 기본값으로 폴백한다.
"""

import json

import models
from services.project_params import DEFAULT_PROJECT_BASE_PARAMS, base_params

API = "/api/v1"
PROJECTS = API + "/projects"
CONFIG_KEY = "project_base_params"


def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers, json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _set_params(client, admin_headers, obj):
    r = client.put(
        f"{API}/config/{CONFIG_KEY}",
        headers=admin_headers,
        json={"config_value": json.dumps(obj)},
    )
    assert r.status_code == 200, r.text


def _delete_params():
    """테스트 격리 — config 행·이력 정리."""
    db = models.SessionLocal()
    try:
        db.query(models.ConfigHistory).filter(
            models.ConfigHistory.config_key == CONFIG_KEY
        ).delete()
        row = db.get(models.Config, CONFIG_KEY)
        if row is not None:
            db.delete(row)
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# (a) 미저장 → 코드 기본값(회귀 0 증명)
# ---------------------------------------------------------------------------
def test_base_params_defaults_when_unsaved():
    _delete_params()
    db = models.SessionLocal()
    try:
        params = base_params(db)
    finally:
        db.close()
    assert params["base_reduction"] == 240.0
    assert params["base_vehicle_age"] == 8.0
    assert params["expire_months"] == 108
    assert params["default_max_payment"] == 2000000
    assert params == DEFAULT_PROJECT_BASE_PARAMS


# ---------------------------------------------------------------------------
# (b) 기준감축량 변경 → expected_payout이 새 기준으로 변함
# ---------------------------------------------------------------------------
def test_base_reduction_override_changes_payout(client, staff_headers, admin_headers):
    _delete_params()
    pid = _mk_project(client, staff_headers, "기준감축량변경검증")
    payload = {"registered_at": "2016-01-01", "reduction_y9": 5, "reduction_y10": 5}
    for i in range(1, 9):
        payload[f"reduction_y{i}"] = 10
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=payload)

    # 기준감축량 240 → 200으로 승격. 잔여반영감축량은 MIN(base, 80)=80(변화 없음)이지만
    # 분모 기준감축량이 200으로 낮아져 payout이 커진다. TRUNC(2,000,000 × 80/200 × 8/8)=800000.
    _set_params(client, admin_headers, {"base_reduction": 200})
    r = client.put(
        f"{PROJECTS}/{pid}/payout-params",
        headers=staff_headers,
        json={"max_payment": 2000000, "approved_at": "2016-02-01"},
    )
    assert r.status_code == 200, r.text
    lr = client.get(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers).json()
    item = lr["items"][0]
    assert item["expected_payout"] == 800000  # 240 기본이면 666666 → 새 기준 반영
    _delete_params()


# ---------------------------------------------------------------------------
# (c) expire_months 변경 → expire_at 변함
# ---------------------------------------------------------------------------
def test_expire_months_override_changes_expire_at(client, staff_headers, admin_headers):
    _delete_params()
    pid = _mk_project(client, staff_headers, "만료개월변경검증")
    payload = {"registered_at": "2016-01-01", "reduction_y1": 10}
    v = client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json=payload).json()
    assert v["expire_at"] == "2024-12-31"  # 등록일+108개월−1일(기본)

    # 만료개월 108 → 120. 파생값 재계산은 payout-params 저장 경로에서 트리거.
    _set_params(client, admin_headers, {"expire_months": 120})
    client.put(
        f"{PROJECTS}/{pid}/payout-params",
        headers=staff_headers,
        json={"max_payment": 2000000, "approved_at": "2016-02-01"},
    )
    lr = client.get(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers).json()
    assert lr["items"][0]["expire_at"] == "2025-12-31"  # +120개월−1일
    _delete_params()


# ---------------------------------------------------------------------------
# (d) 부분 저장 → 나머지 키는 기본값 폴백
# ---------------------------------------------------------------------------
def test_partial_save_falls_back_to_defaults():
    _delete_params()
    db = models.SessionLocal()
    try:
        db.add(models.Config(config_key=CONFIG_KEY, config_value=json.dumps({"base_reduction": 200})))
        db.commit()
        params = base_params(db)
    finally:
        db.close()
    assert params["base_reduction"] == 200.0        # 저장값
    assert params["base_vehicle_age"] == 8.0        # 폴백
    assert params["expire_months"] == 108           # 폴백
    assert params["default_max_payment"] == 2000000  # 폴백
    _delete_params()
