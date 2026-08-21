"""매출단가 시세 마스터(effective-dated, P0-2 증분2) — 유효일자 기반 시세 이력.

현재 시세 = 유효일자 ≤ 오늘 중 최신 단가. 미래 유효일자는 제외한다. 매출단가는 내부
재무정보라 조회도 내부 인증만 허용(외부역할 자동 403). 등록은 master.write + 감사 적재.
실현매출·회계는 미접촉(과거 불변) — 이 모듈은 참조성 마스터만 검증한다.
"""

import models
from services.market_rate import current_market_rate

API = "/api/v1"
RATES = API + "/market-rates"


def _ensure_external_user(user_id, email, role):
    db = models.SessionLocal()
    try:
        u = db.get(models.User, user_id)
        if u is None:
            u = models.User(user_id=user_id, email=email, name=email.split("@")[0])
            db.add(u)
        u.role = role
        u.status = "ACTIVE"
        db.commit()
    finally:
        db.close()


def _login(client, email):
    # dev-login은 내부 전용(외부는 매직링크 전용) — 테스트 토큰은 직접 발급
    from auth import create_access_token

    db = models.SessionLocal()
    try:
        u = db.query(models.User).filter(models.User.email == email).first()
        assert u is not None, email
        return {"Authorization": "Bearer {0}".format(create_access_token(u))}
    finally:
        db.close()


def test_current_rate_is_latest_past(client, admin_headers):
    # 과거 두 날짜 등록 → 최신(2026-06-01=14000)이 현재 시세
    assert client.post(RATES, headers=admin_headers, json={"effective_date": "2026-01-01", "unit_price": 13000}).status_code == 201
    assert client.post(RATES, headers=admin_headers, json={"effective_date": "2026-06-01", "unit_price": 14000}).status_code == 201

    r = client.get(RATES + "/current", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body is not None
    assert body["unit_price"] == 14000
    assert body["effective_date"] == "2026-06-01"


def test_future_effective_date_excluded(client, admin_headers):
    # 미래 유효일자는 현재 시세에서 제외 — 과거 최신(14000) 유지
    assert client.post(RATES, headers=admin_headers, json={"effective_date": "2099-01-01", "unit_price": 99999}).status_code == 201

    r = client.get(RATES + "/current", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["unit_price"] == 14000


def test_resolver_helper_matches(client, admin_headers):
    # current_market_rate 리졸버(증분3 재고평가 재사용)도 동일 결과
    db = models.SessionLocal()
    try:
        assert float(current_market_rate(db)) == 14000
    finally:
        db.close()


def test_list_desc_order(client, admin_headers):
    r = client.get(RATES, headers=admin_headers)
    assert r.status_code == 200, r.text
    dates = [row["effective_date"] for row in r.json()]
    assert dates == sorted(dates, reverse=True)


def test_negative_price_422(client, admin_headers):
    r = client.post(RATES, headers=admin_headers, json={"effective_date": "2026-07-01", "unit_price": -1})
    assert r.status_code == 422


def test_staff_can_write(client, staff_headers):
    # master.write는 STAFF 포함 — 등록 가능
    r = client.post(RATES, headers=staff_headers, json={"effective_date": "2026-05-01", "unit_price": 13500})
    assert r.status_code == 201, r.text


def test_external_role_blocked(client):
    _ensure_external_user("u-mr-partner", "mr-partner@carrier.example", "PARTNER")
    headers = _login(client, "mr-partner@carrier.example")
    # 조회·현재시세·등록 모두 외부역할 자동 차단(403)
    assert client.get(RATES, headers=headers).status_code == 403
    assert client.get(RATES + "/current", headers=headers).status_code == 403
    assert client.post(RATES, headers=headers, json={"effective_date": "2026-08-01", "unit_price": 15000}).status_code == 403


def test_unauthenticated_blocked(client):
    assert client.get(RATES).status_code == 401
    assert client.post(RATES, json={"effective_date": "2026-08-01", "unit_price": 15000}).status_code == 401


def test_audit_logged_on_create(client, admin_headers):
    r = client.post(RATES, headers=admin_headers, json={"effective_date": "2026-04-01", "unit_price": 12345, "note": "감사확인"})
    assert r.status_code == 201, r.text
    rate_id = r.json()["rate_id"]

    db = models.SessionLocal()
    try:
        logs = (
            db.query(models.AuditLog)
            .filter(
                models.AuditLog.action == "MARKET_RATE_CREATE",
                models.AuditLog.target_id == rate_id,
            )
            .all()
        )
        assert len(logs) == 1
        assert logs[0].target_type == "MARKET_RATE"
        assert logs[0].new_value == "12345.0"
    finally:
        db.close()
