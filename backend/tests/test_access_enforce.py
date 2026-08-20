"""접근 그룹 G2 — off/monitor/enforce 모드·경로 매칭·ADMIN 우회·감사로그."""

import access_control
import models
from access_control import is_path_allowed


def _set_mode(db, mode):
    row = db.get(models.Config, access_control.ACCESS_CONTROL_MODE_KEY)
    if row is None:
        row = models.Config(config_key=access_control.ACCESS_CONTROL_MODE_KEY)
        db.add(row)
    row.config_value = '"%s"' % mode
    db.commit()


def _mk_user(db, uid, role="STAFF", group_name=None):
    u = models.User(user_id=uid, email=f"{uid}@hooxi.kr", role=role, status="ACTIVE")
    db.add(u)
    db.commit()
    if group_name:
        g = db.query(models.AccessGroup).filter_by(name=group_name).first()
        db.add(models.UserGroup(user_id=uid, group_id=g.group_id))
        db.commit()
    return u


def _cleanup(db):
    db.query(models.UserGroup).filter(
        models.UserGroup.user_id.like("t-en-%")).delete(synchronize_session=False)
    db.query(models.AuditLog).filter(
        models.AuditLog.actor_id.like("t-en-%")).delete(synchronize_session=False)
    db.query(models.User).filter(
        models.User.user_id.like("t-en-%")).delete(synchronize_session=False)
    _set_mode(db, "off")
    db.commit()


def test_path_matching_rules():
    menus = ["/settlements", "/accounts"]
    assert is_path_allowed("GET", "/api/v1/settlements", menus)
    assert is_path_allowed("POST", "/api/v1/settlements/abc/confirm", menus)
    assert is_path_allowed("GET", "/api/v1/assets", menus)        # accounts→GET assets
    assert not is_path_allowed("POST", "/api/v1/assets", menus)   # 쓰기는 /assets 메뉴 필요
    assert not is_path_allowed("GET", "/api/v1/tax-invoices", menus)
    # 전역 허용
    assert is_path_allowed("GET", "/api/v1/users/me", [])
    assert is_path_allowed("GET", "/api/v1/codes", [])
    assert is_path_allowed("GET", "/api/v1/users", [])
    assert not is_path_allowed("PUT", "/api/v1/users/xyz/role", [])  # 변경은 /settings 필요


def test_enforce_blocks_out_of_scope(client):
    """enforce: 그룹 밖 API 403, 그룹 내 API 통과. off로 복원하면 다시 전부 통과."""
    from auth import create_access_token

    db = models.SessionLocal()
    try:
        _cleanup(db)
        u = _mk_user(db, "t-en-fin", role="STAFF", group_name="정산재무")
        h = {"Authorization": "Bearer " + create_access_token(u)}
        _set_mode(db, "enforce")
        access_control._monitor_seen.clear()
        # 정산재무 그룹: /settlements 허용
        r_ok = client.get("/api/v1/settlements", headers=h)
        assert r_ok.status_code != 403, r_ok.text
        # 그룹 밖: /chat 차단
        r_no = client.get("/api/v1/chat/threads", headers=h)
        assert r_no.status_code == 403
        # 전역 허용은 통과
        assert client.get("/api/v1/users/me", headers=h).status_code == 200
        # off 복원 → 통과
        _set_mode(db, "off")
        assert client.get("/api/v1/chat/threads", headers=h).status_code != 403
    finally:
        _cleanup(db)
        db.close()


def test_monitor_logs_without_blocking(client):
    from auth import create_access_token

    db = models.SessionLocal()
    try:
        _cleanup(db)
        u = _mk_user(db, "t-en-mon", role="STAFF", group_name="자산관리")
        h = {"Authorization": "Bearer " + create_access_token(u)}
        _set_mode(db, "monitor")
        access_control._monitor_seen.clear()
        r = client.get("/api/v1/settlements", headers=h)  # 자산관리 그룹 밖
        assert r.status_code != 403  # 차단 없음
        log = (db.query(models.AuditLog)
               .filter_by(actor_id="t-en-mon", action="ACCESS_DENY_WOULD").first())
        assert log is not None and "/api/v1/settlements" in (log.new_value or "")
    finally:
        _cleanup(db)
        db.close()


def test_enforce_admin_and_default_group_bypass(client):
    """ADMIN은 enforce에서도 전 API. 그룹 미배정(전사 암묵)도 전 메뉴라 차단 없음."""
    from auth import create_access_token

    db = models.SessionLocal()
    try:
        _cleanup(db)
        adm = _mk_user(db, "t-en-adm", role="ADMIN")
        stf = _mk_user(db, "t-en-stf", role="STAFF")  # 미배정 → 전사 암묵
        _set_mode(db, "enforce")
        ha = {"Authorization": "Bearer " + create_access_token(adm)}
        hs = {"Authorization": "Bearer " + create_access_token(stf)}
        assert client.get("/api/v1/chat/threads", headers=ha).status_code != 403
        assert client.get("/api/v1/chat/threads", headers=hs).status_code != 403
    finally:
        _cleanup(db)
        db.close()
