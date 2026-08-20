"""접근 그룹(G1) — 시드·암묵 기본그룹·합집합·ADMIN 우회·/users/me 확장."""

import main
import models
from access_control import MENU_KEYS, resolve_user_access


def _cleanup(db):
    db.query(models.UserGroup).filter(
        models.UserGroup.user_id.like("t-ag-%")).delete(synchronize_session=False)
    db.query(models.User).filter(
        models.User.user_id.like("t-ag-%")).delete(synchronize_session=False)
    db.commit()


def test_seed_groups_created_once(client):
    db = models.SessionLocal()
    try:
        names = {g.name for g in db.query(models.AccessGroup).all()}
        assert {"전사", "경영진", "경영전략실", "자산관리", "정산재무", "사업운영", "시스템관리"} <= names
        default = db.query(models.AccessGroup).filter_by(is_default=True).all()
        assert len(default) == 1 and default[0].name == "전사"
        # 전사 = 전 메뉴
        cnt = db.query(models.GroupMenu).filter_by(group_id=default[0].group_id).count()
        assert cnt == len(MENU_KEYS)
        # 재시드 멱등 — 비어있지 않으면 건너뜀(관리자 편집 보존)
        before = db.query(models.AccessGroup).count()
        main.seed_access_groups()
        assert db.query(models.AccessGroup).count() == before
    finally:
        db.close()


def test_unassigned_user_inherits_default_group(client):
    """그룹 미배정 → 전사(기본) 암묵 소속: 전 메뉴 + implicit 표시(회귀 0 핵심)."""
    db = models.SessionLocal()
    try:
        _cleanup(db)
        u = models.User(user_id="t-ag-staff", email="t-ag-staff@hooxi.kr",
                        role="STAFF", status="ACTIVE")
        db.add(u)
        db.commit()
        acc = resolve_user_access(db, u)
        assert acc["allowed_menus"] == list(MENU_KEYS)
        assert acc["groups"] and acc["groups"][0]["name"] == "전사"
        assert acc["groups"][0]["implicit"] is True
        assert acc["home_path"] == "/dashboard"
    finally:
        _cleanup(db)
        db.close()


def test_assigned_groups_union_and_home(client):
    """명시 배정: 합집합 메뉴 + 단일 그룹이면 그 그룹 홈, 복수면 /dashboard."""
    db = models.SessionLocal()
    try:
        _cleanup(db)
        u = models.User(user_id="t-ag-user", email="t-ag-user@hooxi.kr",
                        role="STAFF", status="ACTIVE")
        db.add(u)
        db.commit()
        g_asset = db.query(models.AccessGroup).filter_by(name="자산관리").first()
        g_fin = db.query(models.AccessGroup).filter_by(name="정산재무").first()
        db.add(models.UserGroup(user_id=u.user_id, group_id=g_asset.group_id))
        db.commit()
        acc1 = resolve_user_access(db, u)
        assert "/assets" in acc1["allowed_menus"]
        assert "/settlements" not in acc1["allowed_menus"]  # 자산관리엔 정산 없음
        assert acc1["home_path"] == "/assets"
        assert acc1["groups"][0]["implicit"] is False
        # 겸직(N:M) — 합집합 + 홈은 중립(/dashboard)
        db.add(models.UserGroup(user_id=u.user_id, group_id=g_fin.group_id))
        db.commit()
        acc2 = resolve_user_access(db, u)
        assert "/assets" in acc2["allowed_menus"] and "/settlements" in acc2["allowed_menus"]
        assert acc2["home_path"] == "/dashboard"
    finally:
        _cleanup(db)
        db.close()


def test_admin_bypass_all_menus(client):
    """ADMIN은 그룹 배정과 무관하게 전 메뉴(락아웃 방지)."""
    db = models.SessionLocal()
    try:
        _cleanup(db)
        u = models.User(user_id="t-ag-admin", email="t-ag-admin@hooxi.kr",
                        role="ADMIN", status="ACTIVE")
        db.add(u)
        db.commit()
        g = db.query(models.AccessGroup).filter_by(name="시스템관리").first()
        db.add(models.UserGroup(user_id=u.user_id, group_id=g.group_id))
        db.commit()
        acc = resolve_user_access(db, u)
        assert acc["allowed_menus"] == list(MENU_KEYS)  # 좁은 그룹이어도 전체
    finally:
        _cleanup(db)
        db.close()


def test_users_me_includes_access_fields(client, admin_headers):
    r = client.get("/api/v1/users/me", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "groups" in body and "allowed_menus" in body and "home_path" in body
    assert body["allowed_menus"]  # ADMIN → 전체
    assert body["home_path"].startswith("/")
