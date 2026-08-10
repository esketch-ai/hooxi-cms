"""감축사업 진행 단계·지연 관찰 (Phase 1) — 시드·지연판정·상태전이 자동기록·부분편집."""

API = "/api/v1"
PROJECTS = API + "/projects"


def _mk_project(client, headers, name, status="기획"):
    r = client.post(
        PROJECTS, headers=headers, json={"project_name": name, "project_status": status}
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_stages_seeded_on_create(client, staff_headers):
    p = _mk_project(client, staff_headers, "단계시드검증")
    stages = p["stages"]
    codes = [s["stage_code"] for s in stages]
    # 세션 공유 DB라 코드 개수는 고정 가정하지 않음 — 5단계가 모두 시드됐는지(부분집합)만 확인
    assert {"기획", "등록완료", "모니터링", "검증", "발급완료"} <= set(codes)
    assert all(s["actual_date"] is None and s["delayed"] is False for s in stages)
    assert p["delayed_stage_count"] == 0


def test_planned_past_is_delayed_and_surfaced(client, staff_headers):
    p = _mk_project(client, staff_headers, "지연판정검증")
    pid = p["project_id"]
    r = client.put(
        f"{PROJECTS}/{pid}/stages",
        headers=staff_headers,
        json={"stages": [{"stage_code": "등록완료", "planned_date": "2020-01-01"}]},
    )
    assert r.status_code == 200, r.text
    reg = [s for s in r.json()["stages"] if s["stage_code"] == "등록완료"][0]
    assert reg["delayed"] is True
    assert r.json()["delayed_stage_count"] >= 1
    # 목록 표식
    lr = client.get(PROJECTS, headers=staff_headers, params={"search": "지연판정검증"})
    item = [i for i in lr.json()["items"] if i["project_id"] == pid][0]
    assert item["delayed_stage_count"] >= 1
    # 관찰 엔드포인트
    d = client.get(f"{PROJECTS}/stage-delays", headers=staff_headers)
    assert any(
        a["project_id"] == pid and a["stage_code"] == "등록완료"
        for a in d.json()["delayed"]
    )


def test_status_change_sets_actual_and_clears_delay(client, staff_headers):
    p = _mk_project(client, staff_headers, "상태전이검증")
    pid = p["project_id"]
    client.put(
        f"{PROJECTS}/{pid}/stages",
        headers=staff_headers,
        json={"stages": [{"stage_code": "등록완료", "planned_date": "2020-01-01"}]},
    )
    r = client.put(
        f"{PROJECTS}/{pid}", headers=staff_headers, json={"project_status": "등록완료"}
    )
    assert r.status_code == 200, r.text
    reg = [s for s in r.json()["stages"] if s["stage_code"] == "등록완료"][0]
    assert reg["actual_date"] is not None  # 도달일 자동 기록
    assert reg["delayed"] is False  # 도달했으므로 지연 해제


def test_partial_stage_update_keeps_actual(client, staff_headers):
    p = _mk_project(client, staff_headers, "부분편집검증")
    pid = p["project_id"]
    client.put(
        f"{PROJECTS}/{pid}/stages",
        headers=staff_headers,
        json={"stages": [{"stage_code": "기획", "actual_date": "2024-01-01"}]},
    )
    r = client.put(
        f"{PROJECTS}/{pid}/stages",
        headers=staff_headers,
        json={"stages": [{"stage_code": "기획", "planned_date": "2024-02-01"}]},
    )
    plan = [s for s in r.json()["stages"] if s["stage_code"] == "기획"][0]
    assert plan["actual_date"] == "2024-01-01"  # 미전달 필드 유지
    assert plan["planned_date"] == "2024-02-01"


def test_delete_project_removes_stages(client, staff_headers, manager_headers):
    # 단계 자식 행이 있어도 사업 삭제가 성공해야 함(Postgres FK 위반 방지)
    p = _mk_project(client, staff_headers, "삭제검증사업")
    pid = p["project_id"]
    assert len(p["stages"]) >= 5  # 시드된 단계 존재
    r = client.delete(f"{PROJECTS}/{pid}", headers=manager_headers)
    assert r.status_code == 200, r.text
    assert client.get(f"{PROJECTS}/{pid}", headers=staff_headers).status_code == 404


def test_edit_without_status_change_keeps_delay(client, staff_headers):
    # 상태 미변경 일반 수정은 단계 도달일을 찍지 않아 지연이 유지돼야 함
    p = _mk_project(client, staff_headers, "지연유지검증")
    pid = p["project_id"]
    client.put(
        f"{PROJECTS}/{pid}/stages",
        headers=staff_headers,
        json={"stages": [{"stage_code": "기획", "planned_date": "2020-01-01"}]},
    )
    # 사업명만 수정(project_status는 폼처럼 동일값 재전송)
    r = client.put(
        f"{PROJECTS}/{pid}",
        headers=staff_headers,
        json={"project_name": "지연유지검증-수정", "project_status": "기획"},
    )
    assert r.status_code == 200, r.text
    plan = [s for s in r.json()["stages"] if s["stage_code"] == "기획"][0]
    assert plan["actual_date"] is None  # 실제 전이 아니므로 도달일 미기록
    assert plan["delayed"] is True  # 지연 유지


def test_invalid_stage_code_422(client, staff_headers):
    p = _mk_project(client, staff_headers, "무효단계검증")
    pid = p["project_id"]
    r = client.put(
        f"{PROJECTS}/{pid}/stages",
        headers=staff_headers,
        json={"stages": [{"stage_code": "없는단계", "planned_date": "2024-01-01"}]},
    )
    assert r.status_code == 422, r.text
