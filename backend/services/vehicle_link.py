"""차량 정규 링크 백필(데이터계층 정합 3) — 파편 모델을 보유차량 원장(ClientVehicle)에 연결.

ReductionRegistry·VehicleCalcInput은 vehicle_no 문자열로만 차량을 참조한다(비유일 — 내연·전기
공존). 차대번호(VIN=ClientVehicle.chassis_no)를 1순위 키로, 없으면 (차량번호+EV여부)로 보유차량에
매칭해 client_vehicle_id를 채운다. VIN 매칭은 무모호, 폴백은 EV/ICE로 disambiguate.
읽기 전용 조립이 아니라 additive 백필(멱등 — 이미 링크된 건 건너뜀).
"""

from collections import defaultdict
from typing import Dict, List, Optional

from models import ClientVehicle, ReductionRegistry, VehicleCalcInput

_EV_FUEL = {"EV", "전기", "전기차", "ELECTRIC"}


def _is_ev(fuel) -> bool:
    return str(fuel or "").strip().upper() in _EV_FUEL or "전기" in str(fuel or "")


def _norm(s) -> str:
    return str(s or "").strip()


def _build_index(db):
    """ClientVehicle 인덱스 — VIN(chassis_no) 단건 + (차량번호, EV여부) 후보목록."""
    by_vin: Dict[str, str] = {}
    by_vno_ev: Dict[tuple, List[str]] = defaultdict(list)
    for c in db.query(ClientVehicle.vehicle_id, ClientVehicle.vehicle_no,
                      ClientVehicle.chassis_no, ClientVehicle.fuel).all():
        if c.chassis_no:
            by_vin.setdefault(_norm(c.chassis_no), c.vehicle_id)
        if c.vehicle_no:
            by_vno_ev[(_norm(c.vehicle_no), _is_ev(c.fuel))].append(c.vehicle_id)
    return by_vin, by_vno_ev


def _match(by_vin, by_vno_ev, vin: Optional[str], vehicle_no: Optional[str],
           is_ev: bool) -> tuple:
    """(vehicle_id, method) 또는 (None, 사유). VIN 1순위, (차량번호+EV) 2순위(유일할 때)."""
    v = _norm(vin)
    if v and v in by_vin:
        return by_vin[v], "VIN"
    cands = by_vno_ev.get((_norm(vehicle_no), is_ev), [])
    if len(cands) == 1:
        return cands[0], "NO+FUEL"
    if len(cands) > 1:
        return None, "AMBIGUOUS"
    return None, "UNMATCHED"


def link_vehicles(db, overwrite: bool = False) -> dict:
    """ReductionRegistry·VehicleCalcInput의 client_vehicle_id 백필. 멱등."""
    by_vin, by_vno_ev = _build_index(db)
    stats = {"registry": {"linked": 0, "vin": 0, "ambiguous": 0, "unmatched": 0, "skipped": 0},
             "calc_input": {"linked": 0, "vin": 0, "ambiguous": 0, "unmatched": 0, "skipped": 0}}

    for r in db.query(ReductionRegistry).all():
        if r.client_vehicle_id and not overwrite:
            stats["registry"]["skipped"] += 1
            continue
        vid, method = _match(by_vin, by_vno_ev, r.vin, r.vehicle_no, r.role == "PROJECT")
        if vid:
            r.client_vehicle_id = vid
            stats["registry"]["linked"] += 1
            if method == "VIN":
                stats["registry"]["vin"] += 1
        elif method == "AMBIGUOUS":
            stats["registry"]["ambiguous"] += 1
        else:
            stats["registry"]["unmatched"] += 1

    for ci in db.query(VehicleCalcInput).all():
        if ci.client_vehicle_id and not overwrite:
            stats["calc_input"]["skipped"] += 1
            continue
        # 산정 입력은 전기 참여차량 관점 — project_vin(EV) 우선, EV 차량으로 매칭
        vid, method = _match(by_vin, by_vno_ev, ci.project_vin, ci.vehicle_no, True)
        if vid:
            ci.client_vehicle_id = vid
            stats["calc_input"]["linked"] += 1
            if method == "VIN":
                stats["calc_input"]["vin"] += 1
        elif method == "AMBIGUOUS":
            stats["calc_input"]["ambiguous"] += 1
        else:
            stats["calc_input"]["unmatched"] += 1

    return stats
