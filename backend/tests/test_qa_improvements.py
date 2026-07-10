"""QA 점검 후속 개선 — 취소 사유 초기화·report_yn 자동·active bool 수용·감사 커밋 순서."""

import models


def _audits(action):
    db = models.SessionLocal()
    try:
        return (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == action)
            .order_by(models.AuditLog.created_at.desc())
            .all()
        )
    finally:
        db.close()


def test_subscription_bool_active_and_report_yn(client, admin_headers):
    """active에 JSON boolean 수용 + 활성 구독 등록 시 report_yn 자동 Y."""
    resp = client.post(
        "/api/v1/clients",
        json={
            "client_type": "TRANSPORT",
            "company_name": "QA-개선검증운수",
            "subscription": {"report_type": "월간 운행", "active": True},
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["report_yn"] == "Y"  # 기본 N이지만 활성 구독으로 자동 Y
    assert body["subscriptions"][0]["active"] == "Y"  # bool → "Y" 변환


def test_canceled_reason_cleared_on_recover(client, admin_headers):
    """CANCELED → 다른 상태 복귀 시 취소 사유 잔존 제거."""
    period = "2030-01"
    client.post(
        "/api/v1/reports/generate?period={0}".format(period), headers=admin_headers
    )
    rows = client.get(
        "/api/v1/reports?period={0}".format(period), headers=admin_headers
    ).json()["items"]
    assert rows, "generate 대상이 없습니다"
    rid = rows[0]["report_id"]

    resp = client.put(
        "/api/v1/reports/{0}/status".format(rid),
        json={"status": "CANCELED", "canceled_reason": "QA-사유"},
        headers=admin_headers,
    )
    assert resp.json()["canceled_reason"] == "QA-사유"

    resp = client.put(
        "/api/v1/reports/{0}/status".format(rid),
        json={"status": "WRITING"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json().get("canceled_reason") in (None, "")


def test_project_update_audit_persisted(client, admin_headers):
    """감사 로그가 커밋 전에 적재되어 실제로 저장되는지 (커밋 순서 회귀 방지)."""
    proj = client.post(
        "/api/v1/projects",
        json={"project_name": "QA-감사검증사업", "reg_no": "R-2026-KR-03-999901"},
        headers=admin_headers,
    )
    assert proj.status_code in (200, 201), proj.text
    pid = proj.json()["project_id"]
    assert _audits("PROJECT_CREATE") and _audits("PROJECT_CREATE")[0].target_id == pid

    resp = client.put(
        "/api/v1/projects/{0}".format(pid),
        json={"progress_status": "등록완료"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    logs = _audits("PROJECT_UPDATE")
    assert logs and logs[0].target_id == pid  # 커밋 후 add였다면 유실되어 실패
