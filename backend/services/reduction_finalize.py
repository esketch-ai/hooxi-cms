"""최종 감축량 확정·배분(라이프사이클 P4) — 발급량을 차량별 비율로 배분·동결.

사업 발급완료 시 확정 발급량(Project.issued_credits)을 참여 차량의 effective_reduction 비율로
배분해 ProjectVehicle.final_reduction에 동결한다. effective 합이 0이면 total_reduction 비율,
그것도 0이면 균등 배분(발급 총량 보존). 발급 총량과 배분 합의 정합을 유지(마지막 차량 보정).
"""

from typing import Optional

from models import Project, ProjectVehicle

_ISSUED_STATUS = "발급완료"


def finalize_project(db, project_id: str) -> dict:
    """발급완료 사업의 issued_credits를 차량별 final_reduction으로 배분·동결."""
    project = db.get(Project, project_id)
    if project is None:
        return {"ok": False, "reason": "사업 없음", "finalized": 0}
    if project.project_status != _ISSUED_STATUS:
        return {"ok": False, "reason": "발급완료 상태가 아님", "finalized": 0}
    if project.issued_credits is None:
        return {"ok": False, "reason": "발급량(issued_credits) 미입력", "finalized": 0}

    issued = float(project.issued_credits)
    vehicles = (db.query(ProjectVehicle)
                .filter(ProjectVehicle.project_id == project_id)
                .order_by(ProjectVehicle.vehicle_id).all())
    if not vehicles:
        return {"ok": False, "reason": "참여 차량 없음", "finalized": 0}

    def _w(v, attr):
        val = getattr(v, attr)
        return float(val) if val is not None else 0.0

    # 가중 기준: effective_reduction → total_reduction → 균등
    weights = [_w(v, "effective_reduction") for v in vehicles]
    method = "effective"
    if sum(weights) <= 0:
        weights = [_w(v, "total_reduction") for v in vehicles]
        method = "total"
    if sum(weights) <= 0:
        weights = [1.0] * len(vehicles)
        method = "equal"

    total_w = sum(weights)
    allocated = 0.0
    for i, (v, w) in enumerate(zip(vehicles, weights)):
        if i == len(vehicles) - 1:
            share = round(issued - allocated, 3)  # 마지막 차량 보정(발급 총량 정합)
        else:
            share = round(issued * w / total_w, 3)
            allocated += share
        v.final_reduction = share

    return {"ok": True, "finalized": len(vehicles), "issued": round(issued, 3),
            "method": method}
