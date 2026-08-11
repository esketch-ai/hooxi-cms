"""사업 참여 차량 (Phase 2 skeleton) — 등록·연차합 파생·도입구분 검증·집계·삭제정리·엑셀 업로드."""

import io

import openpyxl

from services.import_spec import IMPORT_SPECS

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
    for y in (5, 15):
        client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json={"reduction_y1": y})
    lr = client.get(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers).json()
    assert lr["total"] == 2
    assert lr["total_reduction"] == 20  # 5 + 15
    # 원가단가 미입력 → 예상지급액 파생 불가(전건 null → 합계 null)
    assert lr["total_expected_payout"] is None


def test_payout_price_derives_expected_payout(client, staff_headers):
    """원가 톤당 단가 입력 시 전 차량 예상지급액=총감축량×단가 순수 파생 (H.4 일원화)."""
    pid = _mk_project(client, staff_headers, "예상지급액파생검증")
    for y in (5, 15):
        client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json={"reduction_y1": y})
    # 원가단가 10000 입력 → 승인일 자동 세팅 + 전 차량 파생
    r = client.put(f"{PROJECTS}/{pid}/payout-price", headers=staff_headers, json={"unit_price": 10000})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["payout_unit_price"] == 10000
    assert body["approved_at"]  # 미전달 → 오늘로 자동
    lr = client.get(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers).json()
    payouts = sorted(v["expected_payout"] for v in lr["items"])
    assert payouts == [50000, 150000]  # 5×10000, 15×10000
    assert lr["total_expected_payout"] == 200000
    # 신규 차량도 현재 단가로 자동 파생
    v = client.post(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, json={"reduction_y1": 2}).json()
    assert v["expected_payout"] == 20000
    # 요청 바디의 예상지급액 수기값은 무시(스키마에서 제거 → 파생만)
    v2 = client.post(
        f"{PROJECTS}/{pid}/vehicles",
        headers=staff_headers,
        json={"reduction_y1": 1, "expected_payout": 999999},
    ).json()
    assert v2["expected_payout"] == 10000  # 1×10000 (수기 999999 무시)
    # 단가 해제(null) → 전 차량 예상지급액 null
    client.put(f"{PROJECTS}/{pid}/payout-price", headers=staff_headers, json={"unit_price": None})
    lr2 = client.get(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers).json()
    assert all(v["expected_payout"] is None for v in lr2["items"])
    assert lr2["total_expected_payout"] is None


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


def test_vehicle_list_pagination_and_search(client, staff_headers):
    pid = _mk_project(client, staff_headers, "차량페이지검증")
    for i in range(3):
        client.post(
            f"{PROJECTS}/{pid}/vehicles",
            headers=staff_headers,
            json={"vehicle_no": f"페이지차량{i}", "reduction_y1": 1},
        )
    # page_size=2 → 1페이지 2건, total=3
    p1 = client.get(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, params={"page_size": 2, "page": 1}).json()
    assert p1["total"] == 3 and len(p1["items"]) == 2
    p2 = client.get(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, params={"page_size": 2, "page": 2}).json()
    assert len(p2["items"]) == 1
    # 검색(차량번호)
    s = client.get(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers, params={"search": "페이지차량1"}).json()
    assert s["total"] == 1 and s["items"][0]["vehicle_no"] == "페이지차량1"


def test_vehicle_template_download(client, staff_headers):
    pid = _mk_project(client, staff_headers, "차량양식검증")
    r = client.get(f"{PROJECTS}/{pid}/vehicles/template", headers=staff_headers)
    assert r.status_code == 200, r.text
    assert "spreadsheet" in r.headers.get("content-type", "")


def test_vehicle_excel_commit(client, staff_headers):
    pid = _mk_project(client, staff_headers, "차량업로드검증")
    headers = [c.label for c in IMPORT_SPECS["project_vehicles"].columns]
    # 헤더 → 값 매핑(빈 값은 생략). 운수사는 resolver 의존 피하려 비움.
    row = {"차량번호": "테스트차량1", "도입구분": "신규도입", "1차 감축량": 5, "2차 감축량": 10}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    ws.append([row.get(h, None) for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    r = client.post(
        f"{PROJECTS}/{pid}/vehicles/commit",
        headers=staff_headers,
        files={"file": ("veh.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1, body
    # 삽입된 차량의 total_reduction 서버 파생 확인
    lr = client.get(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers).json()
    assert lr["total"] == 1
    v = lr["items"][0]
    assert v["vehicle_no"] == "테스트차량1"
    assert v["total_reduction"] == 15
    assert v["introduction_type"] == "신규도입"


def test_vehicle_excel_skips_garbage(client, staff_headers):
    # 스펙과 무관한 헤더의 파일 → 빈 차량 대량 삽입 방지(created 0, 데이터행은 skipped)
    pid = _mk_project(client, staff_headers, "차량업로드가비지")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["엉뚱헤더A", "엉뚱헤더B"])
    ws.append(["값1", "값2"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    r = client.post(
        f"{PROJECTS}/{pid}/vehicles/commit",
        headers=staff_headers,
        files={"file": ("g.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 0
    assert client.get(f"{PROJECTS}/{pid}/vehicles", headers=staff_headers).json()["total"] == 0


def test_vehicle_rejects_unknown_asset(client, staff_headers):
    pid = _mk_project(client, staff_headers, "차량자산검증")
    r = client.post(
        f"{PROJECTS}/{pid}/vehicles",
        headers=staff_headers,
        json={"vehicle_no": "X", "asset_id": "없는자산id"},
    )
    assert r.status_code == 404, r.text  # 존재하지 않는 자산 참조 거부
