"""주소→좌표 지오코딩(카카오 로컬) + 좌표 백필 엔드포인트 (SCR-09 지도)."""

import models
from services import geocoding

API = "/api/v1"


class _FakeResp:
    def __init__(self, docs):
        self._docs = docs

    def raise_for_status(self):
        pass

    def json(self):
        return {"documents": self._docs}


def _seed_client(region="서울", address="서울특별시 중구 세종대로 110"):
    db = models.SessionLocal()
    try:
        c = models.Client(
            client_type="TRANSPORT",
            company_name="지오코딩운수",
            region=region,
            address=address,
        )
        db.add(c)
        db.commit()
        return c.client_id
    finally:
        db.close()


def test_geocode_service_no_key(client, monkeypatch):
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    assert geocoding.geocode("서울특별시 중구 세종대로 110", "서울") is None
    assert geocoding.is_configured() is False


def test_geocode_service_address_then_region_fallback(client, monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "k")

    def fake_get(url, params=None, headers=None, timeout=None):
        # 주소 질의는 결과 없음, 지역(서울) 질의는 히트 → 폴백 경로 검증
        if params["query"] == "없는주소":
            return _FakeResp([])
        return _FakeResp([{"x": "127.0", "y": "37.0"}])

    monkeypatch.setattr(geocoding.httpx, "get", fake_get)
    assert geocoding.geocode("없는주소", "서울") == (37.0, 127.0)


def test_geocode_missing_requires_key(client, admin_headers, monkeypatch):
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    resp = client.post(API + "/clients/geocode-missing", headers=admin_headers)
    assert resp.status_code == 503


def test_geocode_missing_fills_coords(client, admin_headers, monkeypatch):
    cid = _seed_client()
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-key")

    def fake_get(url, params=None, headers=None, timeout=None):
        return _FakeResp([{"x": "126.9784", "y": "37.5665"}])

    monkeypatch.setattr(geocoding.httpx, "get", fake_get)
    resp = client.post(API + "/clients/geocode-missing", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["updated"] >= 1

    db = models.SessionLocal()
    try:
        c = db.get(models.Client, cid)
        assert c.lat is not None and c.lng is not None
        assert abs(float(c.lat) - 37.5665) < 1e-4
        assert abs(float(c.lng) - 126.9784) < 1e-4
    finally:
        db.close()
