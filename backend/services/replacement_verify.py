"""대체도입 자동 검증(D4) — 청사진 4장 검증 룰을 레지스트리 데이터에 적용.

대체도입은 같은 차량번호로 BASELINE(화석연료)↔PROJECT(전기버스)가 존재해야 하며:
  ① 베이스라인(화석연료) 존재  ② VIN 상이(old≠new)
  ③ 기존 연료 ∈ (경유/CNG)     ④ 신규 연료 = 전기
폐차일 ≤ 도입일(폐차증명)은 문서(PDF) 기반이라 구조 데이터 확보 시 추가(현재 미검증 표시).
신규도입은 베이스라인이 선정차량이라 이 룰 대상 아님(별도).
"""

from typing import Dict, List

from models import ReductionRegistry

_ICE_FUELS = {"경유", "CNG"}


def verify_replacements(db) -> List[dict]:
    """PROJECT(대체도입) 차량별 검증 결과 목록. BASELINE을 차량번호로 페어링."""
    baselines: Dict[str, ReductionRegistry] = {}
    for b in db.query(ReductionRegistry).filter(ReductionRegistry.role == "BASELINE").all():
        if b.vehicle_no:
            baselines.setdefault(b.vehicle_no, b)

    results = []
    projects = (
        db.query(ReductionRegistry)
        .filter(ReductionRegistry.role == "PROJECT",
                ReductionRegistry.introduction_type == "대체도입")
        .all()
    )
    for p in projects:
        b = baselines.get(p.vehicle_no)
        reasons = []
        if b is None:
            reasons.append("베이스라인 없음")
        else:
            if b.vin and p.vin and b.vin == p.vin:
                reasons.append("VIN 동일")
            if b.fuel and b.fuel not in _ICE_FUELS:
                reasons.append("기존 연료 비대상({0})".format(b.fuel))
            if p.fuel and p.fuel != "전기":
                reasons.append("신규 비전기({0})".format(p.fuel))
        status = "PASS" if not reasons else "FAIL"
        results.append({
            "vehicle_no": p.vehicle_no,
            "operator_name": p.operator_name,
            "client_id": p.client_id,
            "region": p.region,
            "old_vin": b.vin if b else None,
            "new_vin": p.vin,
            "old_fuel": b.fuel if b else None,
            "status": status,
            "reasons": reasons,
        })
    return results


def verification_summary(results: List[dict]) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    return {"total": total, "passed": passed, "failed": total - passed}
