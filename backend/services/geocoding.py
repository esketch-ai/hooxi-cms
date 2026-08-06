"""주소 → 좌표(위·경도) 지오코딩 — 카카오 로컬 REST API (SCR-09 관제 지도).

- 키는 integration_config.resolve("KAKAO_REST_API_KEY")로 해석(DB 저장값 우선, env 폴백).
  키 미설정이면 지오코딩 비활성 — 항상 None을 반환해 고객사 저장/일괄처리를 막지 않는다.
- 전체 주소(address) 우선, 없거나 실패하면 지역(region)으로 폴백해 근사 좌표라도 채운다.
- 카카오 응답의 x=경도(lng), y=위도(lat). 모든 예외는 삼켜 None으로(베스트에포트).
"""

from typing import Optional, Tuple

import httpx

from services.integration_config import resolve

_ADDRESS_URL = "https://dapi.kakao.com/v2/local/search/address.json"
_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
_TIMEOUT = 5.0


def is_configured() -> bool:
    """카카오 REST 키가 설정돼 지오코딩이 가능한지."""
    return bool(resolve("KAKAO_REST_API_KEY"))


def _query(url: str, key: str, query: str) -> Optional[Tuple[float, float]]:
    """카카오 로컬 검색 1건 → (lat, lng). 결과 없음·오류 시 None."""
    try:
        resp = httpx.get(
            url,
            params={"query": query, "size": 1},
            headers={"Authorization": "KakaoAK {0}".format(key)},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        docs = resp.json().get("documents") or []
        if not docs:
            return None
        doc = docs[0]
        return float(doc["y"]), float(doc["x"])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


def geocode(
    address: Optional[str], region: Optional[str] = None
) -> Optional[Tuple[float, float]]:
    """주소(우선)·지역(폴백)을 위·경도로 변환. 실패/미설정 시 None.

    반환: (lat, lng) — 카카오 응답의 y=위도, x=경도.
    """
    key = resolve("KAKAO_REST_API_KEY")
    if not key:
        return None
    address = (address or "").strip()
    region = (region or "").strip()

    # 1) 전체 주소 정밀 지오코딩 (주소검색 → 실패 시 키워드검색)
    if address:
        hit = _query(_ADDRESS_URL, key, address) or _query(_KEYWORD_URL, key, address)
        if hit:
            return hit
    # 2) 지역(시/도)만으로 근사 좌표 폴백
    if region:
        return _query(_KEYWORD_URL, key, region) or _query(_ADDRESS_URL, key, region)
    return None
