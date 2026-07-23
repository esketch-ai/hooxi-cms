"""세그먼트 보고서 발송 B1~B5 — 모델·쿼리 빌더·preview·facets·CRUD·발송·이력.

검증 포인트:
- 축별 단독 필터 6종 (region/client_type/contract_status/project_id/asset_group/settlement_status)
- 축 간 AND 결합
- 사업×정산 same-row 회귀: 사업 A 참여 + 사업 B에서만 BILLED인 회사는
  (project_id=[A] AND settlement_status=[BILLED])에 잡히면 안 된다
- preview can_receive: 공통 수신자(sub_id IS NULL, TO 후보) 존재 or main_contact_email
  보유 — CC 전용 수신자만 있으면 False(실제 발송 TO 0건 판정과 일치)
- facets: region distinct(빈 값 제외·정렬)
- CRUD: 생성/목록/수정/soft 삭제(active=N) + criteria 검증 422 + 감사 로그
- 발송(B5): 전건 성공(로그·활동이력·카운트)·건별 실패 격리·수신자 없음 FAIL 후 계속·
  Gmail 미설정 503(SegmentSend 미생성)·없는 doc_id 404·감사 로그 이메일 미포함·이력 조회·
  기본 템플릿 미치환 {변수} 없음({보고서유형} 리터럴 회귀)·첨부 총량 20MB 초과 422·
  soft 삭제 세그먼트 발송 404
"""

import io

import pytest

import models
from services import email_service, storage

API = "/api/v1"
SEG = API + "/segments"
REGION_A = "SEG-서울"   # 본 모듈 전용 region — 타 테스트 모듈과 비충돌
REGION_B = "SEG-부산"
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


