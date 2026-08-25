"""운수사 감축 참여 라이프사이클 — 참여상태 파생·요약(라이프사이클 P1·P2·P3).

보유 차량(ClientVehicle) × 참여 차량(ProjectVehicle) × 사업 상태(Project.project_status)로
참여 상태(기참여/참여중/미참여)를 **파생**(저장 안 함)하고, 운수사 한 화면용 요약+목록을 만든다.
- 기참여(COMPLETED): 소속 사업이 발급완료
- 참여중(ONGOING): 소속 사업이 기획~검증(발급 전)
- 미참여(NOT): 보유버스 중 어떤 참여에도 안 걸린 차량(향후 참여 후보)

3단계 감축량 정합(P2 강화) — **ProjectVehicle이 3단계 전부의 단일 정본**:
- **예상** = ProjectVehicle.total_reduction (계획 산정)
- **모니터링** = ProjectVehicle.monitoring_reduction (워크벤치서 단방향 커밋된 실측)
- **최종** = ProjectVehicle.final_reduction (발급 배분·동결, P4). 미확정 시 발급완료의 effective로 폴백.
reduction_stage는 워크벤치 분석 스냅샷일 뿐 정본 아님(divergence 위험 제거).
"""

from collections import defaultdict
from typing import Dict, List, Optional

from models import Client, ClientVehicle, Project, ProjectVehicle

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
            ProjectVehicle.effective_reduction, ProjectVehicle.final_reduction,
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
        # 최종 = 발급확정 배분(final_reduction) 우선, 미확정이면 발급완료 사업의 effective로 폴백
        fin = _f(r.final_reduction)
        if fin is None and completed:
            fin = _f(r.effective_reduction)
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


def all_operators_overview(db, region: Optional[str] = None) -> dict:
    """전 운수사 크로스 집계(라이프사이클 보) — 운수사별 참여율·상태별 대수·3단계 감축량·오차 신호.

    단건 client_participation을 N번 부르지 않고 벌크 조회 3건으로 집계(N+1 방지):
    보유대수(ClientVehicle)·참여차량(ProjectVehicle×Project). 3단계 정본은 ProjectVehicle 단일.
    """
    # 운수사 마스터(TRANSPORT) — 이름·권역
    cq = db.query(Client.client_id, Client.company_name, Client.region).filter(
        Client.client_type == "TRANSPORT")
    if region:
        cq = cq.filter(Client.region == region)
    clients = {c.client_id: {"name": c.company_name, "region": c.region} for c in cq.all()}
    if not clients:
        return {"items": [], "operator_count": 0, "total_owned": 0, "total_participating": 0,
                "expected_total": 0.0, "monitoring_total": 0.0, "final_total": 0.0,
                "participation_rate": None}

    # 보유대수(폐차 제외)
    owned: Dict[str, int] = defaultdict(int)
    for cv in db.query(ClientVehicle.client_id, ClientVehicle.status).filter(
            ClientVehicle.client_id.in_(list(clients))).all():
        if cv.status != "폐차":
            owned[cv.client_id] += 1

    # 참여차량 + 사업상태 — 운수사별 집계
    agg: Dict[str, dict] = {cid: {"vnos": set(), "completed_vnos": set(),
                                  "exp": 0.0, "mon": 0.0, "fin": 0.0} for cid in clients}
    rows = (db.query(ProjectVehicle.client_id, ProjectVehicle.vehicle_no,
                     ProjectVehicle.total_reduction, ProjectVehicle.monitoring_reduction,
                     ProjectVehicle.effective_reduction, ProjectVehicle.final_reduction,
                     Project.project_status)
            .join(Project, ProjectVehicle.project_id == Project.project_id)
            .filter(ProjectVehicle.client_id.in_(list(clients))).all())
    for r in rows:
        a = agg.get(r.client_id)
        if a is None:
            continue
        completed = r.project_status in _COMPLETED_STATUS
        if r.vehicle_no:
            a["vnos"].add(r.vehicle_no)
            if completed:
                a["completed_vnos"].add(r.vehicle_no)
        if r.total_reduction is not None:
            a["exp"] += float(r.total_reduction)
        if r.monitoring_reduction is not None:
            a["mon"] += float(r.monitoring_reduction)
        fin = r.final_reduction if r.final_reduction is not None else (
            r.effective_reduction if completed else None)
        if fin is not None:
            a["fin"] += float(fin)

    items = []
    tot_owned = tot_part = 0
    exp_t = mon_t = fin_t = 0.0
    for cid, meta in clients.items():
        a = agg[cid]
        ow = owned.get(cid, 0)
        part = len(a["vnos"])
        comp = len(a["completed_vnos"])
        # 보유·참여 둘 다 0인 운수사는 생략(노이즈 축소)
        if ow == 0 and part == 0:
            continue
        tot_owned += ow
        tot_part += part
        exp_t += a["exp"]; mon_t += a["mon"]; fin_t += a["fin"]
        items.append({
            "client_id": cid, "operator_name": meta["name"], "region": meta["region"],
            "owned_count": ow, "participating_count": part,
            "completed_count": comp, "ongoing_count": part - comp,
            "not_participated_count": max(0, ow - part),
            "participation_rate": round(part / ow * 100, 1) if ow else None,
            "expected_reduction": round(a["exp"], 3),
            "monitoring_reduction": round(a["mon"], 3),
            "final_reduction": round(a["fin"], 3),
            "ach_monitoring": _rate(a["mon"], a["exp"]),
            "ach_final": _rate(a["fin"], a["exp"]),
        })
    # 참여율 높은 순
    items.sort(key=lambda x: (x["participation_rate"] is None, -(x["participation_rate"] or 0),
                              x["operator_name"] or ""))
    return {
        "items": items, "operator_count": len(items),
        "total_owned": tot_owned, "total_participating": tot_part,
        "expected_total": round(exp_t, 3), "monitoring_total": round(mon_t, 3),
        "final_total": round(fin_t, 3),
        "participation_rate": round(tot_part / tot_owned * 100, 1) if tot_owned else None,
    }
