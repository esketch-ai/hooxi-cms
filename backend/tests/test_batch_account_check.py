"""월초 계정 점검 배치 — 대상 필터·사이트 판정·멱등·인증·비밀번호 미노출."""

import os

import models
from routers import batch

CHECK = "/api/v1/batch/account-check"


def _mk_asset(db, client_id, agency, auth_type="ID_PW", login_id="etas001", site="https://x.test"):
    a = models.Asset(
        client_id=client_id,
        asset_group="MOBILITY",
        asset_type="ICE",
        agency_name=agency,
        auth_type=auth_type,
        login_id=login_id,
        site_url=site,
        status="ACTIVE",
    )
    db.add(a)
    db.flush()
    return a.asset_id


def _client_with_pm(db):
    pm = db.query(models.User).filter(models.User.role == "MANAGER").first()
    c = models.Client(client_type="TRANSPORT", company_name="QA-배치운수", manager_id=pm.user_id)
    db.add(c)
    db.flush()
    return c.client_id, pm.user_id


def _issues_for(db, marker_period):
    return (
        db.query(models.ActivityHistory)
        .filter(
            models.ActivityHistory.activity_type == "ISSUE",
            models.ActivityHistory.content.like("%:{0}]%".format(marker_period)),
        )
        .all()
    )


def test_secret_gate(client):
    # 시크릿 미설정·토큰 없음 → 403
    resp = client.post(CHECK + "?period=2030-01")
    assert resp.status_code == 403


def test_admin_can_trigger_targets_all_login_assets(client, admin_headers, monkeypatch, staff_headers):
    # STAFF 토큰은 거부
    assert client.post(CHECK + "?period=2030-02", headers=staff_headers).status_code == 403

    db = models.SessionLocal()
    cid, pm_id = _client_with_pm(db)
    ids = {
        "etas": _mk_asset(db, cid, "ETAS 운행기록", site="https://etas.test"),
        "bms": _mk_asset(db, cid, "경기 BMS", site="https://bms.test"),
        "solar": _mk_asset(db, cid, "한화 태양광 모니터링", site="https://solar.test"),
        "hp": _mk_asset(db, cid, "삼성 히트펌프", auth_type="API_KEY", login_id="hp1", site="https://hp.test"),
    }
    none_id = _mk_asset(db, cid, "계정없는설비", auth_type="NONE", site="https://x")
    db.commit()
    db.close()

    # 사이트: bms만 장애
    monkeypatch.setattr(
        batch, "_site_reachable", lambda url: False if (url and "bms" in url) else True
    )

    resp = client.post(CHECK + "?period=2030-02", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    # 전역 카운트가 아닌, 내가 만든 자산별로 검증 (공유 DB 격리)
    db = models.SessionLocal()

    def issue_for(asset_id):
        return (
            db.query(models.ActivityHistory)
            .filter(
                models.ActivityHistory.activity_type == "ISSUE",
                models.ActivityHistory.content.like("%[점검:{0}:2030-02]%".format(asset_id)),
            )
            .first()
        )

    # 운수사·건물 계정 4종 모두 이슈 생성
    assert issue_for(ids["etas"]) and issue_for(ids["solar"]) and issue_for(ids["hp"])
    assert issue_for(ids["etas"]).priority == "NORMAL"   # 정상 접속
    assert issue_for(ids["bms"]).priority == "URGENT"    # 사이트 장애
    assert issue_for(ids["etas"]).manager_id == pm_id    # 담당 PM
    assert issue_for(none_id) is None                    # 계정 없는 자산은 제외
    db.close()

    db = models.SessionLocal()
    issues = {i.title: i for i in _issues_for(db, "2030-02")}
    etas_issue = next(i for t, i in issues.items() if "ETAS" in t)
    bms_issue = next(i for t, i in issues.items() if "BMS" in t)
    assert etas_issue.priority == "NORMAL"      # 정상 접속
    assert bms_issue.priority == "URGENT"       # 사이트 장애
    assert etas_issue.manager_id == pm_id       # 담당 PM 배정
    assert etas_issue.title.startswith("[자동]")
    # 비밀번호 원문·암호문이 이슈 본문에 없어야 함 (login_id만 노출)
    assert "etas001" in etas_issue.content
    assert "login_password" not in etas_issue.content
    db.close()


def test_idempotent(client, admin_headers, monkeypatch):
    monkeypatch.setattr(batch, "_site_reachable", lambda url: True)
    db = models.SessionLocal()
    cid, _ = _client_with_pm(db)
    _mk_asset(db, cid, "ETAS 단독", site="https://etas-one.test")
    db.commit()
    db.close()

    first = client.post(CHECK + "?period=2030-03", headers=admin_headers).json()
    assert first["created"] >= 1  # 최소 이 테스트 자산 1건
    second = client.post(CHECK + "?period=2030-03", headers=admin_headers).json()
    assert second["created"] == 0 and second["skipped"] == first["targets"]


def test_secret_env_path(client, monkeypatch):
    monkeypatch.setenv("BATCH_SECRET", "batch-xyz")
    monkeypatch.setattr(batch, "_site_reachable", lambda url: True)
    # 잘못된 시크릿 403
    assert client.post(CHECK + "?period=2030-04&secret=wrong").status_code == 403
    # 올바른 시크릿 200 (토큰 없이)
    resp = client.post(CHECK + "?period=2030-04&secret=batch-xyz")
    assert resp.status_code == 200


def test_config_keyword_customization(client, admin_headers, monkeypatch):
    monkeypatch.setattr(batch, "_site_reachable", lambda url: True)
    # 점검 키워드를 TAXICHECK로 재정의 → ETAS는 대상에서 빠짐
    client.put(
        "/api/v1/config/account_check_agencies",
        json={"config_value": '["TAXICHECK"]'},
        headers=admin_headers,
    )
    db = models.SessionLocal()
    cid, _ = _client_with_pm(db)
    _mk_asset(db, cid, "ETAS 제외대상", site="https://e.test")
    _mk_asset(db, cid, "TAXICHECK 포함", site="https://t.test")
    db.commit()
    db.close()

    body = client.post(CHECK + "?period=2030-05", headers=admin_headers).json()
    assert body["targets"] == 1  # TAXICHECK만
    # 원복 — 빈 배열(= 전체 점검, 기본 동작)로 복구
    client.put(
        "/api/v1/config/account_check_agencies",
        json={"config_value": "[]"},
        headers=admin_headers,
    )
