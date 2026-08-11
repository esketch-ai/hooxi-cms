"""운수사 보유 차량(fleet) — CRUD·참여 구분·전역 엑셀 업로드·업체명 매칭 (부록 M)."""

import io

import openpyxl

API = "/api/v1"


def _mk_client(client, headers, name):
    r = client.post(
        API + "/clients", headers=headers,
        json={"client_type": "TRANSPORT", "company_name": name},
    )
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


def _mk_project(client, headers, name):
    r = client.post(API + "/projects", headers=headers, json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def test_vehicle_status_codes_seeded(client, staff_headers):
    r = client.get(API + "/codes", headers=staff_headers, params={"category": "VEHICLE_STATUS"})
    assert r.status_code == 200, r.text
    assert {"운행", "폐차"} <= {c["code"] for c in r.json()}


def test_fleet_crud_and_region_derive(client, staff_headers):
    cid = _mk_client(client, staff_headers, "보유차량운수")
    r = client.post(
        f"{API}/clients/{cid}/vehicles", headers=staff_headers,
        json={"vehicle_no": "서울70사1234", "model_name": "BS106", "model_year": 2016},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["region"] == "서울"  # 차량번호 앞 2글자 파생
    assert body["status"] == "운행"  # 기본값
    # 중복 차량번호 → 409
    dup = client.post(f"{API}/clients/{cid}/vehicles", headers=staff_headers, json={"vehicle_no": "서울70사1234"})
    assert dup.status_code == 409, dup.text
    lr = client.get(f"{API}/clients/{cid}/vehicles", headers=staff_headers).json()
    assert lr["total"] == 1
    assert lr["participating_count"] == 0
    assert lr["unassigned_count"] == 1
    assert lr["items"][0]["participation"] is False


def test_fleet_participation_link(client, staff_headers):
    """fleet 차량과 같은 차량번호로 프로젝트 참여차량 등록 시 참여로 링크·표시."""
    cid = _mk_client(client, staff_headers, "참여링크운수")
    client.post(
        f"{API}/clients/{cid}/vehicles", headers=staff_headers,
        json={"vehicle_no": "부산71바5678", "client_id": cid},
    )
    pid = _mk_project(client, staff_headers, "참여링크사업")
    client.post(
        f"{API}/projects/{pid}/vehicles", headers=staff_headers,
        json={"vehicle_no": "부산71바5678", "client_id": cid, "introduction_type": "신규도입", "reduction_y1": 10},
    )
    lr = client.get(f"{API}/clients/{cid}/vehicles", headers=staff_headers).json()
    assert lr["participating_count"] == 1
    assert lr["unassigned_count"] == 0
    item = lr["items"][0]
    assert item["participation"] is True
    assert item["project_name"] == "참여링크사업"
    assert item["introduction_type"] == "신규도입"

    # participation 필터
    part = client.get(f"{API}/clients/{cid}/vehicles", headers=staff_headers, params={"participation": "participating"}).json()
    assert part["total"] == 1
    none = client.get(f"{API}/clients/{cid}/vehicles", headers=staff_headers, params={"participation": "unassigned"}).json()
    assert none["total"] == 0


_FLEET_HEADERS = [
    "차량번호", "업체명", "차대번호", "차명", "연식", "차량등록일", "차종",
    "길이(mm)", "너비(mm)", "높이(mm)", "총중량(kg)", "승차정원", "연료",
]


def _fleet_xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "BUS_LIST_ALL"
    ws.append(_FLEET_HEADERS)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def test_fleet_import_and_client_match(client, staff_headers):
    cid = _mk_client(client, staff_headers, "임포트매칭운수")
    rows = [
        # 업체명이 등록 운수사와 일치 → client 매칭
        ["대구72사0001", "임포트매칭운수", "VIN0001", "BS110", 2018, "2018-03-01", "대형 승합", 10600, 2490, 3200, 13455, 49, "경유"],
        # 미등록 업체 → client_id None
        ["광주73아0002", "미등록운수", "VIN0002", "NEW", 2020, "2020-05-01", "대형 승합", 10600, 2490, 3200, 13455, 45, "전기"],
    ]
    buf = _fleet_xlsx(rows)
    r = client.post(
        f"{API}/fleet/import", headers=staff_headers,
        files={"file": ("bus.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["created"] == 2
    assert res["client_matched"] == 1  # 임포트매칭운수만

    lr = client.get(f"{API}/clients/{cid}/vehicles", headers=staff_headers).json()
    assert lr["total"] == 1  # 매칭된 1대만 이 운수사 소속
    v = lr["items"][0]
    assert v["vehicle_no"] == "대구72사0001"
    assert v["model_year"] == 2018
    assert v["region"] == "대구"


def test_fleet_reimport_preserves_status(client, staff_headers):
    """월간 재업로드가 수기 폐차 status를 덮어쓰지 않는다(reviewer MEDIUM)."""
    cid = _mk_client(client, staff_headers, "재업로드보존운수")
    v = client.post(
        f"{API}/clients/{cid}/vehicles", headers=staff_headers,
        json={"vehicle_no": "대전75자9999", "status": "폐차"},
    ).json()
    assert v["status"] == "폐차"
    # 같은 차량번호로 재업로드(파일엔 status 컬럼 없음) → 폐차 보존, 스펙은 갱신
    buf = _fleet_xlsx([
        ["대전75자9999", "재업로드보존운수", "VINX", "BS110", 2019, "2019-01-01", "대형 승합", 1, 1, 1, 1, 40, "경유"],
    ])
    r = client.post(
        f"{API}/fleet/import", headers=staff_headers,
        files={"file": ("bus.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()
    assert r["updated"] == 1
    lr = client.get(f"{API}/clients/{cid}/vehicles", headers=staff_headers).json()
    item = lr["items"][0]
    assert item["status"] == "폐차"  # 수기 폐차 보존
    assert item["model_name"] == "BS110"  # 스펙은 파일로 갱신


def test_create_client_vehicle_backlinks_participation(client, staff_headers):
    """참여차량 먼저 등록 후 fleet 수기 생성 시 역링크되어 참여로 표시(reviewer MEDIUM)."""
    cid = _mk_client(client, staff_headers, "역링크운수")
    pid = _mk_project(client, staff_headers, "역링크사업")
    # fleet 없는 상태로 참여차량 등록 → client_vehicle_id None
    client.post(
        f"{API}/projects/{pid}/vehicles", headers=staff_headers,
        json={"vehicle_no": "인천76차4321", "client_id": cid, "reduction_y1": 3},
    )
    # 이후 fleet 수기 생성 → 역링크
    client.post(
        f"{API}/clients/{cid}/vehicles", headers=staff_headers,
        json={"vehicle_no": "인천76차4321"},
    )
    lr = client.get(f"{API}/clients/{cid}/vehicles", headers=staff_headers).json()
    assert lr["participating_count"] == 1
    assert lr["items"][0]["participation"] is True
