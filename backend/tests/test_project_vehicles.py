"""사업 참여 차량 (Phase 2 skeleton) — 등록·연차합 파생·도입구분 검증·집계·삭제정리."""

API = "/api/v1"
PROJECTS = API + "/projects"


def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers, json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def test_vehicle_intro_codes_seeded(client, staff_headers):
    r = client.get(API + "/codes", headers=staff_headers, params={"category": "VEHICLE_INTRO"})
    assert r.status_code == 200, r.text
    codes = {c["code"] for c in r.json()}
    assert {"신규도입", "대체도입"} <= codes


def test_create_vehicle_computes_total_reduction(client, staff_headers):
    pid = _mk_project(client, staff_headers, "차량집계검증")
    r = client.post(
        f"{PROJECTS}/{pid}/vehicles",
        headers=staff_headers,
        json={
            "vehicle_no": "제주79자7011",
            "introduction_type": "신규도입",
            "reduction_y1": 10.5,
            "reduction_y2": 20.25,
            "private_invest_ratio": 80,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["total_reduction"] == 30.75  # 서버 파생(연차 합)
    assert body["introduction_type"] == "신규도입"
    # 상세 집계 반영
    d = client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()
    assert d["vehicle_count"] == 1
    assert d["total_reduction"] == 30.75


def test_invalid_intro_type_422(client, staff_headers):
    pid = _mk_project(client, staff_headers, "도입구분검증")
    r = client.post(
        f"{PROJECTS}/{pid}/vehicles",
        headers=staff_headers,
        json={"vehicle_no": "X", "introduction_type": "없는구분"},
    )
    assert r.status_code == 422, r.text


def test_vehicle_list_totals(client, staff_headers):
    pid = _mk_project(client, staff_headers, "차량목록검증")
    for y, payout in [(5, 100000), (15, None)]:
        client.post(
            f"{PROJECTS}/{pid}/vehicles",
            headers=staff_headers,
            json={"reduction_y1": y, "expected_payout": payout},
        )
    lr = client.get(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers).json()
    assert lr["total"] == 2
    assert lr["total_reduction"] == 20  # 5 + 15
    assert lr["total_expected_payout"] == 100000  # 입력분만 합산


def test_update_and_delete_vehicle(client, staff_headers):
    pid = _mk_project(client, staff_headers, "차량수정삭제검증")
    v = client.post(
        f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json={"reduction_y1": 1}
    ).json()
    vid = v["vehicle_id"]
    # 부분 수정 — 연차 추가 시 total_reduction 재계산
    r = client.put(
        f"{PROJECTS}/{pid}/vehicles/{vid}", headers=staff_headers, json={"reduction_y2": 4}
    )
    assert r.status_code == 200, r.text
    assert r.json()["total_reduction"] == 5  # 1 + 4
    # 삭제
    assert client.delete(f"{PROJECTS}/{pid}/vehicles/{vid}", headers=staff_headers).status_code == 200
    assert client.get(f"{PROJECTS}/{pid}", headers=staff_headers).json()["vehicle_count"] == 0


def test_delete_project_removes_vehicles(client, staff_headers, manager_headers):
    pid = _mk_project(client, staff_headers, "차량정리검증")
    client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json={"reduction_y1": 3})
    r = client.delete(f"{PROJECTS}/{pid}", headers=manager_headers)
    assert r.status_code == 200, r.text  # 차량 자식 있어도 삭제 성공(FK)


def test_vehicle_rejects_unknown_asset(client, staff_headers):
    pid = _mk_project(client, staff_headers, "차량자산검증")
    r = client.post(
        f"{PROJECTS}/{pid}/vehicles",
        headers=staff_headers,
        json={"vehicle_no": "X", "asset_id": "없는자산id"},
    )
    assert r.status_code == 404, r.text  # 존재하지 않는 자산 참조 거부
