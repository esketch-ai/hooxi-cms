"""차량 통합 상세(dossier, 개편 P5) — 한 vehicle_no의 전 생애를 7개 모델에서 모아 조립.

파편화된 차량 정체성(보유·참여·레지스트리·산정·로그·3단계·재무)을 차량번호 하나로 묶어
한 화면에 제공한다. 읽기 전용 조회 조립(재계산·저장 없음). vehicle_no는 유일하지 않으므로
(내연·전기 공존) 매칭되는 행을 모두 담는다.
"""

from typing import Optional

from models import (
    ClientVehicle, EvFinance, Project, ProjectVehicle, ReductionRegistry,
    ReductionStage, VehicleCalcInput, VehicleMonthlyLog,
)


def _f(v):
    return float(v) if v is not None else None


def get_dossier(db, vehicle_no: str) -> dict:
    """차량번호로 전 모델을 조회해 통합 상세 dict 조립."""
    vno = (vehicle_no or "").strip()

    # 1) 보유 차량(원장) — 내연·전기 복수 가능
    owned = [
        {"vehicle_id": c.vehicle_id, "client_id": c.client_id, "operator_name": c.operator_name,
         "region": c.region, "chassis_no": c.chassis_no, "model_name": c.model_name,
         "model_year": c.model_year, "vehicle_class": c.vehicle_class, "fuel": c.fuel,
         "seating_capacity": c.seating_capacity, "status": c.status}
        for c in db.query(ClientVehicle).filter(ClientVehicle.vehicle_no == vno).all()
    ]

    # 2) 감축 참여(사업별)
    participations = [
        {"project_id": r.project_id, "project_name": pname, "project_status": pstatus,
         "introduction_type": r.introduction_type, "total_reduction": _f(r.total_reduction),
         "monitoring_reduction": _f(r.monitoring_reduction),
         "effective_reduction": _f(r.effective_reduction), "final_reduction": _f(r.final_reduction),
         "expected_payout": _f(r.expected_payout),
         "private_invest_ratio": _f(r.private_invest_ratio)}
        for r, pname, pstatus in (
            db.query(ProjectVehicle, Project.project_name, Project.project_status)
            .join(Project, ProjectVehicle.project_id == Project.project_id)
            .filter(ProjectVehicle.vehicle_no == vno).all())
    ]

    # 3) 레지스트리(KISA) — 역할·VIN·도입구분
    registry = [
        {"role": r.role, "vin": r.vin, "introduction_type": r.introduction_type,
         "region": r.region}
        for r in db.query(ReductionRegistry).filter(ReductionRegistry.vehicle_no == vno).all()
    ]

    # 4) 산정 입력(연평균)
    ci = db.query(VehicleCalcInput).filter(VehicleCalcInput.vehicle_no == vno).first()
    calc_input = None
    if ci:
        calc_input = {
            "introduction_type": ci.introduction_type, "vin_status": ci.vin_status,
            "fuel": ci.fuel, "baseline_distance": _f(ci.baseline_distance),
            "baseline_fuel": _f(ci.baseline_fuel), "project_distance": _f(ci.project_distance),
            "project_kwh": _f(ci.project_kwh), "ev_reg_year": ci.ev_reg_year,
            "private_ratio": _f(ci.private_ratio)}

    # 5) 3단계 감축량 스냅샷
    stages = {}
    for s in db.query(ReductionStage).filter(ReductionStage.vehicle_no == vno).all():
        stages[s.stage] = {"total_reduction": _f(s.total_reduction),
                           "adjusted_total": _f(s.adjusted_total),
                           "project_distance": _f(s.project_distance),
                           "project_kwh": _f(s.project_kwh)}

    # 6) 월별 로그 요약(전량 대신 커버리지·합계)
    logs = db.query(VehicleMonthlyLog).filter(VehicleMonthlyLog.vehicle_no == vno).all()
    months = sorted({l.year_month for l in logs})
    log_summary = {
        "month_from": months[0] if months else None,
        "month_to": months[-1] if months else None,
        "month_count": len(months),
        "sources": sorted({l.source for l in logs}),
        "total_distance": round(sum(float(l.distance_km) for l in logs if l.distance_km is not None), 1),
        "total_charge": round(sum(float(l.charge_kwh) for l in logs if l.charge_kwh is not None), 1),
        "has_charge": any(l.charge_kwh is not None for l in logs),
    } if logs else None

    # 7) 재무(민간투자비율 근거)
    fin = db.query(EvFinance).filter(EvFinance.vehicle_no == vno).first()
    finance = None
    if fin:
        finance = {"vehicle_value": _f(fin.vehicle_value), "self_payment": _f(fin.self_payment),
                   "private_ratio": _f(fin.private_ratio), "public_ratio": _f(fin.public_ratio),
                   "ev_subsidy": _f(fin.ev_subsidy)}

    return {
        "vehicle_no": vno,
        "found": bool(owned or participations or registry or calc_input or stages or logs or finance),
        "owned": owned, "participations": participations, "registry": registry,
        "calc_input": calc_input, "stages": stages, "log_summary": log_summary,
        "finance": finance,
    }
