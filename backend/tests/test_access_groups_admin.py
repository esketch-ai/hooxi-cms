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


def test_dept_code_label_drives_group_name(client, admin_headers):
    """부서명은 공통코드(DEPT)에서 관리 — 라벨 변경이 그룹 표시명에 즉시 반영."""
    db = models.SessionLocal()
    try:
        _cleanup(db)
        # DEPT 코드 라벨 확인 후 그룹 목록의 표시명과 일치
        asset = db.query(models.Code).filter_by(category="DEPT", code="ASSET").first()
        assert asset is not None
        orig_label = asset.label
        groups = client.get("/api/v1/access-groups", headers=admin_headers).json()
        g = [x for x in groups if x.get("dept_code") == "ASSET"][0]
        assert g["name"] == orig_label
        # 라벨 변경(부서 개명) → 그룹 표시명 라이브 반영
        asset.label = "자산관리본부"
        db.commit()
        groups2 = client.get("/api/v1/access-groups", headers=admin_headers).json()
        g2 = [x for x in groups2 if x.get("dept_code") == "ASSET"][0]
        assert g2["name"] == "자산관리본부"
        # /users/me 그룹명도 라벨 반영
        u = models.User(user_id="t-ga-dept", email="t-ga-dept@hooxi.kr",
                        role="STAFF", status="ACTIVE")
        db.add(u)
        db.commit()
        client.put(f"/api/v1/access-groups/users/t-ga-dept", headers=admin_headers,
                   json={"group_ids": [g2["group_id"]]})
        from access_control import resolve_user_access
        acc = resolve_user_access(db, u)
        assert acc["groups"][0]["name"] == "자산관리본부"
        # 없는 부서 코드로 생성 → 422
        bad = client.post("/api/v1/access-groups", headers=admin_headers,
                          json={"name": "x", "dept_code": "NOPE", "menus": []})
        assert bad.status_code == 422
        # 원복
        asset.label = orig_label
        db.query(models.UserGroup).filter_by(user_id="t-ga-dept").delete(synchronize_session=False)
        db.query(models.User).filter_by(user_id="t-ga-dept").delete(synchronize_session=False)
        db.commit()
    finally:
        _cleanup(db)
        db.close()
