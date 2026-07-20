"""시스템 설정(tb_config)·감사 로그 API 테스트 — SCR-14 (§10.1: ADMIN 전용).

- config CRUD: STAFF 403 / ADMIN OK / 잘못된 JSON 422 / 알려진 키 구조 검증 /
  이력(tb_config_history)·감사 로그(CONFIG_CHANGE) 적재 / 기본값(미저장) 표시
- audit-logs: 필터(action·target_type·기간·actor) + STAFF 403
"""

import json
from datetime import date, timedelta

import models

API = "/api/v1"

SENSITIVE_DEFAULTS = ["수수료", "단가", "계약금액", "보수율", "정산액"]


def _delete_config(config_key):
    """테스트 격리용 — config 행과 이력을 정리한다."""
    db = models.SessionLocal()
    try:
        db.query(models.ConfigHistory).filter(
            models.ConfigHistory.config_key == config_key
        ).delete()
        row = db.get(models.Config, config_key)
        if row is not None:
            db.delete(row)
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 권한 (§10.1: tb_config·감사 로그 = ADMIN 전용)
# ---------------------------------------------------------------------------
def test_config_requires_admin(client, staff_headers):
    assert client.get(API + "/config", headers=staff_headers).status_code == 403
    assert client.get(API + "/config/sensitive_keywords", headers=staff_headers).status_code == 403
    assert (
        client.put(
            API + "/config/sensitive_keywords",
            headers=staff_headers,
            json={"config_value": json.dumps(["수수료"])},
        ).status_code
        == 403
    )
    assert (
        client.get(API + "/config/sensitive_keywords/history", headers=staff_headers).status_code
        == 403
    )


def test_config_requires_auth(client):
    assert client.get(API + "/config").status_code == 401


