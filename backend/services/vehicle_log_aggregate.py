"""차량 월별 로그 → 연평균 집계·정리 뷰(D6, P1·P2).

- consolidate: 로그(차량×월×지표) → 차량×월 통합 표(담당자 취합본과 동일, 자동 생성).
- aggregate: 기간 Σ → 연평균 project_distance/kwh → VehicleCalcInput 사업(project) 측 채움.
  산식(산정 시트 관례): (Σ지표 / Σ운행일수) × 365. 운행일수 0/결여 → 집계 불가.
"""

from collections import defaultdict
from typing import Dict, List, Optional

from models import ReductionRegistry, VehicleCalcInput, VehicleMonthlyLog

# 출처 우선순위(작을수록 우선). 운행=eTAS 권위, 충전량은 INTEGRATED만 보유, BMS는 보조.
_SOURCE_PRIORITY = {"ETAS": 0, "INTEGRATED": 1, "BMS": 2}


def _f(v) -> Optional[float]:
    return float(v) if v is not None else None


def consolidate(db, region: Optional[str] = None, ym_from: Optional[str] = None,
                ym_to: Optional[str] = None, program_only: bool = False) -> dict:
    """로그를 차량×월 통합 표로 정리. program_only=레지스트리 차량만."""
    q = db.query(VehicleMonthlyLog)
    if region:
        q = q.filter(VehicleMonthlyLog.region == region)
    if ym_from:
        q = q.filter(VehicleMonthlyLog.year_month >= ym_from)
    if ym_to:
        q = q.filter(VehicleMonthlyLog.year_month <= ym_to)
    # 출처 우선순위로 정렬 → 지표는 first-write-wins(고우선 출처가 채움, 결정적)
    logs = sorted(q.all(), key=lambda l: _SOURCE_PRIORITY.get(l.source, 9))

    program = None
    if program_only:
        program = {r[0] for r in db.query(ReductionRegistry.vehicle_no).all() if r[0]}

    # 차량 → {월 → 지표}, 차량 → 운수사
    veh: Dict[str, dict] = defaultdict(lambda: {"months": {}, "operator_name": None})
    months = set()
    for lg in logs:
        if program is not None and lg.vehicle_no not in program:
            continue
        slot = veh[lg.vehicle_no]
        if lg.operator_name and not slot["operator_name"]:
            slot["operator_name"] = lg.operator_name
        m = slot["months"].setdefault(lg.year_month, {
            "operating_days": None, "distance_km": None, "charge_kwh": None})
        for k in ("operating_days", "distance_km", "charge_kwh"):
            val = getattr(lg, k)
            if val is not None and m[k] is None:  # 고우선 출처 우선(first-write-wins)
                m[k] = _f(val)
        months.add(lg.year_month)

    vehicles = []
    miss_run = miss_charge = 0
    for vno, slot in sorted(veh.items()):
        has_run = any(mv["distance_km"] is not None for mv in slot["months"].values())
        has_charge = any(mv["charge_kwh"] is not None for mv in slot["months"].values())
        if not has_run:
            miss_run += 1
        if not has_charge:
            miss_charge += 1
        vehicles.append({
            "vehicle_no": vno, "operator_name": slot["operator_name"],
            "months": slot["months"], "has_run": has_run, "has_charge": has_charge,
        })
    return {
        "months": sorted(months), "vehicles": vehicles,
        "vehicle_count": len(vehicles), "missing_run": miss_run,
        "missing_charge": miss_charge,
    }


def aggregate_to_calc(db, region: Optional[str] = None, ym_from: Optional[str] = None,
                      ym_to: Optional[str] = None, commit_project: bool = False) -> dict:
    """기간 Σ → 연평균(project). commit_project=True면 VehicleCalcInput 사업측 갱신."""
    con = consolidate(db, region=region, ym_from=ym_from, ym_to=ym_to, program_only=True)
    updated = created = insufficient = 0
    results = []
    for v in con["vehicles"]:
        sum_days = sum((m["operating_days"] or 0) for m in v["months"].values())
        sum_dist = sum((m["distance_km"] or 0) for m in v["months"].values())
        sum_kwh = sum((m["charge_kwh"] or 0) for m in v["months"].values())
        if sum_days <= 0 or sum_dist <= 0:
            insufficient += 1
            results.append({"vehicle_no": v["vehicle_no"], "status": "INSUFFICIENT",
                            "reason": "운행일수/거리 결여", "project_distance": None,
                            "project_kwh": None})
            continue
        proj_dist = round(sum_dist / sum_days * 365, 3)
        proj_kwh = round(sum_kwh / sum_days * 365, 3) if sum_kwh > 0 else None
        results.append({"vehicle_no": v["vehicle_no"], "status": "OK", "reason": None,
                        "project_distance": proj_dist, "project_kwh": proj_kwh,
                        "months_used": len(v["months"])})
        if commit_project:
            ci = db.query(VehicleCalcInput).filter(
                VehicleCalcInput.vehicle_no == v["vehicle_no"]).first()
            if ci:
                ci.project_distance = proj_dist
                if proj_kwh is not None:
                    ci.project_kwh = proj_kwh
                updated += 1
    return {
        "vehicle_count": con["vehicle_count"], "aggregated": len([r for r in results if r["status"] == "OK"]),
        "insufficient": insufficient, "updated": updated, "created": created,
        "results": results,
    }
