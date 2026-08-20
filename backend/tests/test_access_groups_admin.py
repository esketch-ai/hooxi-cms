"""접근 그룹 관리 API(G3) — CRUD·기본그룹 보호·배정·모드 스위치·권한."""

import models


def _cleanup(db):
    for name in ("TESTG신설", "TESTG개명"):
        g = db.query(models.AccessGroup).filter_by(name=name).first()
        if g:
            db.delete(g)
    db.query(models.User).filter(
        models.User.user_id.like("t-ga-%")).delete(synchronize_session=False)
    row = db.get(models.Config, "access_control_mode")
    if row:
        row.config_value = '"off"'
    db.commit()


def test_group_crud_and_default_protection(client, admin_headers):
    db = models.SessionLocal()
    try:
        _cleanup(db)
        # 생성
        r = client.post("/api/v1/access-groups", headers=admin_headers,
                        json={"name": "TESTG신설", "home_path": "/clients",
                              "menus": ["/clients", "/없는키", "/guide"]})
        assert r.status_code == 201, r.text
        g = r.json()
        assert g["menus"] == ["/clients", "/guide"]  # 정본에 없는 키 필터
        gid = g["group_id"]
        # 수정(개명 + 메뉴 교체)
        r2 = client.put(f"/api/v1/access-groups/{gid}", headers=admin_headers,
                        json={"name": "TESTG개명", "home_path": "/clients",
                              "menus": ["/documents"]})
        assert r2.status_code == 200 and r2.json()["menus"] == ["/documents"]
        # 목록에 노출
        names = [x["name"] for x in client.get("/api/v1/access-groups",
                                               headers=admin_headers).json()]
        assert "TESTG개명" in names and "전사" in names
        # 기본(전사) 그룹: 삭제 금지 + 메뉴 축소 금지
        default = [x for x in client.get("/api/v1/access-groups",
                                         headers=admin_headers).json() if x["is_default"]][0]
        rd = client.delete(f"/api/v1/access-groups/{default['group_id']}",
                           headers=admin_headers)
        assert rd.status_code == 422
        ru = client.put(f"/api/v1/access-groups/{default['group_id']}", headers=admin_headers,
                        json={"name": default["name"], "menus": ["/dashboard"]})
        assert ru.status_code == 200
        still = [x for x in client.get("/api/v1/access-groups",
                                       headers=admin_headers).json() if x["is_default"]][0]
        assert len(still["menus"]) > 1  # 축소 안 됨(전 메뉴 고정)
        # 삭제
        assert client.delete(f"/api/v1/access-groups/{gid}",
                             headers=admin_headers).status_code == 204
    finally:
        _cleanup(db)
        db.close()


def test_assign_user_groups_and_me(client, admin_headers):
    db = models.SessionLocal()
    try:
        _cleanup(db)
        u = models.User(user_id="t-ga-u1", email="t-ga-u1@hooxi.kr",
                        role="STAFF", status="ACTIVE")
        db.add(u)
        db.commit()
        g = db.query(models.AccessGroup).filter_by(name="자산관리").first()
        r = client.put(f"/api/v1/access-groups/users/t-ga-u1", headers=admin_headers,
                       json={"group_ids": [g.group_id]})
        assert r.status_code == 200 and r.json() == [g.group_id]
        # 빈 목록 → 미배정(전사 암묵)
        r2 = client.put(f"/api/v1/access-groups/users/t-ga-u1", headers=admin_headers,
                        json={"group_ids": []})
        assert r2.status_code == 200
        assert db.query(models.UserGroup).filter_by(user_id="t-ga-u1").count() == 0
    finally:
        _cleanup(db)
        db.close()


def test_mode_switch_and_meta(client, admin_headers, staff_headers):
    db = models.SessionLocal()
    try:
        _cleanup(db)
        meta = client.get("/api/v1/access-groups/meta", headers=admin_headers).json()
        assert meta["mode"] == "off" and "/dashboard" in meta["menu_keys"]
        r = client.put("/api/v1/access-groups/mode", headers=admin_headers,
                       json={"mode": "monitor"})
        assert r.status_code == 200 and r.json()["mode"] == "monitor"
        # 잘못된 모드
        assert client.put("/api/v1/access-groups/mode", headers=admin_headers,
                          json={"mode": "block"}).status_code == 422
        # /users/me에 access_mode 반영
        me = client.get("/api/v1/users/me", headers=admin_headers).json()
        assert me["access_mode"] == "monitor"
        # 비ADMIN은 관리 API 접근 불가
        assert client.get("/api/v1/access-groups", headers=staff_headers).status_code == 403
    finally:
        _cleanup(db)
        db.close()
