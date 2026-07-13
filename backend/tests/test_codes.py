"""공통 코드 마스터(tb_code) — SCR-14 공통 코드 관리 스모크.

검증 포인트:
- 내장 구분(CLIENT_TYPE: TRANSPORT/FACILITY) 시드 존재·조회
- ADMIN 추가/수정/비활성/삭제, STAFF 변경 차단
- 코드값 중복 409, 내장 코드 삭제 차단 409
- 사용 중(고객사 참조) 코드 삭제 차단 409, 비활성 전환은 허용
- 고객사 등록 시 유효하지 않은 구분 422, 신규 활성 구분은 등록 허용
"""

API = "/api/v1"


def _codes(client, headers, **params):
    return client.get(f"{API}/codes", params={"category": "CLIENT_TYPE", **params}, headers=headers)


def test_builtin_client_types_seeded(client, admin_headers):
    resp = _codes(client, admin_headers)
    assert resp.status_code == 200, resp.text
    by_code = {c["code"]: c for c in resp.json()}
    assert by_code["TRANSPORT"]["label"] == "운수사"
    assert by_code["FACILITY"]["label"] == "건물·농장"
    assert by_code["TRANSPORT"]["is_system"] == "Y"


def test_staff_cannot_mutate(client, staff_headers):
    resp = client.post(
        f"{API}/codes",
        json={"category": "CLIENT_TYPE", "code": "FARM", "label": "농장"},
        headers=staff_headers,
    )
    assert resp.status_code == 403


def test_admin_crud_and_guards(client, admin_headers):
    # 추가
    resp = client.post(
        f"{API}/codes",
        json={"category": "CLIENT_TYPE", "code": "LOGISTICS", "label": "물류사", "sort_order": 30},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["code"] == "LOGISTICS"
    assert created["is_system"] == "N"
    code_id = created["code_id"]

    # 중복 코드값 409
    dup = client.post(
        f"{API}/codes",
        json={"category": "CLIENT_TYPE", "code": "logistics", "label": "중복"},
        headers=admin_headers,
    )
    assert dup.status_code == 409

    # 라벨 수정
    upd = client.put(
        f"{API}/codes/{code_id}", json={"label": "물류·창고"}, headers=admin_headers
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["label"] == "물류·창고"

    # 미사용 코드 삭제 허용
    dele = client.delete(f"{API}/codes/{code_id}", headers=admin_headers)
    assert dele.status_code == 204


def test_builtin_code_delete_blocked(client, admin_headers):
    transport = next(
        c for c in _codes(client, admin_headers).json() if c["code"] == "TRANSPORT"
    )
    resp = client.delete(f"{API}/codes/{transport['code_id']}", headers=admin_headers)
    assert resp.status_code == 409  # 내장 코드 삭제 불가


def test_client_type_validation_and_in_use_guard(client, admin_headers):
    # 신규 구분 추가 → 활성
    resp = client.post(
        f"{API}/codes",
        json={"category": "CLIENT_TYPE", "code": "FARM", "label": "농장", "sort_order": 40},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    farm_id = resp.json()["code_id"]

    # 유효하지 않은 구분으로 고객사 등록 → 422
    bad = client.post(
        f"{API}/clients",
        json={"client_type": "NOPE", "company_name": "잘못된구분사"},
        headers=admin_headers,
    )
    assert bad.status_code == 422, bad.text

    # 신규 활성 구분으로 고객사 등록 → 성공
    ok = client.post(
        f"{API}/clients",
        json={"client_type": "FARM", "company_name": "행복농장"},
        headers=admin_headers,
    )
    assert ok.status_code == 201, ok.text

    # 사용 중이므로 삭제 차단 409
    blocked = client.delete(f"{API}/codes/{farm_id}", headers=admin_headers)
    assert blocked.status_code == 409

    # 비활성 전환은 허용 → 드롭다운(활성)에서 제외, 관리 목록엔 표시
    deact = client.put(f"{API}/codes/{farm_id}", json={"active": "N"}, headers=admin_headers)
    assert deact.status_code == 200, deact.text
    active_codes = {c["code"] for c in _codes(client, admin_headers).json()}
    assert "FARM" not in active_codes
    all_codes = {c["code"] for c in _codes(client, admin_headers, include_inactive=True).json()}
    assert "FARM" in all_codes
