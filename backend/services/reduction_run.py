"""전 차량 감축량 계산 연결(D5) — 산정 입력 + 방법론 상수 + 민간비율 → 계산 엔진.

VehicleCalcInput(연평균 입력) × MethodologyConstant(상수) × EvFinance(민간비율) →
services.reduction_calc.compute_vehicle. 민간비율은 입력값 우선, 없으면 재무마스터 조인.
결과는 온-더-플라이(재계산 안전) — 3단계 stage 저장은 상위 라이프사이클에서.
"""

from typing import Dict, List, Optional

from models import EvFinance, VehicleCalcInput
from services import reduction_calc as rc


def _ratio_index(db) -> Dict[str, float]:
    idx: Dict[str, float] = {}
    for f in db.query(EvFinance.vehicle_no, EvFinance.private_ratio).all():
        if f.vehicle_no and f.private_ratio is not None:
            idx.setdefault(f.vehicle_no, float(f.private_ratio))
    return idx


def run_all(db, region: Optional[str] = None) -> dict:
    """산정 입력 전건 계산 — 차량별 결과 + 사업/운수사 합계 요약."""
    consts = rc.load_constants(db)
    ratios = _ratio_index(db)
    q = db.query(VehicleCalcInput)
    if region:
        q = q.filter(VehicleCalcInput.region == region)
    inputs = q.all()

    results = []
    computed = skipped = 0
    total_reduction = total_adjusted = 0.0
    for v in inputs:
        # 필수 입력 결여 시 스킵(계산 불가)
        if None in (v.baseline_distance, v.baseline_fuel, v.project_distance,
                    v.project_kwh, v.ev_reg_year) or not v.fuel:
            skipped += 1
            results.append({
                "vehicle_no": v.vehicle_no, "operator_name": v.operator_name,
                "region": v.region, "status": "SKIP", "reason": "입력 결여",
                "total_reduction": None, "adjusted_total": None,
            })
            continue
        ratio = float(v.private_ratio) if v.private_ratio is not None else ratios.get(v.vehicle_no)
        res = rc.compute_vehicle(
            fuel=v.fuel,
            baseline_distance=float(v.baseline_distance),
            baseline_fuel=float(v.baseline_fuel),
            project_distance=float(v.project_distance),
            project_kwh=float(v.project_kwh),
            ev_reg_year=int(v.ev_reg_year),
            private_ratio=ratio,
            consts=consts,
        )
        computed += 1
        total_reduction += res["total_reduction"]
        adj = res.get("adjusted_total")
        if adj is not None:
            total_adjusted += adj
        results.append({
            "vehicle_no": v.vehicle_no, "operator_name": v.operator_name, "region": v.region,
            "status": "OK", "reason": None,
            "fuel": v.fuel, "usage_year": res["usage_year"],
            "project_emission": res["project_emission"],
            "total_reduction": res["total_reduction"],
            "private_ratio": ratio,
            "adjusted_total": res.get("adjusted_total"),
            "annual": [a["reduction"] for a in res["annual"]],
        })
    return {
        "computed": computed,
        "skipped": skipped,
        "total": len(inputs),
        "total_reduction": round(total_reduction, 3),
        "total_adjusted": round(total_adjusted, 3),
        "results": results,
    }
