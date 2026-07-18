"""P1-C 고객사 온보딩 정합 + 보고서 수신자 관리 (시나리오 #1 반려 보강).

- 사업자번호 중복 409 (숫자만 정규화 비교 — 하이픈 표기 차이 무시)
- 담당자 이메일 형식 422
- 문서 업로드 자산-고객사 소유 검증 422
- 수신자 CRUD + 중복 409 + resolve_recipients(R2-B5) 발송 해석 연계
"""

import io

import models
from services.report_sender import resolve_recipients

API = "/api/v1"


def _create_client(client, headers, **overrides):
    payload = {"client_type": "TRANSPORT", "company_name": "P1C-운수"}
    payload.update(overrides)
    return client.post(API + "/clients", json=payload, headers=headers)


# ---------------------------------------------------------------------------
# 1. 사업자번호 중복 차단 (409)
# ---------------------------------------------------------------------------
def test_biz_reg_no_duplicate_rejected_with_hyphen_variants(client, admin_headers):
    """같은 번호는 하이픈 표기가 달라도 409 — 기존 회사명이 메시지에 노출."""
    resp = _create_client(
        client, admin_headers, company_name="P1C-원본운수", biz_reg_no="777-88-99900"
    )
    assert resp.status_code == 201, resp.text

    # 동일 표기
    resp = _create_client(
        client, admin_headers, company_name="P1C-복제운수", biz_reg_no="777-88-99900"
    )
    assert resp.status_code == 409
    assert "이미 등록된 사업자번호" in resp.json()["detail"]
    assert "P1C-원본운수" in resp.json()["detail"]

    # 하이픈 제거 변형도 동일 번호로 판정 (정규화 비교)
    resp = _create_client(
        client, admin_headers, company_name="P1C-변형운수", biz_reg_no="7778899900"
    )
    assert resp.status_code == 409


