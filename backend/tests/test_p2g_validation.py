"""P2-G 백엔드 검증 마감 테스트 — 실무 정합성 시나리오 #3·#5·#6 잔여 6건.

1. 스키마 길이 정합 — String(N) 컬럼 대응 입력 필드 max_length → 초과 시 422
2. 정산 산식 상한 — unit_price·expected_credits le=1e12 + expected_amount Numeric(15,2) 초과 422
3. 일정 시간 역전 — end_at < start_at 422
4. 검색 와일드카드 이스케이프 — %·_ 검색은 리터럴 매치만
5. soft 삭제 세그먼트 PUT 404
6. 시간대 접미사 거부 — 벽시계 datetime 입력에 tz-aware(Z/+09:00) 422
"""

API = "/api/v1"
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


def _create_client(client, headers, name, **extra):
    payload = {"client_type": "TRANSPORT", "company_name": name}
    payload.update(extra)
    resp = client.post(API + "/clients", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["client_id"]


# ---------------------------------------------------------------------------
# 4. 검색 와일드카드 이스케이프 — %·_는 리터럴 매치만
# ---------------------------------------------------------------------------
def test_setup_wildcard_clients(client, staff_headers):
    """와일드카드 문자를 포함한 고객사 + 평범한 고객사 준비."""
    S["c_percent"] = _create_client(client, staff_headers, "P2G 100% 달성운수")
    S["c_under"] = _create_client(client, staff_headers, "P2G_언더스코어운수")
    S["c_plain"] = _create_client(client, staff_headers, "P2G평범운수")


def test_client_search_percent_literal(client, staff_headers):
    """'%' 검색 — 전체 매치가 아니라 이름에 %가 든 고객사만."""
    resp = client.get(API + "/clients", params={"search": "100%"}, headers=staff_headers)
    assert resp.status_code == 200
    names = [c["company_name"] for c in resp.json()["items"]]
    assert names == ["P2G 100% 달성운수"]

    # '%' 단독 검색도 리터럴 — 평범한 고객사는 미포함
    resp = client.get(API + "/clients", params={"search": "%"}, headers=staff_headers)
    names = [c["company_name"] for c in resp.json()["items"]]
    assert "P2G평범운수" not in names
    assert "P2G 100% 달성운수" in names


def test_client_search_underscore_literal(client, staff_headers):
    """'_' 검색 — 임의 1글자 매치가 아니라 이름에 _가 든 고객사만."""
    resp = client.get(API + "/clients", params={"search": "P2G_"}, headers=staff_headers)
    assert resp.status_code == 200
    names = [c["company_name"] for c in resp.json()["items"]]
    assert names == ["P2G_언더스코어운수"]


def test_history_and_document_search_escaped(client, staff_headers):
    """활동 이력·문서 검색도 동일하게 이스케이프."""
    resp = client.post(
        API + "/histories",
        headers=staff_headers,
        json={
            "client_id": S["c_plain"],
            "activity_date": "2026-07-01T10:00:00",
            "activity_type": "CALL",
            "title": "P2G 50%_할인 문의",
        },
    )
    assert resp.status_code == 201, resp.text

    resp = client.get(API + "/histories", params={"search": "50%_할인"}, headers=staff_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # 이스케이프가 없다면 '50X할인' 류도 매치됐을 패턴 — 리터럴이라 0건
    resp = client.get(API + "/histories", params={"search": "5_%_할인"}, headers=staff_headers)
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# 3. 일정 시간 역전 — end_at < start_at 422
# ---------------------------------------------------------------------------
def test_schedule_create_time_inversion_422(client, staff_headers):
    resp = client.post(
        API + "/schedules",
        headers=staff_headers,
        json={
            "schedule_type": "MEETING",
            "title": "P2G 역전 일정",
            "start_at": "2026-07-20T15:00:00",
            "end_at": "2026-07-20T14:00:00",
        },
    )
    assert resp.status_code == 422
    assert "종료 시각이 시작 시각보다 빠릅니다" in resp.text


def test_schedule_update_time_inversion_422(client, staff_headers):
    resp = client.post(
        API + "/schedules",
        headers=staff_headers,
        json={
            "schedule_type": "MEETING",
            "title": "P2G 정상 일정",
            "start_at": "2026-07-20T10:00:00",
            "end_at": "2026-07-20T11:00:00",
        },
    )
    assert resp.status_code == 201, resp.text
    S["schedule_id"] = resp.json()["schedule_id"]

    # 둘 다 전달 — 스키마 검증
    resp = client.put(
        API + "/schedules/" + S["schedule_id"],
        headers=staff_headers,
        json={"start_at": "2026-07-20T12:00:00", "end_at": "2026-07-20T11:30:00"},
    )
    assert resp.status_code == 422

    # 부분 수정(start_at만 저장된 end_at 뒤로) — 라우터 최종 검증
    resp = client.put(
        API + "/schedules/" + S["schedule_id"],
        headers=staff_headers,
        json={"start_at": "2026-07-20T12:00:00"},
    )
    assert resp.status_code == 422
    assert "종료 시각이 시작 시각보다 빠릅니다" in resp.text

    # 정상 이동은 통과
    resp = client.put(
        API + "/schedules/" + S["schedule_id"],
        headers=staff_headers,
        json={"start_at": "2026-07-21T10:00:00", "end_at": "2026-07-21T11:00:00"},
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 5. soft 삭제 세그먼트 PUT 차단 — 404 (발송과 동일 톤)
# ---------------------------------------------------------------------------
def test_deleted_segment_put_404(client, admin_headers):
    resp = client.post(
        API + "/segments",
        headers=admin_headers,
        json={"name": "P2G 삭제 대상", "criteria": {}},
    )
    assert resp.status_code == 201, resp.text
    segment_id = resp.json()["segment_id"]

    assert (
        client.delete(API + "/segments/" + segment_id, headers=admin_headers).status_code == 204
    )

    resp = client.put(
        API + "/segments/" + segment_id,
        headers=admin_headers,
        json={"name": "부활 시도"},
    )
    assert resp.status_code == 404
    assert "삭제됨" in resp.json()["detail"]

    # active=Y 부활 시도도 동일하게 404
    resp = client.put(
        API + "/segments/" + segment_id,
        headers=admin_headers,
        json={"active": "Y"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. 시간대 접미사 거부 — 벽시계 datetime 입력에 Z/+09:00 → 422
# ---------------------------------------------------------------------------
def test_history_tz_aware_activity_date_422(client, staff_headers):
    for bad in ("2026-07-01T10:00:00Z", "2026-07-01T10:00:00+09:00"):
        resp = client.post(
            API + "/histories",
            headers=staff_headers,
            json={
                "client_id": S["c_plain"],
                "activity_date": bad,
                "activity_type": "CALL",
                "title": "tz 접미사 거부",
            },
        )
        assert resp.status_code == 422, resp.text
        assert "시간대 없는 KST 시각으로 입력하세요" in resp.text


def test_schedule_tz_aware_422(client, staff_headers):
    resp = client.post(
        API + "/schedules",
        headers=staff_headers,
        json={
            "schedule_type": "MEETING",
            "title": "tz 일정",
            "start_at": "2026-07-20T10:00:00Z",
        },
    )
    assert resp.status_code == 422
    assert "시간대 없는 KST 시각으로 입력하세요" in resp.text

    resp = client.put(
        API + "/schedules/" + S["schedule_id"],
        headers=staff_headers,
        json={"end_at": "2026-07-21T12:00:00+09:00"},
    )
    assert resp.status_code == 422


def test_client_tz_aware_contract_date_422(client, staff_headers):
    resp = client.post(
        API + "/clients",
        headers=staff_headers,
        json={
            "client_type": "TRANSPORT",
            "company_name": "tz계약운수",
            "contract_date": "2026-07-01T00:00:00Z",
        },
    )
    assert resp.status_code == 422
    assert "시간대 없는 KST 시각으로 입력하세요" in resp.text


# ---------------------------------------------------------------------------
# 1. 스키마 길이 정합 — String(N) 초과 입력 422 (DB 오류 500 예방)
# ---------------------------------------------------------------------------
def test_client_field_over_length_422(client, staff_headers):
    # phone String(20)·biz_reg_no String(20)·region String(20)·company_name String(100)
    over_cases = [
        {"main_contact_phone": "0" * 21},
        {"biz_reg_no": "1" * 21},
        {"region": "가" * 21},
        {"company_name": "회" * 101},
        {"address": "주" * 201},
        {"keyman": "키" * 51},
    ]
    for extra in over_cases:
        payload = {"client_type": "TRANSPORT", "company_name": "길이검증운수"}
        payload.update(extra)
        resp = client.post(API + "/clients", headers=staff_headers, json=payload)
        assert resp.status_code == 422, (extra, resp.text)

    # 경계값(딱 맞는 길이)은 통과
    S["c_len"] = _create_client(
        client, staff_headers, "길이검증운수", main_contact_phone="0" * 20, region="가" * 20
    )

    # 수정 스키마도 동일 규칙
    resp = client.put(
        API + "/clients/" + S["c_len"],
        headers=staff_headers,
        json={"main_contact_phone": "0" * 21},
    )
    assert resp.status_code == 422


def test_asset_field_over_length_422(client, staff_headers):
    base = {"client_id": S["c_len"], "asset_group": "MOBILITY"}
    for extra in [
        {"location_info": "위" * 201},
        {"main_spec": "제" * 101},
        {"agency_name": "기" * 101},
        {"site_url": "u" * 256},
    ]:
        payload = dict(base)
        payload.update(extra)
        resp = client.post(API + "/assets", headers=staff_headers, json=payload)
        assert resp.status_code == 422, (extra, resp.text)


# ---------------------------------------------------------------------------
# 2. 정산 산식 상한 — 입력 상한 + expected_amount Numeric(15,2) 초과 422
# ---------------------------------------------------------------------------
def test_project_input_caps_422(client, admin_headers):
    # 단가 상한(1e12) 초과
    resp = client.post(
        API + "/projects",
        headers=admin_headers,
        json={"project_name": "P2G 상한사업", "unit_price": 2e12},
    )
    assert resp.status_code == 422

    # 발행량 상한(Numeric(10,2) 정수부 8자리) 초과
    resp = client.post(
        API + "/projects",
        headers=admin_headers,
        json={"project_name": "P2G 상한사업", "expected_credits": 1e8},
    )
    assert resp.status_code == 422


def test_expected_amount_overflow_422(client, admin_headers, staff_headers):
    # 최대 허용 입력 조합은 산식 결과가 Numeric(15,2)를 넘는다 → 저장 전 422
    resp = client.post(
        API + "/projects",
        headers=admin_headers,
        json={
            "project_name": "P2G 산식상한 사업",
            "expected_credits": 99_999_999,
            "unit_price": 1e12,
        },
    )
    assert resp.status_code == 201, resp.text
    project_id = resp.json()["project_id"]
    S["overflow_project"] = project_id

    resp = client.post(
        API + "/projects/{0}/clients".format(project_id),
        headers=admin_headers,
        json={"client_id": S["c_len"], "allocation_ratio": 100, "success_fee_rate": 100},
    )
    assert resp.status_code == 422
    assert "예상 정산액이 허용 범위를 초과합니다" in resp.json()["detail"]

    # 정상 단가로 매핑 성립 후, 단가 인상으로 상한 초과 재계산 시도 → 422 (재계산 경로)
    resp = client.put(
        API + "/projects/{0}/unit-price".format(project_id),
        headers=admin_headers,
        json={"unit_price": 10000},
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        API + "/projects/{0}/clients".format(project_id),
        headers=admin_headers,
        json={"client_id": S["c_len"], "allocation_ratio": 100, "success_fee_rate": 100},
    )
    assert resp.status_code == 201, resp.text

    resp = client.put(
        API + "/projects/{0}/unit-price".format(project_id),
        headers=admin_headers,
        json={"unit_price": 1e12},
    )
    assert resp.status_code == 422
    assert "예상 정산액이 허용 범위를 초과합니다" in resp.json()["detail"]

    # 차단 후에도 기존 단가·금액은 유지(트랜잭션 롤백)
    resp = client.get(API + "/projects/" + project_id, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["unit_price"] == 10000