# ---------------------------------------------------------------------------
# 조회 — 알려진 키 기본값(미저장) 표시
# ---------------------------------------------------------------------------
def test_config_list_includes_unsaved_defaults(client, admin_headers):
    resp = client.get(API + "/config", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    items = {item["config_key"]: item for item in resp.json()}

    # funnel_mapping 은 퍼널 위젯 제거와 함께 알려진 키에서 빠졌다 (회귀)
    assert "funnel_mapping" not in items

    sensitive = items["sensitive_keywords"]
    assert sensitive["is_default"] is True
    assert "기본값(미저장)" in sensitive["description"]
    assert json.loads(sensitive["config_value"]) == SENSITIVE_DEFAULTS


def test_config_get_single_default(client, admin_headers):
    resp = client.get(API + "/config/sensitive_keywords", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_default"] is True
    assert body["updated_at"] is None
    assert json.loads(body["config_value"]) == SENSITIVE_DEFAULTS


def test_config_get_unknown_key_404(client, admin_headers):
    resp = client.get(API + "/config/no_such_key", headers=admin_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 변경 — 값 검증 (잘못된 JSON 422 · 구조 검증)
# ---------------------------------------------------------------------------
def test_config_put_invalid_json_422(client, admin_headers):
    resp = client.put(
        API + "/config/sensitive_keywords",
        headers=admin_headers,
        json={"config_value": "이건 JSON이 아님 {{"},
    )
    assert resp.status_code == 422, resp.text


def test_config_put_sensitive_keywords_validation(client, admin_headers):
    for bad in ({"수수료": 1}, [], ["수수료", 123], ["  "]):
        resp = client.put(
            API + "/config/sensitive_keywords",
            headers=admin_headers,
            json={"config_value": json.dumps(bad, ensure_ascii=False)},
        )
        assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# 변경 — 저장·이력·감사 로그 적재
# ---------------------------------------------------------------------------
def test_config_put_records_history_and_audit(client, admin_headers):
    first = ["수수료", "단가", "위약금"]
    resp = client.put(
        API + "/config/sensitive_keywords",
        headers=admin_headers,
        json={"config_value": json.dumps(first, ensure_ascii=False)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_default"] is False
    assert body["updated_by"] == "u-admin"
    assert body["updated_by_name"] == "관리자"
    assert json.loads(body["config_value"]) == first

    # 단건 조회도 저장값 반환 (기본값 아님)
    resp = client.get(API + "/config/sensitive_keywords", headers=admin_headers)
    assert resp.json()["is_default"] is False

    # 2차 변경 — 이전 값이 이력에 남는다
    second = ["수수료"]
    resp = client.put(
        API + "/config/sensitive_keywords",
        headers=admin_headers,
        json={"config_value": json.dumps(second, ensure_ascii=False), "description": "민감 키워드 축소"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["description"] == "민감 키워드 축소"

    # 이력(최근순): 2건 — 최신 이력의 old_value = 1차 저장값
    resp = client.get(API + "/config/sensitive_keywords/history", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    history = resp.json()
    assert history["total"] == 2
    latest = history["items"][0]
    assert json.loads(latest["old_value"]) == first
    assert json.loads(latest["new_value"]) == second
    assert latest["updated_by_name"] == "관리자"
    oldest = history["items"][1]
    assert oldest["old_value"] is None  # 최초 생성 — 이전 값 없음

    # 감사 로그 CONFIG_CHANGE 적재
    resp = client.get(
        API + "/audit-logs",
        headers=admin_headers,
        params={"action": "CONFIG_CHANGE", "target_type": "CONFIG"},
    )
    assert resp.status_code == 200, resp.text
    logs = resp.json()
    assert logs["total"] >= 2
    assert all(log["action"] == "CONFIG_CHANGE" for log in logs["items"])
    assert logs["items"][0]["target_id"] == "sensitive_keywords"
    assert logs["items"][0]["actor_name"] == "관리자"

    _delete_config("sensitive_keywords")


# ---------------------------------------------------------------------------
# 감사 로그 조회 — 필터·권한
# ---------------------------------------------------------------------------
def test_audit_logs_requires_admin(client, staff_headers):
    assert client.get(API + "/audit-logs", headers=staff_headers).status_code == 403


def test_audit_logs_filters(client, admin_headers):
    # 필터용 로그 적재 (다른 actor 포함)
    db = models.SessionLocal()
    try:
        db.add_all(
            [
                models.AuditLog(
                    actor_id="u-staff", action="REVEAL_AUTH",
                    target_type="ASSET", target_id="asset-x",
                ),
                models.AuditLog(
                    actor_id="u-admin", action="KAKAO_APPROVAL",
                    target_type="KAKAO_CONTACT", target_id="kc-x",
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    # action 필터
    resp = client.get(
        API + "/audit-logs", headers=admin_headers, params={"action": "REVEAL_AUTH"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    assert all(log["action"] == "REVEAL_AUTH" for log in body["items"])
    assert body["items"][0]["actor_name"] == "실무자"  # actor 이름 조인

    # actor 필터
    resp = client.get(
        API + "/audit-logs", headers=admin_headers, params={"actor_id": "u-staff"}
    )
    assert all(log["actor_id"] == "u-staff" for log in resp.json()["items"])

    # target_type 필터
    resp = client.get(
        API + "/audit-logs", headers=admin_headers, params={"target_type": "KAKAO_CONTACT"}
    )
    assert all(log["target_type"] == "KAKAO_CONTACT" for log in resp.json()["items"])

    # 기간 필터 — 미래 구간은 0건
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = client.get(
        API + "/audit-logs", headers=admin_headers, params={"date_from": tomorrow}
    )
    assert resp.json()["total"] == 0

    # 오늘까지 포함 구간은 존재
    resp = client.get(
        API + "/audit-logs",
        headers=admin_headers,
        params={"date_from": date.today().isoformat(), "date_to": date.today().isoformat()},
    )
    assert resp.json()["total"] >= 2

    # 페이지네이션
    resp = client.get(
        API + "/audit-logs", headers=admin_headers, params={"page": 1, "page_size": 1}
    )
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["total"] >= 2
