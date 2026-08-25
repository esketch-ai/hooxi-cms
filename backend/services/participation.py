"""운수사 감축 참여 라이프사이클 — 참여상태 파생·요약(라이프사이클 P1·P2·P3).

보유 차량(ClientVehicle) × 참여 차량(ProjectVehicle) × 사업 상태(Project.project_status)로
참여 상태(기참여/참여중/미참여)를 **파생**(저장 안 함)하고, 운수사 한 화면용 요약+목록을 만든다.
- 기참여(COMPLETED): 소속 사업이 발급완료
- 참여중(ONGOING): 소속 사업이 기획~검증(발급 전)
- 미참여(NOT): 보유버스 중 어떤 참여에도 안 걸린 차량(향후 참여 후보)

3단계 감축량 정합(P2 강화) — **ProjectVehicle이 3단계 전부의 단일 정본**:
- **예상** = ProjectVehicle.total_reduction (계획 산정)
- **모니터링** = ProjectVehicle.monitoring_reduction (워크벤치서 단방향 커밋된 실측)
- **최종** = ProjectVehicle.effective_reduction (승인 후 파생, 발급완료 시)
reduction_stage는 워크벤치 분석 스냅샷일 뿐 정본 아님(divergence 위험 제거).
"""

from typing import Dict, List

from models import ClientVehicle, Project, ProjectVehicle

_COMPLETED_STATUS = {"발급완료"}
_EV_FUEL = {"EV", "전기", "전기차", "ELECTRIC"}


def _f(v):
    return float(v) if v is not None else None


def _rate(num, den):
    """달성률 % — num/den×100(소수1). 분모 0/None이면 None."""
    if num is None or not den:
        return None
    return round(num / den * 100, 1)


def _is_ev(fuel) -> bool:
    return str(fuel or "").strip().upper() in _EV_FUEL or "전기" in str(fuel or "")


def client_participation(db, client_id: str) -> dict:
    """운수사 감축 참여 요약 + 참여 차량 목록 + 미참여(후보) 목록."""
    pv_rows = (
        db.query(
            ProjectVehicle.vehicle_no, ProjectVehicle.introduction_type,
            ProjectVehicle.total_reduction, ProjectVehicle.monitoring_reduction,
            ProjectVehicle.effective_reduction,
            ProjectVehicle.expected_payout, ProjectVehicle.client_vehicle_id,
            Project.project_id, Project.project_name, Project.project_status,
        )
        .join(Project, ProjectVehicle.project_id == Project.project_id)
        .filter(ProjectVehicle.client_id == client_id)
        .all()
    )
    cvs = db.query(ClientVehicle).filter(ClientVehicle.client_id == client_id).all()

    linked_cv_ids = set()
    linked_vnos = set()
    participated: List[dict] = []
    expected_total = monitoring_total = final_total = 0.0
    for r in pv_rows:
        completed = r.project_status in _COMPLETED_STATUS
        state = "COMPLETED" if completed else "ONGOING"
        if r.client_vehicle_id:
            linked_cv_ids.add(r.client_vehicle_id)
        if r.vehicle_no:
            linked_vnos.add(r.vehicle_no)
        exp = _f(r.total_reduction)
        mon = _f(r.monitoring_reduction)
        fin = _f(r.effective_reduction) if completed else None
        if exp:
            expected_total += exp
        if mon:
            monitoring_total += mon
        if fin:
            final_total += fin
        participated.append({
            "vehicle_no": r.vehicle_no, "introduction_type": r.introduction_type,
            "participation_status": state, "project_id": r.project_id,
            "project_name": r.project_name, "project_status": r.project_status,
            "expected_reduction": exp, "monitoring_reduction": mon, "final_reduction": fin,
            "ach_monitoring": _rate(mon, exp), "ach_final": _rate(fin, exp),
            "expected_payout": _f(r.expected_payout),
        })

    # 상태별 distinct 차량(대체도입 등 한 차량 복수 이력 → 최선 상태로 집계)
    vno_state: Dict[str, str] = {}
    for p in participated:
        vno = p["vehicle_no"] or ""
        if vno_state.get(vno) != "COMPLETED":
            vno_state[vno] = p["participation_status"]

    not_participated: List[dict] = []
    owned = 0
    for cv in cvs:
        if cv.status == "폐차":
            continue
        owned += 1
        linked = (cv.vehicle_id in linked_cv_ids) or (cv.vehicle_no in linked_vnos)
        if not linked:
            not_participated.append({
                "vehicle_no": cv.vehicle_no, "model_name": cv.model_name,
                "fuel": cv.fuel, "model_year": cv.model_year, "is_ev": _is_ev(cv.fuel),
            })

    participating = len(vno_state)
    completed_count = sum(1 for s in vno_state.values() if s == "COMPLETED")
    ongoing_count = participating - completed_count
    ev_candidates = sum(1 for n in not_participated if n["is_ev"])

    return {
        "summary": {
            "owned_count": owned,
            "participating_count": participating,
            "completed_count": completed_count,
            "ongoing_count": ongoing_count,
            "not_participated_count": len(not_participated),
            "ev_candidate_count": ev_candidates,
            "participation_rate": round(participating / owned * 100, 1) if owned else None,
            "expected_reduction_total": round(expected_total, 3),
            "monitoring_reduction_total": round(monitoring_total, 3),
            "final_reduction_total": round(final_total, 3),
        },
        "participated": participated,
        "not_participated": not_participated,
    }
