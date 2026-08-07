"""지역(REGION) 공통코드화 — 시드·드롭다운 소스·생성/수정 검증 (SCR-03)."""

API = "/api/v1"


def test_region_codes_seeded(client, staff_headers):
    resp = client.get(API + "/codes", headers=staff_headers, params={"category": "REGION"})
    assert resp.status_code == 200, resp.text
    codes = {c["code"] for c in resp.json()}
    # 17개 시/도가 모두 시드되어 드롭다운 소스로 제공
    assert {"서울", "부산", "제주", "세종", "경기"} <= codes
    assert len(codes) == 17


def test_create_client_rejects_unknown_region(client, staff_headers):
    resp = client.post(
        API + "/clients",
        headers=staff_headers,
        json={"client_type": "TRANSPORT", "company_name": "지역검증운수", "region": "제주도"},
    )
    assert resp.status_code == 422, resp.text  # 표기흔들림('제주도')은 코드 아님 → 거부


def test_create_and_update_client_with_valid_region(client, staff_headers):
    resp = client.post(
        API + "/clients",
        headers=staff_headers,
        json={"client_type": "TRANSPORT", "company_name": "지역코드운수", "region": "제주"},
    )
    assert resp.status_code == 201, resp.text
    cid = resp.json()["client_id"]
    assert resp.json()["region"] == "제주"

    # 유효 코드로 변경 OK
    ok = client.put(API + "/clients/" + cid, headers=staff_headers, json={"region": "서울"})
    assert ok.status_code == 200, ok.text
    # 무효 코드로 변경은 거부
    bad = client.put(API + "/clients/" + cid, headers=staff_headers, json={"region": "서울특별시"})
    assert bad.status_code == 422, bad.text


def test_blank_region_allowed(client, staff_headers):
    # 지역은 선택 항목 — 빈값/미입력은 통과(None 정규화)
    resp = client.post(
        API + "/clients",
        headers=staff_headers,
        json={"client_type": "TRANSPORT", "company_name": "지역미입력운수", "region": ""},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["region"] is None
