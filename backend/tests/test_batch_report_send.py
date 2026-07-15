"""보고서 배치 자동 발송 (POST /batch/report-send) — 승인 게이트·멱등·실패 격리·인증.

검증 포인트:
- APPROVED(발송승인)만 발송 — WRITING/SENT는 건드리지 않음
- 멱등: 재실행 시 sent=0, SUCCESS send_log 중복 없음
- 실패 격리: 한 건 실패해도 나머지 계속 — 실패 건 APPROVED 유지 + FAIL 로그
- Gmail 미설정(503)은 즉시 전체 중단 — 상태 변경 없음
- 인증: 시크릿 불일치 403 / ADMIN 토큰 허용 / STAFF 거부 (account-check와 동일)
- period 미지정 시 전월(KST) 기본값 + 당월 대상 자동 생성(멱등)
- 부수효과: 성공 건 SENT + sent_at + send_log(EMAIL/SUCCESS) + 활동이력 [자동]
"""

import io

import models
from routers import batch
from services import email_service

API = "/api/v1"
SEND = API + "/batch/report-send"
PERIOD = "2028-05"   # 발송 대상 전용 기간 (타 테스트 모듈과 비충돌)
PERIOD2 = "2028-06"  # 실패 격리 전용 기간
PERIOD3 = "2028-08"  # Gmail 미설정 전용 기간
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


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
        files={"file": ("report.pdf", io.BytesIO(b"PDF-BATCH"), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    path = {"WRITING": [], "APPROVED": ["REVIEW", "APPROVED"], "SENT": ["SENT"]}[to_status]
    for status in path:
        resp = client.put(
            API + "/reports/{0}/status".format(report_id),
            headers=headers,
            json={"status": status},
        )
        assert resp.status_code == 200, resp.text
    return report_id


def _enable_mail(monkeypatch, fail_marker=None):
    """Gmail 환경변수 + send_mail 모킹 — fail_marker 포함 수신자는 발송 예외 유발."""
    monkeypatch.setenv("GMAIL_SENDER", "hooxi12345@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    calls = []

    def fake_send_mail(to, subject, body, cc=None, attachments=None, reply_to=None, html=False):
        if fail_marker and any(fail_marker in addr for addr in to):
            raise RuntimeError("SMTP down (테스트 유발)")
        calls.append({"to": to, "subject": subject})
        return {"sender": "hooxi12345@gmail.com", "recipients": list(to) + list(cc or [])}

    monkeypatch.setattr(email_service, "send_mail", fake_send_mail)
    return calls


def _send_logs(db, report_id):
    return (
        db.query(models.ReportSendLog)
        .filter(models.ReportSendLog.report_id == report_id)
        .all()
    )


# ---------------------------------------------------------------------------
# 인증 — account-check와 동일 게이트
# ---------------------------------------------------------------------------
def test_auth_gate(client, staff_headers, monkeypatch):
    # 시크릿 미설정·토큰 없음 → 403
    assert client.post(SEND + "?period=2030-06").status_code == 403
    # STAFF 토큰 거부
    assert client.post(SEND + "?period=2030-06", headers=staff_headers).status_code == 403
    # 시크릿 불일치 403 / 일치 200 (토큰 없이, 대상 0건 기간)
    monkeypatch.setenv("BATCH_SECRET", "report-xyz")
    assert client.post(SEND + "?period=2030-06&secret=wrong").status_code == 403
    resp = client.post(SEND + "?period=2030-06&secret=report-xyz")
    assert resp.status_code == 200, resp.text
    assert resp.json()["targets"] == 0


# ---------------------------------------------------------------------------
# 승인 게이트 + 성공 부수효과
# ---------------------------------------------------------------------------
def test_approved_gate_and_side_effects(client, staff_headers, admin_headers, monkeypatch):
    S["approved"] = _create_client(client, staff_headers, "배치승인운수", "batch-a@batch-send.example.com")
    S["writing"] = _create_client(client, staff_headers, "배치작성운수", "batch-w@batch-send.example.com")
    S["already"] = _create_client(client, staff_headers, "배치기발송운수", "batch-s@batch-send.example.com")
    resp = client.post(API + "/reports/generate", params={"period": PERIOD}, headers=staff_headers)
    assert resp.status_code == 200, resp.text

    S["approved_report"] = _prepare(client, staff_headers, S["approved"], PERIOD, "APPROVED")
    S["writing_report"] = _prepare(client, staff_headers, S["writing"], PERIOD, "WRITING")
    S["already_report"] = _prepare(client, staff_headers, S["already"], PERIOD, "SENT")

    calls = _enable_mail(monkeypatch)
    resp = client.post(SEND + "?period=" + PERIOD, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["period"] == PERIOD
    assert body["targets"] == 1 and body["sent"] == 1 and body["failed"] == 0
    assert body["details"] == [
        {
            "report_id": S["approved_report"],
            "client_name": "배치승인운수",
            "result": "SENT",
            "detail": None,
        }
    ]
    assert len(calls) == 1 and calls[0]["to"] == ["batch-a@batch-send.example.com"]

    # APPROVED만 발송 — WRITING/SENT는 불변
    assert _report_of(client, staff_headers, S["approved"], PERIOD)["status"] == "SENT"
    assert _report_of(client, staff_headers, S["writing"], PERIOD)["status"] == "WRITING"
    assert _report_of(client, staff_headers, S["already"], PERIOD)["status"] == "SENT"

    db = models.SessionLocal()
    delivery = db.get(models.ReportDelivery, S["approved_report"])
    assert delivery.sent_at is not None and delivery.sent_channel == "EMAIL"
    logs = _send_logs(db, S["approved_report"])
    assert len(logs) == 1
    assert logs[0].channel == "EMAIL" and logs[0].result == "SUCCESS"
    assert logs[0].sent_by == "u-admin"  # ADMIN 토큰 호출 — 그 user_id가 발송자
    assert _send_logs(db, S["already_report"]) == []  # 시드 SENT 건은 미발송(불변)
    # 활동 이력 EMAIL "[자동]" 적재
    history = (
        db.query(models.ActivityHistory)
        .filter(
            models.ActivityHistory.client_id == S["approved"],
            models.ActivityHistory.activity_type == "EMAIL",
        )
        .all()
    )
    assert len(history) == 1 and history[0].title.startswith("[자동]")
    db.close()


def test_idempotent_second_run(client, staff_headers, admin_headers, monkeypatch):
    _enable_mail(monkeypatch)
    resp = client.post(SEND + "?period=" + PERIOD, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 1회차에서 SENT로 전환됐으므로 재실행 대상 없음
    assert body["targets"] == 0 and body["sent"] == 0 and body["failed"] == 0

    db = models.SessionLocal()
    logs = _send_logs(db, S["approved_report"])
    assert len([l for l in logs if l.result == "SUCCESS"]) == 1  # SUCCESS 중복 없음
    db.close()


# ---------------------------------------------------------------------------
# 실패 격리 — 한 건 실패해도 나머지 계속
# ---------------------------------------------------------------------------
def test_failure_isolation(client, staff_headers, admin_headers, monkeypatch):
    S["fail"] = _create_client(client, staff_headers, "배치실패운수", "batch-fail@batch-send.example.com")
    S["ok"] = _create_client(client, staff_headers, "배치성공운수", "batch-ok@batch-send.example.com")
    resp = client.post(API + "/reports/generate", params={"period": PERIOD2}, headers=staff_headers)
    assert resp.status_code == 200, resp.text
    S["fail_report"] = _prepare(client, staff_headers, S["fail"], PERIOD2, "APPROVED")
    S["ok_report"] = _prepare(client, staff_headers, S["ok"], PERIOD2, "APPROVED")

    _enable_mail(monkeypatch, fail_marker="batch-fail")
    resp = client.post(SEND + "?period=" + PERIOD2, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["targets"] == 2 and body["sent"] == 1 and body["failed"] == 1
    by_id = {d["report_id"]: d for d in body["details"]}
    assert by_id[S["ok_report"]]["result"] == "SENT"
    assert by_id[S["fail_report"]]["result"] == "FAIL"
    assert "발송에 실패" in by_id[S["fail_report"]]["detail"]

    # 실패 건은 APPROVED 유지 + FAIL 로그, 성공 건은 SENT
    assert _report_of(client, staff_headers, S["fail"], PERIOD2)["status"] == "APPROVED"
    assert _report_of(client, staff_headers, S["ok"], PERIOD2)["status"] == "SENT"
    db = models.SessionLocal()
    fail_logs = _send_logs(db, S["fail_report"])
    assert len(fail_logs) == 1 and fail_logs[0].result == "FAIL"
    db.close()


# ---------------------------------------------------------------------------
# Gmail 미설정 — 첫 건 감지 시 전체 중단 503 (상태 변경 없음)
# ---------------------------------------------------------------------------
def test_gmail_unconfigured_aborts_503(client, staff_headers, admin_headers):
    S["nomail"] = _create_client(client, staff_headers, "배치메일미설정운수", "batch-n@batch-send.example.com")
    resp = client.post(API + "/reports/generate", params={"period": PERIOD3}, headers=staff_headers)
    assert resp.status_code == 200, resp.text
    S["nomail_report"] = _prepare(client, staff_headers, S["nomail"], PERIOD3, "APPROVED")

    # conftest가 GMAIL_* 를 제거한 상태 그대로 실행 → 503 전체 중단
    resp = client.post(SEND + "?period=" + PERIOD3, headers=admin_headers)
    assert resp.status_code == 503
    assert _report_of(client, staff_headers, S["nomail"], PERIOD3)["status"] == "APPROVED"
    db = models.SessionLocal()
    assert _send_logs(db, S["nomail_report"]) == []  # 로그·상태 변경 없음
    db.close()


# ---------------------------------------------------------------------------
# 기본값(전월) + 당월 대상 자동 생성 (멱등)
# ---------------------------------------------------------------------------
def test_default_previous_period_and_current_generation(client, staff_headers, admin_headers, monkeypatch):
    _enable_mail(monkeypatch)
    current = batch._current_period_kst()

    resp = client.post(SEND, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["period"] == batch._previous_period(current)  # period 미지정 → 전월(KST)

    # 당월 대상 자동 생성 — 구독 활성 고객사의 STANDBY 생성
    row = _report_of(client, staff_headers, S["approved"], current)
    assert row["status"] == "STANDBY"

    # 멱등 — 재실행 시 당월 중복 생성 없음
    resp = client.post(SEND, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["generated_created"] == 0
    db = models.SessionLocal()
    count = (
        db.query(models.ReportDelivery)
        .filter(
            models.ReportDelivery.client_id == S["approved"],
            models.ReportDelivery.period == current,
        )
        .count()
    )
    assert count == 1
    db.close()
