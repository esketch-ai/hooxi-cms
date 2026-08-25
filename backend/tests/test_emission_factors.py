"""배출계수(EF) 마스터 — 등록·이력·연료별 현재값·권한(M4)."""

from datetime import date

import models

API = "/api/v1/emission-factors"


def _login(client, email):
    r = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer {0}".format(r.json()["access_token"])}


def test_seed_current_and_history(client, staff_headers):
    # 시드된 3종(경유/CNG/전력) 현재값 조회
    cur = client.get(API + "/current", headers=staff_headers).json()
    fuels = {c["fuel_type"] for c in cur}
    assert {"경유", "CNG", "전력"}.issubset(fuels)

    # 전력 EF 갱신 등록(더 최신 유효일자) → current가 새 값
    r = client.post(API, headers=staff_headers, json={
        "fuel_type": "전력", "ef_value": 0.4567, "unit": "kgCO2/kWh",
        "effective_date": "2025-01-01", "note": "갱신",
    })
    assert r.status_code == 201, r.text
    cur2 = client.get(API + "/current", headers=staff_headers).json()
    elec = next(c for c in cur2 if c["fuel_type"] == "전력")
    assert abs(elec["ef_value"] - 0.4567) < 1e-9
    # 이력엔 옛 값도 남는다
    hist = client.get(API, headers=staff_headers).json()
    assert sum(1 for h in hist if h["fuel_type"] == "전력") >= 2


def test_create_requires_write(client):
    # OBSERVER(쓰기 권한 없음) 사용자 생성 후 등록 시도 → 403
    db = models.SessionLocal()
    try:
        if not db.query(models.User).filter_by(email="ef-observer@hooxipartners.com").first():
            db.add(models.User(
                user_id="u-ef-obs", email="ef-observer@hooxipartners.com",
                name="관찰자", role="OBSERVER", status="ACTIVE",
            ))
            db.commit()
    finally:
        db.close()
    obs = _login(client, "ef-observer@hooxipartners.com")
    r = client.post(API, headers=obs, json={
        "fuel_type": "경유", "ef_value": 2.7, "effective_date": "2026-01-01",
    })
    assert r.status_code == 403


def test_requires_auth(client):
    assert client.get(API).status_code == 401
