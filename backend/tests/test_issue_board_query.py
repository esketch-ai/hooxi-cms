"""이슈 보드 조회 필터 테스트 — issue_status 콤마 다중 값 + closed_since (감사 ③ 200건 절단 해소).

세션 공유 SQLite에서 다른 테스트와 섞이지 않도록 전용 고객사(client_id)로 격리한다.
"""

from datetime import datetime, timedelta

import pytest

import models

API = "/api/v1"

# closed_since 경계 검증용 고정 컷오프 (YYYY-MM-DD)
CUTOFF = datetime(2026, 6, 1)


@pytest.fixture(scope="module")
def board(client, staff_headers):
    """전용 고객사 + 상태별 이슈 시딩 — {client_id, ids{status: history_id}} 반환."""
    resp = client.post(
        API + "/clients",
        headers=staff_headers,
        json={
            "client_type": "TRANSPORT",
            "company_name": "이슈보드쿼리테스트",
            "manager_id": "u-manager",
        },
    )
    assert resp.status_code == 201, resp.text
    client_id = resp.json()["client_id"]

    ids = {}
    seeds = [
        ("OPEN", "보드 접수 이슈"),
        ("IN_PROGRESS", "보드 처리중 이슈"),
        ("HOLD", "보드 보류 이슈"),
        ("CLOSED", "보드 최근 완료 이슈"),
        ("CLOSED_OLD", "보드 옛 완료 이슈"),
    ]
    for key, title in seeds:
        status = "CLOSED" if key.startswith("CLOSED") else key
        resp = client.post(
            API + "/histories",
            headers=staff_headers,
            json={
                "client_id": client_id,
                "activity_date": "2026-06-10T09:00:00",
                "activity_type": "ISSUE",
                "issue_status": status,
                "title": title,
            },
        )
        assert resp.status_code == 201, resp.text
        ids[key] = resp.json()["history_id"]

    # closed_since 경계 검증용 updated_at 직접 세팅 — bulk update라 onupdate 미적용
    db = models.SessionLocal()
    try:
        db.query(models.ActivityHistory).filter(
            models.ActivityHistory.history_id == ids["CLOSED"]
        ).update({"updated_at": CUTOFF})  # 경계값(포함) — 컷오프 당일 자정
        db.query(models.ActivityHistory).filter(
            models.ActivityHistory.history_id == ids["CLOSED_OLD"]
        ).update({"updated_at": CUTOFF - timedelta(days=10)})
        db.commit()
    finally:
        db.close()

    return {"client_id": client_id, "ids": ids}


def _fetch(client, headers, board, **params):
    params = dict({"client_id": board["client_id"], "activity_type": "ISSUE"}, **params)
    resp = client.get(API + "/histories", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_issue_status_single_value_backward_compat(client, staff_headers, board):
    """기존 단일 값 호출 하위 호환 — OPEN만 반환."""
    body = _fetch(client, staff_headers, board, issue_status="OPEN")
    assert body["total"] == 1
    assert [h["issue_status"] for h in body["items"]] == ["OPEN"]


def test_issue_status_comma_multi_values(client, staff_headers, board):
    """콤마 다중 값 — OPEN+HOLD만 반환 (공백 섞여도 허용)."""
    body = _fetch(client, staff_headers, board, issue_status="OPEN, HOLD")
    assert body["total"] == 2
    assert sorted(h["issue_status"] for h in body["items"]) == ["HOLD", "OPEN"]


def test_open_board_query_excludes_closed(client, staff_headers, board):
    """미종결 보드 쿼리(OPEN,IN_PROGRESS,HOLD)에 CLOSED가 섞이지 않는다."""
    body = _fetch(client, staff_headers, board, issue_status="OPEN,IN_PROGRESS,HOLD")
    assert body["total"] == 3
    statuses = {h["issue_status"] for h in body["items"]}
    assert "CLOSED" not in statuses
    assert statuses == {"OPEN", "IN_PROGRESS", "HOLD"}


def test_closed_since_filters_recent_only(client, staff_headers, board):
    """closed_since — 컷오프 이후 갱신된 CLOSED만 (경계일 자정 포함)."""
    body = _fetch(
        client, staff_headers, board,
        issue_status="CLOSED", closed_since=CUTOFF.date().isoformat(),
    )
    assert body["total"] == 1
    assert body["items"][0]["history_id"] == board["ids"]["CLOSED"]


def test_closed_without_since_returns_all(client, staff_headers, board):
    """closed_since 미지정 시 기존과 동일하게 CLOSED 전건."""
    body = _fetch(client, staff_headers, board, issue_status="CLOSED")
    assert body["total"] == 2
