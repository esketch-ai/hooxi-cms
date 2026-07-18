"""P1-D 활동 이력 제한적 수정 — 고객사 사후 연결·이슈 담당자 인계 스모크.

정책 (시나리오 #3, 사용자 확정): 기록 불변 원칙 유지 — 단 2개 필드만 예외.
- PATCH /histories/{id}/client: client_id가 null인 이력만 연결(변경 불허 409) + 감사 HISTORY_CLIENT_LINK
- PATCH /histories/{id}/manager: ISSUE 유형만, ASSIGN 코멘트+감사 ISSUE_ASSIGN, 자기 자신 무변경 200
- 동시성: P0-B 조건부 UPDATE 준용 — 스냅샷 불일치 시 409 + phantom 흔적 없음
"""

from sqlalchemy import text as sa_text

import models
from routers import common as rcommon

API = "/api/v1"
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


def _inject_after_snapshot(monkeypatch, model, target_id, sql, params):
    """get_or_404 스냅샷 직후 raw UPDATE 1회 주입 — 동시 변경 인터리빙 재현 (P0-B와 동일)."""
    orig = rcommon.get_or_404
    fired = {"done": False}

    def stale_get(db, m, pk, label):
        obj = orig(db, m, pk, label)
        if m is model and pk == target_id and not fired["done"]:
            fired["done"] = True
            db.execute(sa_text(sql), params)
        return obj

    monkeypatch.setattr(rcommon, "get_or_404", stale_get)


def _audit_count(action, target_id):
    db = models.SessionLocal()
    try:
        return (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == action, models.AuditLog.target_id == target_id)
            .count()
        )
    finally:
        db.close()


