"""전화번호 정규화·고객사 대조 — 카카오 연락처 승인 보조(전화 기반 후보 제안).

카카오 채널로 들어온 가입자의 전화번호를 고객사 연락처(주담당·대표 전화)와 대조해
'일치 후보 고객사'를 관리자에게 제안한다. 확정(매핑·승인)은 사람이 한다 — CR-3 유지.
자동 승인 아님(제안은 UI 보조).
"""

import re
from typing import Dict, List, Tuple

from models import Client

# (Client 전화 컬럼, 사람이 읽는 라벨)
_CLIENT_PHONE_FIELDS = (
    ("main_contact_phone", "주 담당 전화"),
    ("ceo_contact_phone", "대표 전화"),
)


def normalize_phone(raw) -> str:
    """숫자만 남긴 정규화. 국제표기 +82 → 0 (예: '+82 10-1234-5678' → '01012345678')."""
    digits = re.sub(r"\D", "", str(raw or "").strip())
    if digits.startswith("82"):
        digits = "0" + digits[2:]
    return digits


def client_phone_index(db) -> Dict[str, List[Tuple[str, str, str]]]:
    """정규화 전화 → [(client_id, company_name, 매칭 필드 라벨)] 인덱스 (1쿼리).

    유효 자릿수(9+)인 번호만 색인 — 빈값·부분값은 오매칭 방지 위해 제외.
    """
    idx: Dict[str, List[Tuple[str, str, str]]] = {}
    rows = db.query(
        Client.client_id,
        Client.company_name,
        Client.main_contact_phone,
        Client.ceo_contact_phone,
    ).all()
    for cid, name, main_p, ceo_p in rows:
        for value, label in ((main_p, "주 담당 전화"), (ceo_p, "대표 전화")):
            key = normalize_phone(value)
            if len(key) < 9:
                continue
            idx.setdefault(key, []).append((cid, name or "", label))
    return idx


def suggest_clients(index: Dict[str, List[Tuple[str, str, str]]], phone) -> List[dict]:
    """전화 → 후보 고객사 목록. 동일 client 중복 제거(첫 매칭 필드 라벨 유지)."""
    key = normalize_phone(phone)
    if len(key) < 9:
        return []
    seen: Dict[str, dict] = {}
    for cid, name, label in index.get(key, []):
        if cid not in seen:
            seen[cid] = {"client_id": cid, "company_name": name, "matched_field": label}
    return list(seen.values())
