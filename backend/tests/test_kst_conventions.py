"""KST 벽시계 규약 회귀 테스트 — 자동 적재 activity_date·'당월' 기준 (감사 지적 2·7).

경계 시각: UTC 2026-06-30 23:30 = KST 2026-07-01 08:30
(매월 1일 08:00 KST Cloud Scheduler 배치가 도는 시간대 = UTC로는 전날 23:00).
이때 activity_date가 07-01로, current_period()가 '2026-07'로 계산되어야 한다.
"""

from datetime import date, datetime

import models
from routers import batch, common

CHECK = "/api/v1/batch/account-check"

# UTC 2026-06-30 23:30 = KST 2026-07-01 08:30 — 날짜가 갈리는 경계
FROZEN_UTC = datetime(2026, 6, 30, 23, 30, 0)


def _freeze(monkeypatch):
    """common 모듈의 utcnow만 고정 — now_kst()·current_period()가 이를 참조."""
    monkeypatch.setattr(common, "utcnow", lambda: FROZEN_UTC)


# ---------------------------------------------------------------------------
# '당월' 계산 — KST 기준 통일 (지적 7)
# ---------------------------------------------------------------------------
def test_current_period_is_kst_at_month_boundary(monkeypatch):
    _freeze(monkeypatch)
    assert common.now_kst() == datetime(2026, 7, 1, 8, 30, 0)
    assert common.current_period() == "2026-07"  # UTC 기준이면 '2026-06'으로 밀림
    # 배치 하위호환 별칭도 같은 구현을 공유
    assert batch._current_period_kst() == "2026-07"


def test_previous_period_month_rollback():
    assert common.previous_period("2026-07") == "2026-06"
    assert common.previous_period("2026-01") == "2025-12"  # 연 경계
    assert batch._previous_period("2026-07") == "2026-06"


# ---------------------------------------------------------------------------
# 자동 적재 activity_date — 저장값=KST 벽시계 (지적 2)
# ---------------------------------------------------------------------------
def test_account_check_activity_date_is_kst_wall_clock(client, admin_headers, monkeypatch):
    _freeze(monkeypatch)
    monkeypatch.setattr(batch, "_site_reachable", lambda url: True)

    db = models.SessionLocal()
    pm = db.query(models.User).filter(models.User.role == "MANAGER").first()
    c = models.Client(client_type="TRANSPORT", company_name="QA-KST경계", manager_id=pm.user_id)
    db.add(c)
    db.flush()
    a = models.Asset(
        client_id=c.client_id,
        asset_group="MOBILITY",
        asset_type="ICE",
        agency_name="ETAS KST경계",
        auth_type="ID_PW",
        login_id="kst001",
        site_url="https://kst.test",
        status="ACTIVE",
    )
    db.add(a)
    db.commit()
    asset_id = a.asset_id
    db.close()

    # period 미지정 → 기본값도 KST 당월(2026-07)이어야 함
    resp = client.post(CHECK, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["period"] == "2026-07"

    db = models.SessionLocal()
    issue = (
        db.query(models.ActivityHistory)
        .filter(
            models.ActivityHistory.activity_type == "ISSUE",
            models.ActivityHistory.content.like("%[점검:{0}:2026-07]%".format(asset_id)),
        )
        .first()
    )
    assert issue is not None
    # UTC(06-30)가 아닌 KST 벽시계(07-01 08:30)로 저장돼야 함
    assert issue.activity_date == datetime(2026, 7, 1, 8, 30, 0)
    assert issue.due_date == date(2026, 7, 5)  # 당월 5일까지 처리
    # created_at 계열은 naive UTC 저장 규약 유지 — 고정 시각(과거)이 아닌 실제 서버 시각
    assert issue.created_at != FROZEN_UTC
    db.close()
