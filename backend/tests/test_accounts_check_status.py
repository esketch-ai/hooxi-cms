"""수집 계정 관리 뷰 — 계정별 이번 달 점검 상태(check_status)·요약(check_summary)·필터.

점검 상태는 점검 이슈(결정적 PK)에서 라이브 도출: 없음=NOT_CREATED, OPEN=PENDING,
URGENT 미완료=ISSUE, CLOSED=DONE. 담당자가 이슈를 닫으면 계정 화면도 자동 DONE.
"""

import models
from routers import common

API = "/api/v1"
ASSETS = API + "/assets"


def _setup(db):
    pm = db.query(models.User).filter(models.User.role == "MANAGER").first()
    c = models.Client(client_type="TRANSPORT", company_name="점검상태검증운수", manager_id=pm.user_id)
    db.add(c)
    db.flush()
    a = models.Asset(
        client_id=c.client_id, asset_group="MOBILITY", asset_type="ICE",
        agency_name="계정점검상태검증기관", auth_type="ID_PW", login_id="chk001",
        site_url="https://chk-status.test", status="ACTIVE",
    )
    db.add(a)
    db.flush()
    return c.client_id, a.asset_id, pm.user_id


def _put_issue(db, asset_id, period, issue_status, priority, manager_id):
    db.add(
        models.ActivityHistory(
            history_id=common.account_check_issue_id(asset_id, period),
            manager_id=manager_id, created_by=manager_id, activity_date=common.now_kst(),
            activity_type="ISSUE", issue_status=issue_status, priority=priority,
            title="계정 점검", content="[점검:{0}:{1}]".format(asset_id, period),
        )
    )
    db.commit()


def _row(client, headers, client_id, asset_id, **params):
    q = {"credentials_only": "true", "client_id": client_id, **params}
    resp = client.get(ASSETS, headers=headers, params=q)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    row = next((i for i in body["items"] if i["asset_id"] == asset_id), None)
    return body, row


def test_check_status_lifecycle_and_filter(client, admin_headers):
    db = models.SessionLocal()
    cid, aid, pm = _setup(db)
    db.commit()
    period = common.current_period()

    # 1) 이슈 없음 → NOT_CREATED, 요약 not_created>=1
    body, row = _row(client, admin_headers, cid, aid)
    assert row["check_status"]["state"] == "NOT_CREATED"
    assert row["check_status"]["period"] == period
    assert body["check_summary"]["not_created"] >= 1

    # 2) OPEN 이슈 → PENDING (issue_id로 이슈 역추적 가능)
    _put_issue(db, aid, period, "OPEN", "NORMAL", pm)
    _, row = _row(client, admin_headers, cid, aid)
    assert row["check_status"]["state"] == "PENDING"
    assert row["check_status"]["issue_id"] == common.account_check_issue_id(aid, period)

    # 3) URGENT 미완료 → ISSUE
    iss = db.get(models.ActivityHistory, common.account_check_issue_id(aid, period))
    iss.priority = "URGENT"
    db.commit()
    _, row = _row(client, admin_headers, cid, aid)
    assert row["check_status"]["state"] == "ISSUE"

    # 4) CLOSED → DONE (담당자가 이슈 처리 시 계정 화면 자동 반영)
    iss = db.get(models.ActivityHistory, common.account_check_issue_id(aid, period))
    iss.issue_status = "CLOSED"
    db.commit()
    body, row = _row(client, admin_headers, cid, aid)
    assert row["check_status"]["state"] == "DONE"
    assert body["check_summary"]["done"] >= 1

    # 5) '미완료만 보기'(check_state=pending) → DONE 건은 제외
    _, row = _row(client, admin_headers, cid, aid, check_state="pending")
    assert row is None
    db.close()