def test_biz_reg_no_update_self_allowed_but_other_conflict(client, admin_headers):
    """update 시 자기 자신은 허용, 타사 번호로 변경은 409. 빈 값은 검사 제외."""
    resp = _create_client(
        client, admin_headers, company_name="P1C-수정운수", biz_reg_no="555-66-77788"
    )
    assert resp.status_code == 201, resp.text
    cid = resp.json()["client_id"]

    # 자기 번호를 표기만 바꿔 재저장 — 허용 (자기 자신 제외)
    resp = client.put(
        API + "/clients/{0}".format(cid),
        json={"biz_reg_no": "5556677788"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["biz_reg_no"] == "5556677788"  # 원문 그대로 저장

    # 타사(원본운수) 번호로 변경 — 409
    resp = client.put(
        API + "/clients/{0}".format(cid),
        json={"biz_reg_no": "777-88-99900"},
        headers=admin_headers,
    )
    assert resp.status_code == 409

    # 빈 값/None은 검사 제외 — 여러 고객사가 미입력이어도 충돌 없음
    resp = client.put(
        API + "/clients/{0}".format(cid), json={"biz_reg_no": None}, headers=admin_headers
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 2. 이메일 형식 검증 (422)
# ---------------------------------------------------------------------------
def test_client_email_format_validated(client, admin_headers):
    """main/ceo 담당자 이메일 형식 오류는 422 (한국어 메시지)."""
    resp = _create_client(
        client, admin_headers, company_name="P1C-이메일운수", main_contact_email="not-an-email"
    )
    assert resp.status_code == 422
    assert "이메일 형식이 올바르지 않습니다" in resp.text

    resp = _create_client(
        client, admin_headers, company_name="P1C-이메일운수", ceo_contact_email="a@b"
    )
    assert resp.status_code == 422

    # 정상 형식 + 빈 문자열(미입력 간주)은 통과
    resp = _create_client(
        client,
        admin_headers,
        company_name="P1C-이메일운수",
        main_contact_email="ok@example.com",
        ceo_contact_email="",
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["main_contact_email"] == "ok@example.com"

    # update도 동일 검증
    cid = resp.json()["client_id"]
    resp = client.put(
        API + "/clients/{0}".format(cid),
        json={"main_contact_email": "broken@@example.com"},
        headers=admin_headers,
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 3. 문서 업로드 자산-고객사 소유 검증 (422)
# ---------------------------------------------------------------------------
def test_document_upload_asset_ownership(client, admin_headers):
    """asset_id와 client_id가 함께 오면 자산 소유 고객사 일치 검증."""
    resp = _create_client(client, admin_headers, company_name="P1C-자산주인운수")
    owner_id = resp.json()["client_id"]
    resp = _create_client(client, admin_headers, company_name="P1C-남의운수")
    other_id = resp.json()["client_id"]

    resp = client.post(
        API + "/assets",
        json={"client_id": owner_id, "asset_group": "MOBILITY", "asset_type": "EV"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    asset_id = resp.json()["asset_id"]

    # 다른 고객사의 문서에 남의 자산 연결 — 422
    resp = client.post(
        API + "/documents",
        data={"doc_type": "PHOTO", "client_id": other_id, "asset_id": asset_id},
        files={"file": ("현장.jpg", io.BytesIO(b"jpg"), "image/jpeg")},
        headers=admin_headers,
    )
    assert resp.status_code == 422
    assert "연결 자산이 해당 고객사의 자산이 아닙니다" in resp.json()["detail"]

    # 소유 고객사와 일치하면 정상 업로드
    resp = client.post(
        API + "/documents",
        data={"doc_type": "PHOTO", "client_id": owner_id, "asset_id": asset_id},
        files={"file": ("현장.jpg", io.BytesIO(b"jpg"), "image/jpeg")},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# 4. 수신자 관리 CRUD + resolve_recipients 연계
# ---------------------------------------------------------------------------
def test_recipient_crud_and_resolve(client, admin_headers):
    resp = _create_client(
        client,
        admin_headers,
        company_name="P1C-수신자운수",
        main_contact_email="fallback@example.com",
        subscription={"report_type": "월간 운행 보고서", "channel": "EMAIL", "due_day": 25},
    )
    assert resp.status_code == 201, resp.text
    cid = resp.json()["client_id"]
    sub_id = resp.json()["subscriptions"][0]["sub_id"]

    # 공통 TO
    resp = client.post(
        API + "/clients/{0}/recipients".format(cid),
        json={"email": "to@example.com", "name": "김수신"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    common_id = resp.json()["recipient_id"]
    assert resp.json()["cc_yn"] == "N"
    assert resp.json()["sub_id"] is None

    # 구독 지정 CC
    resp = client.post(
        API + "/clients/{0}/recipients".format(cid),
        json={"email": "cc@example.com", "cc_yn": "Y", "sub_id": sub_id},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text

    # 이메일 형식 오류 422
    resp = client.post(
        API + "/clients/{0}/recipients".format(cid),
        json={"email": "broken"},
        headers=admin_headers,
    )
    assert resp.status_code == 422

    # 같은 (고객사, 이메일, sub_id) 중복 409 — 대소문자 무시
    resp = client.post(
        API + "/clients/{0}/recipients".format(cid),
        json={"email": "TO@example.com"},
        headers=admin_headers,
    )
    assert resp.status_code == 409
    # 같은 이메일이라도 sub_id가 다르면 등록 가능
    resp = client.post(
        API + "/clients/{0}/recipients".format(cid),
        json={"email": "to@example.com", "sub_id": sub_id},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    sub_scoped_id = resp.json()["recipient_id"]

    # 존재하지 않는 구독 404
    resp = client.post(
        API + "/clients/{0}/recipients".format(cid),
        json={"email": "x@example.com", "sub_id": "no-such-sub"},
        headers=admin_headers,
    )
    assert resp.status_code == 404

    # 목록 — 공통분 + 구독 지정분 모두 포함 (sub_id·cc_yn 노출)
    resp = client.get(API + "/clients/{0}/recipients".format(cid), headers=admin_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 3
    assert {r["email"] for r in rows} == {"to@example.com", "cc@example.com"}

    # 발송 해석(R2-B5) 연계 — 공통 TO + 구독 지정분이 TO/CC로 분리
    db = models.SessionLocal()
    try:
        client_row = db.get(models.Client, cid)
        sub_row = db.get(models.ReportSubscription, sub_id)
        to, cc = resolve_recipients(db, client_row, sub_row)
        assert sorted(to) == ["to@example.com", "to@example.com"]
        assert cc == ["cc@example.com"]
        # 구독 미지정이면 공통분만
        to, cc = resolve_recipients(db, client_row, None)
        assert to == ["to@example.com"]
        assert cc == []
    finally:
        db.close()

    # 삭제 + 404 가드
    resp = client.delete(
        API + "/clients/{0}/recipients/{1}".format(cid, sub_scoped_id), headers=admin_headers
    )
    assert resp.status_code == 200
    resp = client.delete(
        API + "/clients/{0}/recipients/{1}".format(cid, sub_scoped_id), headers=admin_headers
    )
    assert resp.status_code == 404

    # 다른 고객사 경로로는 삭제 불가 (경로-소유 일치 가드)
    resp = _create_client(client, admin_headers, company_name="P1C-남의수신자운수")
    other_cid = resp.json()["client_id"]
    resp = client.delete(
        API + "/clients/{0}/recipients/{1}".format(other_cid, common_id), headers=admin_headers
    )
    assert resp.status_code == 404

    # 감사 로그 — RECIPIENT_ADD/REMOVE 기록 (이메일은 비밀값 아님, R2-E6 검토)
    db = models.SessionLocal()
    try:
        adds = (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == "RECIPIENT_ADD", models.AuditLog.target_id == cid)
            .all()
        )
        removes = (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == "RECIPIENT_REMOVE", models.AuditLog.target_id == cid)
            .all()
        )
        assert len(adds) == 3
        assert len(removes) == 1
    finally:
        db.close()
