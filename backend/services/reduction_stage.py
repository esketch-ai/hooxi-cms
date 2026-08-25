"""3단계 감축량 스냅샷·비교(D6 P5) — 예상/모니터링/최종.

동일 방법론(reduction_calc)을 시점·데이터 품질만 바꿔 3회 실행한 결과를 단계별로 동결·비교.
- save_stage: 현재 산정 입력(VehicleCalcInput)으로 전 차량 계산 → 지정 단계 스냅샷 upsert.
  (예: 모니터링 로그 집계로 project를 갱신한 뒤 'MONITORING' 저장하면 예상과 나란히 비교)
- compare: 차량별 예상↔모니터링↔최종 + 달성률(모니터링/예상, 최종/예상).
"""

from typing import Dict, List, Optional

from models import ReductionStage, VehicleCalcInput
from services import reduction_calc as rc
from services.reduction_run import _ratio_index

STAGES = ("PLANNED", "MONITORING", "FINAL")
_STAGE_KEY = {"PLANNED": "planned", "MONITORING": "monitoring", "FINAL": "final"}
STAGE_LABEL = {"PLANNED": "예상", "MONITORING": "모니터링", "FINAL": "최종"}

_SNAP_FIELDS = ("operator_name", "region", "fuel", "usage_year", "project_emission",
                "total_reduction", "adjusted_total", "project_distance", "project_kwh",
                "baseline_distance", "baseline_fuel", "private_ratio")


def save_stage(db, stage: str, region: Optional[str] = None,
               note: Optional[str] = None) -> dict:
    """산정 입력 전건 계산 → 지정 단계 스냅샷 upsert(차량·단계). 계산 가능 건만."""
    if stage not in STAGES:
        raise ValueError("알 수 없는 단계: {0}".format(stage))
    consts = rc.load_constants(db)
    ratios = _ratio_index(db)
    q = db.query(VehicleCalcInput)
    if region:
        q = q.filter(VehicleCalcInput.region == region)

    saved = skipped = 0
    for v in q.all():
        if None in (v.baseline_distance, v.baseline_fuel, v.project_distance,
                    v.project_kwh, v.ev_reg_year) or not v.fuel:
            skipped += 1
            continue
        ratio = float(v.private_ratio) if v.private_ratio is not None else ratios.get(v.vehicle_no)
        res = rc.compute_vehicle(
            fuel=v.fuel, baseline_distance=float(v.baseline_distance),
            baseline_fuel=float(v.baseline_fuel), project_distance=float(v.project_distance),
            project_kwh=float(v.project_kwh), ev_reg_year=int(v.ev_reg_year),
            private_ratio=ratio, consts=consts,
        )
        payload = {
            "operator_name": v.operator_name, "region": v.region, "fuel": v.fuel,
            "usage_year": res["usage_year"], "project_emission": res["project_emission"],
            "total_reduction": res["total_reduction"], "adjusted_total": res.get("adjusted_total"),
            "project_distance": float(v.project_distance), "project_kwh": float(v.project_kwh),
            "baseline_distance": float(v.baseline_distance), "baseline_fuel": float(v.baseline_fuel),
            "private_ratio": ratio, "note": note,
        }
        existing = db.query(ReductionStage).filter(
            ReductionStage.vehicle_no == v.vehicle_no, ReductionStage.stage == stage).first()
        if existing:
            for k, val in payload.items():
                setattr(existing, k, val)
        else:
            db.add(ReductionStage(vehicle_no=v.vehicle_no, stage=stage, **payload))
        saved += 1
    return {"stage": stage, "saved": saved, "skipped": skipped}


def _rate(num: Optional[float], den: Optional[float]) -> Optional[float]:
    if num is None or not den:
        return None
    return round(num / den * 100, 1)


def compare(db, region: Optional[str] = None) -> dict:
    """차량별 예상↔모니터링↔최종 + 달성률. 저장된 스냅샷만 대상."""
    q = db.query(ReductionStage)
    if region:
        q = q.filter(ReductionStage.region == region)

    by: Dict[str, dict] = {}
    for r in q.all():
        slot = by.setdefault(r.vehicle_no, {
            "vehicle_no": r.vehicle_no, "operator_name": r.operator_name, "region": r.region,
            "planned": None, "monitoring": None, "final": None})
        if r.operator_name and not slot["operator_name"]:
            slot["operator_name"] = r.operator_name
        val = float(r.total_reduction) if r.total_reduction is not None else None
        slot[_STAGE_KEY[r.stage]] = val

    items: List[dict] = []
    totals = {"planned": 0.0, "monitoring": 0.0, "final": 0.0}
    for slot in sorted(by.values(), key=lambda s: (s["region"] or "", s["vehicle_no"])):
        p, m, f = slot["planned"], slot["monitoring"], slot["final"]
        slot["ach_monitoring"] = _rate(m, p)
        slot["ach_final"] = _rate(f, p)
        for k in ("planned", "monitoring", "final"):
            if slot[k]:
                totals[k] += slot[k]
        items.append(slot)
    return {
        "items": items, "vehicle_count": len(items),
        "total_planned": round(totals["planned"], 3),
        "total_monitoring": round(totals["monitoring"], 3),
        "total_final": round(totals["final"], 3),
    }
