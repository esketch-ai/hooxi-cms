"""일괄 발송 미리보기 (GET /batch/report-send/preview) — 발송 전 사전 점검(읽기 전용).

검증 포인트:
- APPROVED(발송승인)만 대상 — WRITING/SENT는 제외
- 항목: 실제 발송될 첨부파일명 + 수신자 수 + 발송가능(ready) 여부
- 차단 사유(issue): 파일 없음 → ready=False + filename None
- 무부작용: 미리보기 후에도 상태 불변(APPROVED) + 발송 로그 없음 + 당월 대상 미생성
- 인증: 토큰 없음 403 / STAFF 거부 403 / ADMIN 허용 (시크릿 경로 없음)
"""

import io

import models

API = "/api/v1"
PREVIEW = API + "/batch/report-send/preview"
PERIOD = "2029-03"  # 미리보기 전용 기간 (타 모듈과 비충돌)


def _create_client(client, headers, name, email):
    resp = client.post(
        API + "/clients",
        headers=headers,
        json={
            "client_type": "TRANSPORT",
            "company_name": name,
            "contract_status": "ACTIVE",
            "report_yn": "Y",
            "main_contact_email": email,
            "subscription": {"report_type": "월간 운행 보고서", "channel": "EMAIL", "due_day": 25},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["client_id"]


def _report_of(client, headers, client_id, period):
    resp = client.get(API + "/reports", params={"period": period}, headers=headers)
    assert resp.status_code == 200, resp.text
    mine = [i for i in resp.json()["items"] if i["client_id"] == client_id]
    assert len(mine) == 1
    return mine[0]


def _prepare(client, headers, client_id, period, to_status):
    """파일 업로드(STANDBY→WRITING) 후 목표 상태로 전이. report_id 반환."""
    report_id = _report_of(client, headers, client_id, period)["report_id"]
    resp = client.post(
        API + "/reports/{0}/file".format(report_id),
        headers=headers,
        files={"file": ("report.pdf", io.BytesIO(b"PDF-PREVIEW"), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    path = {"WRITING": [], "APPROVED": ["REVIEW", "APPROVED"]}[to_status]
    for status in path:
        resp = client.put(
            API + "/reports/{0}/status".format(report_id),
            headers=headers,
            json={"status": status},
        )
        assert resp.status_code == 200, resp.text
    return report_id


def test_auth_gate(client, staff_headers):
    # 토큰 없음 → 403 (미리보기는 시크릿 경로 없음)
    assert client.get(PREVIEW + "?period=" + PERIOD).status_code == 403
    # STAFF 토큰 거부
    assert client.get(PREVIEW + "?period=" + PERIOD, headers=staff_headers).status_code == 403


def test_preview_lists_ready_targets_only(client, staff_headers, admin_headers):
    approved = _create_client(client, staff_headers, "미리보기승인운수", "prev-a@preview.example.com")
    writing = _create_client(client, staff_headers, "미리보기작성운수", "prev-w@preview.example.com")
    resp = client.post(API + "/reports/generate", params={"period": PERIOD}, headers=staff_headers)
    assert resp.status_code == 200, resp.text
    approved_report = _prepare(client, staff_headers, approved, PERIOD, "APPROVED")
    _prepare(client, staff_headers, writing, PERIOD, "WRITING")

    resp = client.get(PREVIEW + "?period=" + PERIOD, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # APPROVED 1건만 대상 (WRITING 제외)
    assert body["period"] == PERIOD
    assert body["total"] == 1 and body["ready_count"] == 1 and body["blocked_count"] == 0
    item = body["items"][0]
    assert item["report_id"] == approved_report
    assert item["client_name"] == "미리보기승인운수"
    assert item["filename"].endswith("report.pdf")  # 발송될 실제 첨부파일명(저장 prefix 포함)
    assert item["recipients"] == 1 and item["ready"] is True and item["issue"] is None

    # 무부작용: 미리보기 후에도 상태 불변 + 발송 로그 없음
    assert _report_of(client, staff_headers, approved, PERIOD)["status"] == "APPROVED"
    db = models.SessionLocal()
    logs = (
        db.query(models.ReportSendLog)
        .filter(models.ReportSendLog.report_id == approved_report)
        .all()
    )
    assert logs == []
    db.close()


def test_preview_flags_missing_file(client, staff_headers, admin_headers):
    """파일 없는 APPROVED 건 → ready=False + filename None + issue."""
    nofile = _create_client(client, staff_headers, "미리보기파일없음운수", "prev-n@preview.example.com")
    resp = client.post(API + "/reports/generate", params={"period": PERIOD}, headers=staff_headers)
    assert resp.status_code == 200, resp.text
    report_id = _report_of(client, staff_headers, nofile, PERIOD)["report_id"]
    # 파일 없이 APPROVED 상태를 DB로 직접 강제 (상태 전이 API는 파일 요구)
    db = models.SessionLocal()
    row = db.get(models.ReportDelivery, report_id)
    row.status = "APPROVED"
    row.doc_id = None
    row.pinned_doc_id = None
    db.commit()
    db.close()

    resp = client.get(PREVIEW + "?period=" + PERIOD, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    item = next(it for it in resp.json()["items"] if it["report_id"] == report_id)
    assert item["ready"] is False
    assert item["filename"] is None
    assert "파일" in item["issue"]