def _last_audit(action, target_id):
    db = models.SessionLocal()
    try:
        return (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == action, models.AuditLog.target_id == target_id)
            .order_by(models.AuditLog.created_at.desc())
            .first()
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 준비 — 고객사 1 + 미상 고객 이력(CALL) 2 + 이슈 1
# ---------------------------------------------------------------------------
def test_setup(client, staff_headers):
    resp = client.post(
        API + "/clients",
        headers=staff_headers,
        json={
            "client_type": "TRANSPORT",
            "company_name": "이력수정운수",  # 타 모듈 검색 검증과 겹치지 않는 이름
            "contract_status": "ACTIVE",
        },
    )
    assert resp.status_code == 201, resp.text
    S["client_id"] = resp.json()["client_id"]

    for key in ("call_id", "call_id2"):
        resp = client.post(
            API + "/histories",
            headers=staff_headers,
            json={
                "activity_date": "2027-03-01T09:00:00",
                "activity_type": "CALL",
                "title": "미상 고객 문의 전화 ({0})".format(key),
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["client_id"] is None
        S[key] = resp.json()["history_id"]

    resp = client.post(
        API + "/histories",
        headers=staff_headers,
        json={
            "activity_date": "2027-03-02T10:00:00",
            "activity_type": "ISSUE",
            "title": "담당자 인계 테스트 이슈",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["manager_id"] == "u-staff"  # 작성자 기본 담당
    S["issue_id"] = resp.json()["history_id"]


# ---------------------------------------------------------------------------
# 1) 고객사 사후 연결 — 성공 + 감사 / 이미 연결 409 / 없는 고객사 404 / 동시성 409
# ---------------------------------------------------------------------------
def test_client_link_success_with_audit(client, staff_headers):
    resp = client.patch(
        API + "/histories/{0}/client".format(S["call_id"]),
        headers=staff_headers,
        json={"client_id": S["client_id"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["client_id"] == S["client_id"]
    assert resp.json()["client_name"] == "이력수정운수"

    log = _last_audit("HISTORY_CLIENT_LINK", S["call_id"])
    assert log is not None
    assert log.old_value == "미지정"
    assert log.new_value == "이력수정운수"


def test_client_link_already_linked_409(client, staff_headers):
    """이미 연결된 이력의 고객사 변경(재연결)은 불허 — 기록 위조 방지."""
    resp = client.patch(
        API + "/histories/{0}/client".format(S["call_id"]),
        headers=staff_headers,
        json={"client_id": S["client_id"]},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "이미 고객사가 연결된 이력입니다"
    assert _audit_count("HISTORY_CLIENT_LINK", S["call_id"]) == 1  # 감사 추가 없음


def test_client_link_unknown_client_404(client, staff_headers):
    resp = client.patch(
        API + "/histories/{0}/client".format(S["call_id2"]),
        headers=staff_headers,
        json={"client_id": "no-such-client"},
    )
    assert resp.status_code == 404, resp.text


def test_client_link_stale_conflict_409(client, staff_headers, monkeypatch):
    """스냅샷(미연결) 이후 다른 사용자가 먼저 연결 → 조건부 UPDATE 0건 → 409 + 감사 없음."""
    _inject_after_snapshot(
        monkeypatch,
        models.ActivityHistory,
        S["call_id2"],
        "UPDATE tb_activity_history SET client_id=:c WHERE history_id=:h",
        {"c": S["client_id"], "h": S["call_id2"]},
    )
    resp = client.patch(
        API + "/histories/{0}/client".format(S["call_id2"]),
        headers=staff_headers,
        json={"client_id": S["client_id"]},
    )
    assert resp.status_code == 409, resp.text
    assert "다른 사용자가 방금 고객사를 연결했습니다" in resp.json()["detail"]
    assert _audit_count("HISTORY_CLIENT_LINK", S["call_id2"]) == 0


# ---------------------------------------------------------------------------
# 2) 이슈 담당자 인계 — 성공+ASSIGN 코멘트+감사 / 자기 자신 무변경 / 비이슈 409 /
#    비ACTIVE 422 / 없는 사용자 404 / 동시성 409
# ---------------------------------------------------------------------------
def _assign_comments(client, headers, history_id):
    resp = client.get(API + "/histories/{0}/comments".format(history_id), headers=headers)
    assert resp.status_code == 200
    return [c for c in resp.json() if c["comment_type"] == "ASSIGN"]


def test_manager_transfer_success_with_comment_and_audit(client, staff_headers):
    resp = client.patch(
        API + "/histories/{0}/manager".format(S["issue_id"]),
        headers=staff_headers,
        json={"manager_id": "u-manager"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["manager_id"] == "u-manager"

    comments = _assign_comments(client, staff_headers, S["issue_id"])
    assert len(comments) == 1
    assert comments[0]["content"] == "담당자 변경: 실무자 → 팀장"

    log = _last_audit("ISSUE_ASSIGN", S["issue_id"])
    assert log is not None
    assert log.old_value == "실무자"
    assert log.new_value == "팀장"


def test_manager_transfer_to_self_noop_200(client, staff_headers):
    """현 담당자 그대로 지정 — 무변경 200, 코멘트·감사 추가 없음."""
    resp = client.patch(
        API + "/histories/{0}/manager".format(S["issue_id"]),
        headers=staff_headers,
        json={"manager_id": "u-manager"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["manager_id"] == "u-manager"
    assert len(_assign_comments(client, staff_headers, S["issue_id"])) == 1
    assert _audit_count("ISSUE_ASSIGN", S["issue_id"]) == 1


def test_manager_transfer_non_issue_409(client, staff_headers):
    resp = client.patch(
        API + "/histories/{0}/manager".format(S["call_id"]),
        headers=staff_headers,
        json={"manager_id": "u-manager"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "이슈(ISSUE) 유형의 이력만 담당자를 변경할 수 있습니다"


def test_manager_transfer_inactive_user_422(client, staff_headers):
    resp = client.patch(
        API + "/histories/{0}/manager".format(S["issue_id"]),
        headers=staff_headers,
        json={"manager_id": "u-pending"},  # conftest 시드 PENDING 사용자
    )
    assert resp.status_code == 422, resp.text
    assert "ACTIVE" in resp.json()["detail"]


def test_manager_transfer_unknown_user_404(client, staff_headers):
    resp = client.patch(
        API + "/histories/{0}/manager".format(S["issue_id"]),
        headers=staff_headers,
        json={"manager_id": "no-such-user"},
    )
    assert resp.status_code == 404, resp.text


def test_manager_transfer_stale_conflict_409(client, staff_headers, monkeypatch):
    """스냅샷(u-manager) 이후 다른 사용자가 u-admin으로 인계 → 409 + phantom 흔적 없음."""
    _inject_after_snapshot(
        monkeypatch,
        models.ActivityHistory,
        S["issue_id"],
        "UPDATE tb_activity_history SET manager_id='u-admin' WHERE history_id=:h",
        {"h": S["issue_id"]},
    )
    resp = client.patch(
        API + "/histories/{0}/manager".format(S["issue_id"]),
        headers=staff_headers,
        json={"manager_id": "u-staff"},
    )
    assert resp.status_code == 409, resp.text
    assert "다른 사용자가 방금 담당자를 변경했습니다" in resp.json()["detail"]
    # 반려 건은 실제 인계가 아니므로 ASSIGN 코멘트·감사 로그 미증가
    assert len(_assign_comments(client, staff_headers, S["issue_id"])) == 1
    assert _audit_count("ISSUE_ASSIGN", S["issue_id"]) == 1