def _create_client(client, headers, name, client_type, contract_status, region, email=None):
    resp = client.post(
        API + "/clients",
        headers=headers,
        json={
            "client_type": client_type,
            "company_name": name,
            "contract_status": contract_status,
            "region": region,
            "main_contact_email": email,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["client_id"]


def _create_project(client, headers, name):
    resp = client.post(
        API + "/projects", headers=headers, json={"project_name": name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["project_id"]


def _map_client(client, headers, project_id, client_id, ratio):
    resp = client.post(
        API + "/projects/{0}/clients".format(project_id),
        headers=headers,
        json={"client_id": client_id, "allocation_ratio": ratio, "success_fee_rate": 10},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["map_id"]


def _create_asset(client, headers, client_id, asset_group):
    resp = client.post(
        API + "/assets",
        headers=headers,
        json={"client_id": client_id, "asset_group": asset_group},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["asset_id"]


def _preview(client, headers, criteria):
    resp = client.post(SEG + "/preview", headers=headers, json={"criteria": criteria})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _preview_ids(client, headers, criteria):
    return {item["client_id"] for item in _preview(client, headers, criteria)["items"]}


def _audit_logs(db, action, target_id):
    return (
        db.query(models.AuditLog)
        .filter(models.AuditLog.action == action, models.AuditLog.target_id == target_id)
        .all()
    )


@pytest.fixture(scope="module")
def seg_data(client, staff_headers):
    """모듈 전용 시드 — 고객사 3·사업 2·매핑 3·자산 2·공통 수신자 1.

    - c1: TRANSPORT/ACTIVE/서울, 이메일 O, MOBILITY 자산, 사업A(STANDBY)
    - c2: BUILDING/HOLD/부산, 이메일 X, FACILITY 자산, 사업A(STANDBY)+사업B(BILLED)
    - c3: TRANSPORT/END/서울, 이메일 X(공통 수신자 O), 사업A(BILLED)
    """
    c1 = _create_client(client, staff_headers, "세그운수A", "TRANSPORT", "ACTIVE",
                        REGION_A, "seg-c1@segments.example.com")
    c2 = _create_client(client, staff_headers, "세그건물B", "BUILDING", "HOLD", REGION_B)
    c3 = _create_client(client, staff_headers, "세그운수C", "TRANSPORT", "END", REGION_A)

    project_a = _create_project(client, staff_headers, "세그사업A")
    project_b = _create_project(client, staff_headers, "세그사업B")
    map_a1 = _map_client(client, staff_headers, project_a, c1, 30)
    map_a2 = _map_client(client, staff_headers, project_a, c2, 30)
    map_a3 = _map_client(client, staff_headers, project_a, c3, 30)
    map_b2 = _map_client(client, staff_headers, project_b, c2, 50)

    _create_asset(client, staff_headers, c1, "MOBILITY")
    _create_asset(client, staff_headers, c2, "FACILITY")

    # 정산 상태·공통 수신자는 DB 직접 세팅 (상태전이 게이트 우회 — 데이터 형상만 필요)
    db = models.SessionLocal()
    try:
        db.get(models.ProjectClientMap, map_a3).settlement_status = "BILLED"  # c3: 사업A에서 청구
        db.get(models.ProjectClientMap, map_b2).settlement_status = "BILLED"  # c2: 사업B에서만 청구
        db.add(models.ReportRecipient(
            client_id=c3, name="세그담당", email="seg-c3@segments.example.com",
            cc_yn="N", sub_id=None,
        ))
        db.commit()
    finally:
        db.close()

    return {
        "c1": c1, "c2": c2, "c3": c3,
        "project_a": project_a, "project_b": project_b,
        "maps": {"a1": map_a1, "a2": map_a2, "a3": map_a3, "b2": map_b2},
    }


# ---------------------------------------------------------------------------
# 축별 단독 필터 6종
# ---------------------------------------------------------------------------
def test_axis_region(client, staff_headers, seg_data):
    ids = _preview_ids(client, staff_headers, {"region": [REGION_A]})
    assert seg_data["c1"] in ids and seg_data["c3"] in ids
    assert seg_data["c2"] not in ids


def test_axis_client_type(client, staff_headers, seg_data):
    ids = _preview_ids(client, staff_headers, {"client_type": ["BUILDING"]})
    assert seg_data["c2"] in ids
    assert seg_data["c1"] not in ids and seg_data["c3"] not in ids


def test_axis_contract_status(client, staff_headers, seg_data):
    ids = _preview_ids(client, staff_headers, {"contract_status": ["END"]})
    assert seg_data["c3"] in ids
    assert seg_data["c1"] not in ids and seg_data["c2"] not in ids


def test_axis_project_id(client, staff_headers, seg_data):
    ids = _preview_ids(client, staff_headers, {"project_id": [seg_data["project_a"]]})
    assert {seg_data["c1"], seg_data["c2"], seg_data["c3"]} <= ids
    ids_b = _preview_ids(client, staff_headers, {"project_id": [seg_data["project_b"]]})
    assert seg_data["c2"] in ids_b
    assert seg_data["c1"] not in ids_b and seg_data["c3"] not in ids_b


def test_axis_asset_group(client, staff_headers, seg_data):
    ids = _preview_ids(client, staff_headers, {"asset_group": ["MOBILITY"]})
    assert seg_data["c1"] in ids
    assert seg_data["c2"] not in ids and seg_data["c3"] not in ids


def test_axis_settlement_status(client, staff_headers, seg_data):
    ids = _preview_ids(client, staff_headers, {"settlement_status": ["BILLED"]})
    assert seg_data["c2"] in ids and seg_data["c3"] in ids
    assert seg_data["c1"] not in ids


# ---------------------------------------------------------------------------
# 축 간 AND + 사업×정산 same-row 회귀
# ---------------------------------------------------------------------------
def test_composite_and(client, staff_headers, seg_data):
    """축 간 AND — region 축이 모듈 전용 값이라 정확 일치 검증 가능."""
    ids = _preview_ids(
        client, staff_headers,
        {"region": [REGION_A], "client_type": ["TRANSPORT"], "contract_status": ["ACTIVE"]},
    )
    assert ids == {seg_data["c1"]}


def test_project_settlement_same_row(client, staff_headers, seg_data):
    """핵심 회귀 — 사업A 참여 + 사업B에서만 BILLED인 c2는 (A AND BILLED)에 제외.

    EXISTS를 축별로 분리하면 c2가 잘못 포함된다(같은 map 행 평가 보장 검증).
    """
    ids = _preview_ids(
        client, staff_headers,
        {"project_id": [seg_data["project_a"]], "settlement_status": ["BILLED"]},
    )
    assert seg_data["c3"] in ids           # 사업A에서 BILLED — 포함
    assert seg_data["c2"] not in ids       # 사업B에서만 BILLED — 제외 (same-row)
    assert seg_data["c1"] not in ids       # 사업A STANDBY — 제외

    ids_b = _preview_ids(
        client, staff_headers,
        {"project_id": [seg_data["project_b"]], "settlement_status": ["BILLED"]},
    )
    assert seg_data["c2"] in ids_b and seg_data["c3"] not in ids_b


# ---------------------------------------------------------------------------
# preview can_receive + facets + 인증
# ---------------------------------------------------------------------------
def test_preview_can_receive(client, staff_headers, seg_data):
    body = _preview(client, staff_headers, {"region": [REGION_A, REGION_B]})
    assert body["total"] == len(body["items"]) == 3
    receivable = {i["client_id"]: i["can_receive"] for i in body["items"]}
    assert receivable[seg_data["c1"]] is True    # main_contact_email 보유
    assert receivable[seg_data["c2"]] is False   # 이메일·수신자 모두 없음
    assert receivable[seg_data["c3"]] is True    # 공통 수신자(sub_id IS NULL) 존재
    # 계약 상태 노출 — 종료(END) 고객사 오발송 예방 배지용
    contract = {i["client_id"]: i["contract_status"] for i in body["items"]}
    assert contract[seg_data["c1"]] == "ACTIVE"
    assert contract[seg_data["c2"]] == "HOLD"
    assert contract[seg_data["c3"]] == "END"


def test_preview_can_receive_cc_only_false(client, staff_headers, seg_data):
    """CC 전용 수신자만 + main_contact_email 없음 — TO 0건이라 can_receive False.

    실제 발송(resolve_recipients)이 TO 0건 FAIL이 되는 형상을 미리보기도 동일 판정.
    """
    c4 = _create_client(client, staff_headers, "세그참조전용D", "TRANSPORT", "ACTIVE", "SEG-대전")
    db = models.SessionLocal()
    try:
        db.add(models.ReportRecipient(
            client_id=c4, name="참조만", email="seg-c4-cc@segments.example.com",
            cc_yn="Y", sub_id=None,
        ))
        db.commit()
    finally:
        db.close()

    body = _preview(client, staff_headers, {"region": ["SEG-대전"]})
    receivable = {i["client_id"]: i["can_receive"] for i in body["items"]}
    assert receivable[c4] is False


def test_facets_regions(client, staff_headers, seg_data):
    resp = client.get(SEG + "/facets", headers=staff_headers)
    assert resp.status_code == 200, resp.text
    regions = resp.json()["regions"]
    assert REGION_A in regions and REGION_B in regions
    assert all(r for r in regions)               # 빈 값 제외
    assert regions == sorted(regions)            # 정렬


def test_requires_auth(client, seg_data):
    assert client.post(SEG + "/preview", json={"criteria": {}}).status_code == 401
    assert client.get(SEG).status_code == 401


# ---------------------------------------------------------------------------
# CRUD + criteria 검증 422 + 감사 로그
# ---------------------------------------------------------------------------
def test_create_segment_and_audit(client, staff_headers, seg_data):
    resp = client.post(
        SEG,
        headers=staff_headers,
        json={
            "name": "서울 청구 세그먼트",
            "description": "서울 지역 청구 고객",
            "criteria": {"region": [REGION_A], "settlement_status": ["BILLED"]},
            "mail_subject": "[Hooxi] {고객사명} 안내",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    S["segment_id"] = body["segment_id"]
    assert body["name"] == "서울 청구 세그먼트"
    assert body["active"] == "Y"
    # criteria가 JSON 문자열이 아닌 객체로 왕복되는지
    assert body["criteria"]["region"] == [REGION_A]
    assert body["criteria"]["settlement_status"] == ["BILLED"]

    db = models.SessionLocal()
    try:
        logs = _audit_logs(db, "SEGMENT_CREATE", S["segment_id"])
        assert len(logs) == 1
        assert "settlement_status=BILLED" in logs[0].new_value
    finally:
        db.close()


def test_list_segments(client, staff_headers):
    resp = client.get(SEG, headers=staff_headers)
    assert resp.status_code == 200, resp.text
    assert S["segment_id"] in {s["segment_id"] for s in resp.json()}


def test_update_segment_and_audit(client, staff_headers):
    resp = client.put(
        SEG + "/" + S["segment_id"],
        headers=staff_headers,
        json={"name": "서울 운수 세그먼트", "criteria": {"region": [REGION_A], "client_type": ["TRANSPORT"]}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "서울 운수 세그먼트"
    assert body["criteria"] == {
        "region": [REGION_A], "client_type": ["TRANSPORT"],
        "contract_status": None, "project_id": None,
        "asset_group": None, "settlement_status": None,
    }

    db = models.SessionLocal()
    try:
        logs = _audit_logs(db, "SEGMENT_UPDATE", S["segment_id"])
        assert len(logs) == 1
        assert "settlement_status=BILLED" in logs[0].old_value
        assert "client_type=TRANSPORT" in logs[0].new_value
    finally:
        db.close()


def test_criteria_validation_422(client, staff_headers, seg_data):
    # 비활성/미등록 코드값 — validate_active_code 재사용
    resp = client.post(SEG, headers=staff_headers,
                       json={"name": "잘못된 코드", "criteria": {"client_type": ["NOPE"]}})
    assert resp.status_code == 422, resp.text
    # 미지원 criteria 키 — 스키마 extra=forbid
    resp = client.post(SEG, headers=staff_headers,
                       json={"name": "잘못된 키", "criteria": {"foo": ["x"]}})
    assert resp.status_code == 422, resp.text
    # 존재하지 않는 사업
    resp = client.post(SEG, headers=staff_headers,
                       json={"name": "없는 사업", "criteria": {"project_id": ["no-such-project"]}})
    assert resp.status_code == 422, resp.text
    # preview도 미지원 키 422 (같은 스키마)
    resp = client.post(SEG + "/preview", headers=staff_headers,
                       json={"criteria": {"bar": ["y"]}})
    assert resp.status_code == 422, resp.text


def test_soft_delete_and_audit(client, staff_headers):
    resp = client.delete(SEG + "/" + S["segment_id"], headers=staff_headers)
    assert resp.status_code == 204, resp.text

    # 기본 목록에서 제외, include_inactive=true면 active=N으로 노출
    resp = client.get(SEG, headers=staff_headers)
    assert S["segment_id"] not in {s["segment_id"] for s in resp.json()}
    resp = client.get(SEG, params={"include_inactive": True}, headers=staff_headers)
    rows = {s["segment_id"]: s for s in resp.json()}
    assert rows[S["segment_id"]]["active"] == "N"

    db = models.SessionLocal()
    try:
        assert db.get(models.Segment, S["segment_id"]) is not None  # 행 보존 (soft)
        assert len(_audit_logs(db, "SEGMENT_DELETE", S["segment_id"])) == 1
    finally:
        db.close()


def test_delete_missing_404(client, staff_headers):
    assert client.delete(SEG + "/no-such-segment", headers=staff_headers).status_code == 404


# ---------------------------------------------------------------------------
# 발송 실행 (B5) — tb_segment_send/log + 활동 이력 + 감사 로그
# ---------------------------------------------------------------------------
def _enable_mail(monkeypatch, fail_marker=None):
    """Gmail 환경변수 + send_mail 모킹 — fail_marker 포함 수신자는 발송 예외 유발
    (test_batch_report_send 관용구 — 첨부도 기록)."""
    monkeypatch.setenv("GMAIL_SENDER", "hooxi12345@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    calls = []

    def fake_send_mail(to, subject, body, cc=None, attachments=None, reply_to=None, html=False):
        if fail_marker and any(fail_marker in addr for addr in to):
            raise RuntimeError("SMTP down (테스트 유발)")
        calls.append({"to": to, "subject": subject, "body": body, "attachments": attachments})
        return {"sender": "hooxi12345@gmail.com", "recipients": list(to) + list(cc or [])}

    monkeypatch.setattr(email_service, "send_mail", fake_send_mail)
    return calls


def _upload_doc(client, headers, name):
    resp = client.post(
        API + "/documents",
        headers=headers,
        files={"file": (name, io.BytesIO(b"PDF-SEG"), "application/pdf")},
        data={"doc_type": "FORM", "title": name},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["doc_id"]


def _send_count(db):
    return db.query(models.SegmentSend).count()


def _send_logs(db, send_id):
    return (
        db.query(models.SegmentSendLog)
        .filter(models.SegmentSendLog.send_id == send_id)
        .all()
    )


def test_send_missing_doc_404(client, staff_headers, seg_data, monkeypatch):
    """없는 doc_id — 발송 전 사전 차단(404) + SegmentSend 미생성."""
    _enable_mail(monkeypatch)
    db = models.SessionLocal()
    before = _send_count(db)
    db.close()

    resp = client.post(
        SEG + "/send",
        headers=staff_headers,
        json={"doc_ids": ["no-such-doc"], "criteria": {"region": [REGION_A]}},
    )
    assert resp.status_code == 404, resp.text

    db = models.SessionLocal()
    assert _send_count(db) == before
    db.close()


def test_send_requires_criteria_and_docs_422(client, staff_headers, seg_data, monkeypatch):
    _enable_mail(monkeypatch)
    # 즉석 발송 criteria 누락 → 422
    doc = _upload_doc(client, staff_headers, "세그양식-검증.pdf")
    resp = client.post(SEG + "/send", headers=staff_headers, json={"doc_ids": [doc]})
    assert resp.status_code == 422, resp.text
    # doc_ids 빈 배열 → 422 (스키마 min_length=1)
    resp = client.post(
        SEG + "/send", headers=staff_headers,
        json={"doc_ids": [], "criteria": {"region": [REGION_A]}},
    )
    assert resp.status_code == 422, resp.text


def test_send_attachment_total_cap_422(client, staff_headers, seg_data, monkeypatch):
    """첨부 총량 20MB 초과 — 발송 전 422 사전 차단 + SegmentSend 미생성."""
    _enable_mail(monkeypatch)
    doc = _upload_doc(client, staff_headers, "세그대용량.pdf")
    # 저장소 읽기만 대용량으로 대체 — 실제 21MB 업로드 없이 총량 판정 검증
    monkeypatch.setattr(storage, "read_file", lambda url: b"x" * (21 * 1024 * 1024))

    db = models.SessionLocal()
    before = _send_count(db)
    db.close()

    resp = client.post(
        SEG + "/send",
        headers=staff_headers,
        json={"doc_ids": [doc], "criteria": {"region": [REGION_A]}},
    )
    assert resp.status_code == 422, resp.text
    assert "20MB" in resp.json()["detail"]

    db = models.SessionLocal()
    assert _send_count(db) == before
    db.close()


def test_send_soft_deleted_segment_404(client, staff_headers, seg_data, monkeypatch):
    """soft 삭제(active=N) 세그먼트 발송 — 404 차단 + SegmentSend 미생성."""
    _enable_mail(monkeypatch)
    doc = _upload_doc(client, staff_headers, "세그삭제검증.pdf")
    resp = client.post(
        SEG, headers=staff_headers,
        json={"name": "삭제 후 발송 차단", "criteria": {"region": [REGION_A]}},
    )
    assert resp.status_code == 201, resp.text
    segment_id = resp.json()["segment_id"]
    assert client.delete(SEG + "/" + segment_id, headers=staff_headers).status_code == 204

    db = models.SessionLocal()
    before = _send_count(db)
    db.close()

    resp = client.post(
        SEG + "/{0}/send".format(segment_id),
        headers=staff_headers,
        json={"doc_ids": [doc]},
    )
    assert resp.status_code == 404, resp.text

    db = models.SessionLocal()
    assert _send_count(db) == before
    db.close()


def test_send_gmail_unconfigured_503(client, staff_headers, seg_data):
    """Gmail 미설정 — 503 즉중단 + SegmentSend 미생성(상태 무변경)."""
    db = models.SessionLocal()
    before = _send_count(db)
    db.close()

    # conftest가 GMAIL_* 를 제거한 상태 그대로 실행 → 503 (문서 검증 이전에 즉중단)
    resp = client.post(
        SEG + "/send",
        headers=staff_headers,
        json={"doc_ids": ["any-doc"], "criteria": {"region": [REGION_A]}},
    )
    assert resp.status_code == 503, resp.text

    db = models.SessionLocal()
    assert _send_count(db) == before
    db.close()


def test_send_all_success(client, staff_headers, seg_data, monkeypatch):
    """전건 성공 — 대상별 SUCCESS 로그 + 활동 이력 [자동] + 카운트 + 첨부 N부."""
    S["doc1"] = S.get("doc1") or _upload_doc(client, staff_headers, "세그양식1.pdf")
    S["doc2"] = _upload_doc(client, staff_headers, "세그양식2.pdf")
    calls = _enable_mail(monkeypatch)

    resp = client.post(
        SEG + "/send",
        headers=staff_headers,
        json={"doc_ids": [S["doc1"], S["doc2"]], "criteria": {"region": [REGION_A]}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    S["send_ok"] = body["send_id"]
    # REGION_A = c1(main_contact_email) + c3(공통 수신자) — 둘 다 수신 가능
    assert body["target_count"] == 2 and body["sent_count"] == 2 and body["failed_count"] == 0
    results = {d["client_id"]: d for d in body["details"]}
    assert results[seg_data["c1"]]["result"] == "SUCCESS"
    assert results[seg_data["c3"]]["result"] == "SUCCESS"

    # 메일 2통 + 첨부 2부 + 기본 제목 템플릿의 {고객사명} 치환
    assert len(calls) == 2
    assert all(len(c["attachments"]) == 2 for c in calls)
    subjects = " / ".join(c["subject"] for c in calls)
    assert "세그운수A" in subjects and "세그운수C" in subjects
    # 제목·본문 미지정 → 세그먼트 전용 기본 템플릿 — 월간 보고서 폴백의
    # {보고서유형} 리터럴 발송 회귀 방지: 렌더 결과에 미치환 {변수}가 없어야 함
    assert "{" not in subjects
    assert all("{" not in c["body"] for c in calls)
    assert "보고서유형" not in subjects

    db = models.SessionLocal()
    try:
        send = db.get(models.SegmentSend, S["send_ok"])
        assert send.target_count == 2 and send.sent_count == 2 and send.failed_count == 0
        assert send.segment_id is None  # 즉석 발송
        logs = _send_logs(db, S["send_ok"])
        assert len(logs) == 2 and all(l.result == "SUCCESS" for l in logs)
        assert all(l.recipients for l in logs)  # 수신자 스냅샷 보존
        # 활동 이력 EMAIL "[자동]" — c1·c3 각 1건
        for cid in (seg_data["c1"], seg_data["c3"]):
            history = (
                db.query(models.ActivityHistory)
                .filter(
                    models.ActivityHistory.client_id == cid,
                    models.ActivityHistory.activity_type == "EMAIL",
                )
                .all()
            )
            assert len(history) == 1 and history[0].title.startswith("[자동]")
    finally:
        db.close()


def test_send_failure_isolation(client, staff_headers, seg_data, monkeypatch):
    """1건 send_mail 예외 — 격리(나머지 계속) + FAIL 로그 사유."""
    _enable_mail(monkeypatch, fail_marker="seg-c1")

    resp = client.post(
        SEG + "/send",
        headers=staff_headers,
        json={"doc_ids": [S["doc1"]], "criteria": {"region": [REGION_A]}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target_count"] == 2 and body["sent_count"] == 1 and body["failed_count"] == 1
    results = {d["client_id"]: d for d in body["details"]}
    assert results[seg_data["c1"]]["result"] == "FAIL"
    assert "SMTP down" in results[seg_data["c1"]]["reason"]
    assert results[seg_data["c3"]]["result"] == "SUCCESS"

    db = models.SessionLocal()
    logs = {l.client_id: l for l in _send_logs(db, body["send_id"])}
    assert logs[seg_data["c1"]].result == "FAIL" and "SMTP down" in logs[seg_data["c1"]].reason
    assert logs[seg_data["c3"]].result == "SUCCESS"
    db.close()


def test_send_no_recipient_fail_and_continue(client, staff_headers, seg_data, monkeypatch):
    """수신자 없는 고객사(c2) — FAIL(수신자 없음) 기록 후 나머지 계속."""
    _enable_mail(monkeypatch)

    resp = client.post(
        SEG + "/send",
        headers=staff_headers,
        json={"doc_ids": [S["doc1"]], "criteria": {"region": [REGION_A, REGION_B]}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target_count"] == 3 and body["sent_count"] == 2 and body["failed_count"] == 1
    results = {d["client_id"]: d for d in body["details"]}
    assert results[seg_data["c2"]]["result"] == "FAIL"
    assert "수신자 없음" in results[seg_data["c2"]]["reason"]
    assert results[seg_data["c1"]]["result"] == "SUCCESS"
    assert results[seg_data["c3"]]["result"] == "SUCCESS"


def test_send_saved_segment_with_override(client, staff_headers, seg_data, monkeypatch):
    """저장 세그먼트 발송 — 저장 criteria 사용 + mail_subject 오버라이드 치환."""
    resp = client.post(
        SEG,
        headers=staff_headers,
        json={
            "name": "발송용 세그먼트",
            "criteria": {"region": [REGION_A], "client_type": ["TRANSPORT"],
                         "contract_status": ["ACTIVE"]},
            "mail_subject": "[Hooxi] {고객사명} 안내",
        },
    )
    assert resp.status_code == 201, resp.text
    segment_id = resp.json()["segment_id"]

    calls = _enable_mail(monkeypatch)
    resp = client.post(
        SEG + "/{0}/send".format(segment_id),
        headers=staff_headers,
        json={"doc_ids": [S["doc1"]]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target_count"] == 1 and body["sent_count"] == 1  # 저장 criteria → c1만
    assert len(calls) == 1 and calls[0]["subject"] == "[Hooxi] 세그운수A 안내"

    db = models.SessionLocal()
    send = db.get(models.SegmentSend, body["send_id"])
    assert send.segment_id == segment_id  # 저장 세그먼트 참조 기록
    db.close()

    # 없는 세그먼트 → 404
    resp = client.post(SEG + "/no-such-segment/send", headers=staff_headers,
                       json={"doc_ids": [S["doc1"]]})
    assert resp.status_code == 404


def test_send_audit_summary_only(client, staff_headers):
    """감사 로그 SEGMENT_SEND — 카운트 요약만, 수신자 이메일 미포함 (R2-E6)."""
    db = models.SessionLocal()
    try:
        logs = (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == "SEGMENT_SEND")
            .all()
        )
        assert len(logs) >= 4  # 본 모듈 발송 실행 건수만큼 적재
        for log in logs:
            assert "sent=" in log.new_value and "failed=" in log.new_value
            assert "@" not in (log.new_value or "")  # 이메일 주소 금지
            assert "@" not in (log.old_value or "")
    finally:
        db.close()


def test_send_history(client, staff_headers):
    """이력 목록(최신순)·상세(로그 포함) 조회 + 인증 게이트."""
    resp = client.get(SEG + "/sends", headers=staff_headers)
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert S["send_ok"] in {r["send_id"] for r in rows}
    created = [r["created_at"] for r in rows]
    assert created == sorted(created, reverse=True)  # 최신순

    resp = client.get(SEG + "/sends/" + S["send_ok"], headers=staff_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target_count"] == 2 and body["sent_count"] == 2
    assert body["doc_ids"] and S["doc1"] in body["doc_ids"]  # doc_ids JSON 스냅샷
    assert len(body["logs"]) == 2
    assert all(l["result"] == "SUCCESS" and l["client_name"] for l in body["logs"])

    assert client.get(SEG + "/sends").status_code == 401
    assert client.get(SEG + "/sends/no-such-send", headers=staff_headers).status_code == 404


def test_send_history_missing_404(client, staff_headers):
    assert client.get(SEG + "/sends/no-such-send", headers=staff_headers).status_code == 404
