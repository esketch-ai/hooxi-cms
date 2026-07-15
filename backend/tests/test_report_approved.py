"""보고서 APPROVED(발송승인) 상태 — 배치 자동 발송 전제 상태 신설 스모크.

검증 포인트:
- REVIEW → APPROVED 전이 200 (발송할 파일이 있는 건)
- 파일 없는 건 APPROVED 전이 409 (발송 불가 — 파일 선행 업로드 요구)
- 발송 현황 요약에 approved 카운트 반영
- 공통 코드 마스터(REPORT_STATUS) 시드 노출 + 전 값 로직 잠금
"""

import io

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
    _, row = _report_of(client, staff_headers, S["no_file"])
    resp = client.put(
        API + "/reports/{0}/status".format(row["report_id"]),
        headers=staff_headers,
        json={"status": "APPROVED"},
    )
    assert resp.status_code == 409
    assert "파일" in resp.json()["detail"]

    # 상태는 유지 (전이 거부)
    _, row = _report_of(client, staff_headers, S["no_file"])
    assert row["status"] == "STANDBY"


def test_summary_counts_approved(client, staff_headers):
    summary, row = _report_of(client, staff_headers, S["with_file"])
    assert row["status"] == "APPROVED"
    assert summary["approved"] >= 1


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
