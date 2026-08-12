"""DB 정밀검사 조치 검증 (F1·F2·F5) — 코드 길이 정렬·매핑 유니크·조회 인덱스."""

from sqlalchemy import inspect

API = "/api/v1"


def test_code_over_20_chars_rejected(client, admin_headers):
    """F1 — 코드값 소비 컬럼 String(20) 정합: 21자 코드 생성 422."""
    resp = client.post(
        API + "/codes",
        headers=admin_headers,
        json={"category": "CLIENT_TYPE", "code": "A" * 21, "label": "너무 긴 코드"},
    )
    assert resp.status_code == 422
    # 20자는 허용 (경계)
    resp = client.post(
        API + "/codes",
        headers=admin_headers,
        json={"category": "CLIENT_TYPE", "code": "B" * 20, "label": "경계 코드"},
    )
    assert resp.status_code in (200, 201), resp.text


def test_growth_indexes_exist_and_idempotent():
    """F5 — 조회 인덱스 8종 존재 + ensure_schema 재실행 멱등."""
    import models

    expected = {
        "tb_activity_history": {
            "ix_history_activity_date", "ix_history_client",
            "ix_history_manager", "ix_history_type_status",
        },
        "tb_chat_message": {"ix_chat_message_thread_created"},
        "tb_audit_log": {"ix_audit_created", "ix_audit_actor"},
        "tb_report_delivery": {"ix_report_period_status"},
    }
    models.ensure_schema()  # 멱등 재실행
    insp = inspect(models.engine)
    for table, names in expected.items():
        existing = {ix["name"] for ix in insp.get_indexes(table)}
        missing = names - existing
        assert not missing, f"{table}: {missing}"
