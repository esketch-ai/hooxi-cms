"""카카오 승인 보조 — 전화번호 자동 수집 + 고객사 대조 후보 제안(CR-3 승인은 유지).

웹훅이 전화를 저장하고, 승인 대기 응답에 전화 일치 '후보 고객사'가 제안되는지 검증.
자동 승인은 없다(사람이 확정). services/phone_match 정규화·대조 단위 포함.
"""

import pytest

import models
from services import phone_match

API = "/api/v1"
WEBHOOK_SECRET = "test-hook-secret"


def _login(client, email):
    resp = client.post(API + "/auth/dev-login", json={"email": email})
    assert resp.status_code == 200, resp.text
    return {"Authorization": "Bearer {0}".format(resp.json()["access_token"])}


@pytest.fixture(scope="module")
def manager_headers(client):
    return _login(client, "manager@hooxipartners.com")


@pytest.fixture(autouse=True)
def _webhook_secret(monkeypatch):
    monkeypatch.setenv("KAKAO_WEBHOOK_SECRET", WEBHOOK_SECRET)


def _payload(user_key, utterance, phone=None):
    props = {"nickname": "테스터"}
    if phone is not None:
        props["phone"] = phone
    return {
        "userRequest": {
            "user": {"id": user_key, "properties": props},
            "utterance": utterance,
            "block": {"id": "fallback", "name": "폴백"},
        },
        "bot": {"id": "b", "name": "hooxi-bot"},
        "action": {"params": {}, "clientExtra": {}},
    }


def _webhook(client, user_key, utterance, phone=None):
    return client.post(
        API + "/kakao/webhook", params={"secret": WEBHOOK_SECRET},
        json=_payload(user_key, utterance, phone),
    )


# ── 단위: 정규화·대조 ───────────────────────────────────────────────
def test_normalize_phone():
    assert phone_match.normalize_phone("010-1234-5678") == "01012345678"
    assert phone_match.normalize_phone("+82 10-1234-5678") == "01012345678"
    assert phone_match.normalize_phone("  02)555-1234 ") == "025551234"
    assert phone_match.normalize_phone(None) == ""


def test_index_and_suggest(client):
    db = models.SessionLocal()
    try:
        db.query(models.Client).filter(
            models.Client.company_name.in_(["전화매칭운수", "무번호운수"])
        ).delete(synchronize_session=False)
        db.add(models.Client(
            client_type="TRANSPORT", company_name="전화매칭운수",
            main_contact_phone="010-9999-0001",
        ))
        db.add(models.Client(client_type="TRANSPORT", company_name="무번호운수"))
        db.commit()
        idx = phone_match.client_phone_index(db)
        hits = phone_match.suggest_clients(idx, "+82 10-9999-0001")
        assert len(hits) == 1
        assert hits[0]["company_name"] == "전화매칭운수"
        assert hits[0]["matched_field"] == "주 담당 전화"
        # 부분/미일치 번호는 후보 없음
        assert phone_match.suggest_clients(idx, "010-0000-0000") == []
        assert phone_match.suggest_clients(idx, "123") == []
    finally:
        db.query(models.Client).filter(
            models.Client.company_name.in_(["전화매칭운수", "무번호운수"])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


# ── 통합: 웹훅 전화 저장 + 승인 대기 후보 제안 ──────────────────────
def test_webhook_stores_phone_and_suggests(client, manager_headers):
    db = models.SessionLocal()
    try:
        db.query(models.Client).filter(models.Client.company_name == "후보제안운수").delete(
            synchronize_session=False
        )
        db.add(models.Client(
            client_type="TRANSPORT", company_name="후보제안운수",
            main_contact_phone="010-7777-1234",
        ))
        db.query(models.KakaoContact).filter(
            models.KakaoContact.kakao_user_key == "phone-key-001"
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()

    # 첫 발화에 전화 동의 정보 포함 → PENDING + phone 저장
    resp = _webhook(client, "phone-key-001", "상담 문의합니다", phone="+82 10-7777-1234")
    assert resp.status_code == 200, resp.text

    db = models.SessionLocal()
    try:
        c = db.query(models.KakaoContact).filter_by(kakao_user_key="phone-key-001").one()
        assert c.phone == "+82 10-7777-1234"
        assert c.status == "PENDING"
    finally:
        db.close()

    # 승인 대기 목록에 전화 일치 후보 제안이 실린다(확정은 사람 — 자동승인 아님)
    listed = client.get(
        API + "/kakao/contacts", headers=manager_headers, params={"status": "PENDING"}
    ).json()
    row = next(i for i in listed["items"] if i["kakao_user_key"] == "phone-key-001")
    assert row["status"] == "PENDING"  # 자동 승인되지 않음
    names = [s["company_name"] for s in row["suggested_clients"]]
    assert "후보제안운수" in names

    db = models.SessionLocal()
    try:
        db.query(models.KakaoContact).filter_by(kakao_user_key="phone-key-001").delete(
            synchronize_session=False
        )
        db.query(models.Client).filter_by(company_name="후보제안운수").delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()
