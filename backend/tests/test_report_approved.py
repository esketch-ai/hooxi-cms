"""보고서 APPROVED(발송승인) 상태 — 배치 자동 발송 전제 상태 신설 스모크.

검증 포인트:
- REVIEW → APPROVED 전이 200 (발송할 파일이 있는 건)
- 파일 없는 건 APPROVED 전이 409 (발송 불가 — 파일 선행 업로드 요구)
- 발송 현황 요약에 approved 카운트 반영
- 공통 코드 마스터(REPORT_STATUS) 시드 노출 + 전 값 로직 잠금
- 상태 전이 사전 서버 강제(감사 수정 ①): CANCELED→APPROVED 차단(오발송 경로),
  SENT 직접 설정 차단, CONFIRMED 최종 상태, CANCELED→STANDBY 복원 후 재진행
"""

import io

import models

API = "/api/v1"
PERIOD = "2027-01"  # 타 테스트 모듈(당월)과 겹치지 않는 전용 기간
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


def _create_client(client, headers, name):
    resp = client.post(
        API + "/clients",
        headers=headers,
        json={
            "client_type": "TRANSPORT",
            "company_name": name,
            "contract_status": "ACTIVE",
            "report_yn": "Y",
            "subscription": {"report_type": "월간 운행 보고서", "channel": "EMAIL", "due_day": 25},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["client_id"]


def _report_of(client, headers, client_id):
    resp = client.get(API + "/reports", params={"period": PERIOD}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    mine = [i for i in body["items"] if i["client_id"] == client_id]
    assert len(mine) == 1
    return body["summary"], mine[0]


def test_setup_generate_reports(client, staff_headers):
    S["with_file"] = _create_client(client, staff_headers, "승인테스트운수")
    S["no_file"] = _create_client(client, staff_headers, "미승인테스트운수")
    resp = client.post(
        API + "/reports/generate", params={"period": PERIOD}, headers=staff_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"] >= 2


def test_review_to_approved_with_file(client, staff_headers):
    _, row = _report_of(client, staff_headers, S["with_file"])
    S["report_id"] = row["report_id"]

    # 파일 업로드(STANDBY → WRITING) 후 REVIEW 경유
    resp = client.post(
        API + "/reports/{0}/file".format(S["report_id"]),
        headers=staff_headers,
        files={"file": ("report.pdf", io.BytesIO(b"PDF-APPROVE"), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    resp = client.put(
        API + "/reports/{0}/status".format(S["report_id"]),
        headers=staff_headers,
        json={"status": "REVIEW"},
    )
    assert resp.status_code == 200, resp.text

    # 파일이 있으므로 APPROVED 전이 허용
    resp = client.put(
        API + "/reports/{0}/status".format(S["report_id"]),
        headers=staff_headers,
        json={"status": "APPROVED"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "APPROVED"


def test_approved_without_file_409(client, staff_headers):
    # 전이 사전 도입으로 STANDBY→APPROVED는 전이 자체가 차단 — WRITING 경유 후 파일 검증 확인
    _, row = _report_of(client, staff_headers, S["no_file"])
    resp = client.put(
        API + "/reports/{0}/status".format(row["report_id"]),
        headers=staff_headers,
        json={"status": "WRITING"},
    )
    assert resp.status_code == 200, resp.text

    resp = client.put(
        API + "/reports/{0}/status".format(row["report_id"]),
        headers=staff_headers,
        json={"status": "APPROVED"},
    )
    assert resp.status_code == 409
    assert "파일" in resp.json()["detail"]

    # 상태는 유지 (전이 거부)
    _, row = _report_of(client, staff_headers, S["no_file"])
    assert row["status"] == "WRITING"


def test_summary_counts_approved(client, staff_headers):
    summary, row = _report_of(client, staff_headers, S["with_file"])
    assert row["status"] == "APPROVED"
    assert summary["approved"] >= 1


# ---------------------------------------------------------------------------
# 상태 전이 사전 서버 강제 (감사 수정 ①)
# ---------------------------------------------------------------------------
def _put_status(client, headers, report_id, body):
    return client.put(
        API + "/reports/{0}/status".format(report_id), headers=headers, json=body
    )


def test_canceled_to_approved_blocked_409(client, staff_headers):
    """핵심 — CANCELED→APPROVED 1콜 차단 (월초 배치 오발송 경로)."""
    # APPROVED 건을 취소(사유 필수) 후 곧바로 재승인 시도
    resp = _put_status(
        client, staff_headers, S["report_id"],
        {"status": "CANCELED", "canceled_reason": "고객 요청 취소"},
    )
    assert resp.status_code == 200, resp.text

    resp = _put_status(client, staff_headers, S["report_id"], {"status": "APPROVED"})
    assert resp.status_code == 409
    assert "변경할 수 없습니다" in resp.json()["detail"]

    # 상태 유지 — 배치 발송 대상(APPROVED)으로 되살아나지 않음
    _, row = _report_of(client, staff_headers, S["with_file"])
    assert row["status"] == "CANCELED"


def test_canceled_restore_then_normal_flow(client, staff_headers):
    """CANCELED→STANDBY 복원(사유 초기화) 후 정상 흐름 재진행 가능."""
    resp = _put_status(client, staff_headers, S["report_id"], {"status": "STANDBY"})
    assert resp.status_code == 200, resp.text
    assert resp.json().get("canceled_reason") in (None, "")

    # 복원 후 정상 흐름: STANDBY→WRITING→REVIEW→APPROVED (파일은 기존 업로드분 유지)
    for status in ("WRITING", "REVIEW", "APPROVED"):
        resp = _put_status(client, staff_headers, S["report_id"], {"status": status})
        assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "APPROVED"


def test_sent_direct_set_blocked_409(client, staff_headers):
    """SENT 직접 설정 차단 — 발송 경로(send_report_core)만 SENT 가능 (KPI 왜곡 방지)."""
    resp = _put_status(client, staff_headers, S["report_id"], {"status": "SENT"})
    assert resp.status_code == 409
    assert "변경할 수 없습니다" in resp.json()["detail"]

    _, row = _report_of(client, staff_headers, S["with_file"])
    assert row["status"] == "APPROVED"


def test_confirmed_is_terminal(client, staff_headers):
    """SENT→CONFIRMED만 허용, CONFIRMED→STANDBY 역행 409 (KPI 왜곡 방지)."""
    # SENT는 발송 코어 전용 — 테스트는 발송 완료 상태를 DB로 시드
    db = models.SessionLocal()
    db.get(models.ReportDelivery, S["report_id"]).status = "SENT"
    db.commit()
    db.close()

    resp = _put_status(
        client, staff_headers, S["report_id"],
        {"status": "CONFIRMED", "confirm_basis": "회신메일"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CONFIRMED"

    resp = _put_status(client, staff_headers, S["report_id"], {"status": "STANDBY"})
    assert resp.status_code == 409
    assert "변경할 수 없습니다" in resp.json()["detail"]


def test_report_status_codes_seeded_and_locked(client, admin_headers):
    rows = client.get(
        API + "/codes",
        params={"category": "REPORT_STATUS", "include_inactive": True},
        headers=admin_headers,
    ).json()
    by_code = {c["code"]: c for c in rows}
    assert by_code["APPROVED"]["label"] == "발송승인"
    assert by_code["APPROVED"]["is_system"] == "Y"
    assert set(by_code) >= {
        "STANDBY", "WRITING", "REVIEW", "APPROVED", "SENT", "CONFIRMED", "CANCELED"
    }

    # 전 값 로직 잠금 — 삭제 차단 409 (상태전이 머신·배치 참조)
    resp = client.delete(
        API + "/codes/{0}".format(by_code["APPROVED"]["code_id"]), headers=admin_headers
    )
    assert resp.status_code == 409
