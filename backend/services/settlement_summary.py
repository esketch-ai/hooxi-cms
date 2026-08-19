"""정산 요약 매트릭스 조회층 — 운수사×사업 grain 집계(P2 '자산관리 보고').

ProjectVehicle의 저장 파생값(total_reduction·effective_reduction·expected_payout)을
(운수사, 사업) 조합으로 배치 집계(1쿼리)하고, 운수사별로 롤업한다. 재계산 없음 —
finance_query·compute_accounting과 동일한 None 전파 규약(그룹 전건 None이면 None,
아니면 non-null 합)을 따른다. 매출/매입은 운수사 귀속이 애매하여 제외(예상지급액 중심).

지급 정본은 ProjectVehicle.client_id(차량 소유 운수사)다 — Project.client_id(대표사)와
다를 수 있다. client_id가 없는 차량은 '(미지정)' 행으로 모아 Σ행==전사총계 정합을 보장한다.
조회 전용 — 신규 컬럼 없음.
"""

from typing import Optional

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Client, Project, ProjectVehicle
from services.market_rate import expected_revenue

# NULL client_id(미지정 운수사) 행의 표시 라벨 — 실제 client_id가 아니라 집계 표시 전용.
UNASSIGNED_LABEL = "(미지정)"


def _sum_opt(values, ndigits):
    """None 안전 합 — 전부 None이면 None, 일부 None은 제외하고 합(반올림).

    finance_query._sum_opt와 동일 규약(그룹 전건 None → None). 감축량은 3자리,
    예상지급액은 2자리로 호출부에서 ndigits를 지정한다.
    """
    parts = [float(v) for v in values if v is not None]
    return round(sum(parts), ndigits) if parts else None


def settlement_summary(
    db: Session,
    *,
    client_id: Optional[str] = None,
    client_type: Optional[str] = None,
    region: Optional[str] = None,
    avg6: Optional[Decimal] = None,
) -> dict:
    """운수사×사업 정산 요약 매트릭스 — 운수사별 롤업 + 사업 드릴다운 + 전사 총계.

    1쿼리로 (client_id, project_id) group_by 집계(vehicle_count·Σ감축량·Σ예상지급액)를
    구하고, 이를 운수사별로 롤업한다. NULL client_id 차량은 '(미지정)' 행으로 모은다.
    필터(client_id/client_type/region)는 Client 속성 기준으로 적용한다(client_type 값은
    전달값 그대로 — 공통코드 하드코딩 금지). N+1 없음(집계 1쿼리 + 파이썬 롤업).
    """
    # 집계 1쿼리 — Project는 필수 조인(FK NOT NULL), Client는 outer(NULL client_id 보존).
    # Postgres 호환을 위해 비집계 선택 컬럼은 모두 group_by에 포함(값은 id에 종속 → 무해).
    q = (
        db.query(
            ProjectVehicle.client_id,
            Client.company_name,
            Client.region,
            Client.client_type,
            Client.contract_status,
            ProjectVehicle.project_id,
            Project.project_name,
            func.count(ProjectVehicle.vehicle_id),
            func.sum(ProjectVehicle.total_reduction),
            func.sum(ProjectVehicle.effective_reduction),
            func.sum(ProjectVehicle.expected_payout),
        )
        .join(Project, Project.project_id == ProjectVehicle.project_id)
        .outerjoin(Client, Client.client_id == ProjectVehicle.client_id)
        .group_by(
            ProjectVehicle.client_id,
            Client.company_name,
            Client.region,
            Client.client_type,
            Client.contract_status,
            ProjectVehicle.project_id,
            Project.project_name,
        )
    )
    if client_id:
        q = q.filter(ProjectVehicle.client_id == client_id)
    if client_type:
        q = q.filter(Client.client_type == client_type)
    if region:
        q = q.filter(Client.region == region)

    # 운수사별 롤업 — key는 client_id(미지정은 None). 사업별 드릴다운을 먼저 모은다.
    entries: dict = {}
    for (
        cid,
        cname,
        cregion,
        ctype,
        cstatus,
        pid,
        pname,
        vcount,
        tred,
        ered,
        payout,
    ) in q.all():
        entry = entries.get(cid)
        if entry is None:
            entry = {
                "client_id": cid,
                "company_name": cname if cid is not None else UNASSIGNED_LABEL,
                "region": cregion,
                "client_type": ctype,
                "contract_status": cstatus,
                "projects": [],
            }
            entries[cid] = entry
        entry["projects"].append(
            {
                "project_id": pid,
                "project_name": pname,
                "vehicle_count": int(vcount or 0),
                "total_reduction": round(float(tred), 3) if tred is not None else None,
                "effective_reduction": (
                    round(float(ered), 3) if ered is not None else None
                ),
                "expected_payout": (
                    round(float(payout), 2) if payout is not None else None
                ),
                # 예상수익 — 셀(운수사×사업) leaf에서 Σeff×6개월평균시세 원단위 절사(None 안전)
                "expected_revenue": expected_revenue(ered, avg6),
            }
        )

    # 운수사 행 롤업 — 사업별 드릴다운(project_name 정렬)에서 None 안전 합으로 요약.
    items = []
    for entry in entries.values():
        projs = sorted(entry["projects"], key=lambda p: p["project_name"] or "")
        entry["projects"] = projs
        entry["participating_project_count"] = len(projs)
        entry["participating_vehicle_count"] = sum(p["vehicle_count"] for p in projs)
        entry["total_reduction"] = _sum_opt((p["total_reduction"] for p in projs), 3)
        entry["effective_reduction"] = _sum_opt(
            (p["effective_reduction"] for p in projs), 3
        )
        entry["expected_payout"] = _sum_opt((p["expected_payout"] for p in projs), 2)
        # 예상수익 롤업 — 셀 값을 None-안전 합(셀→운수사 정합). 원단위 정수라 0자리.
        entry["expected_revenue"] = _sum_opt(
            (p["expected_revenue"] for p in projs), 0
        )
        items.append(entry)
    items.sort(key=lambda e: e["company_name"] or "")

    # 전사 총계 — 전체 셀(운수사×사업) 기준. distinct project는 합산 아닌 고유수(중복계상 회피).
    all_cells = [p for e in items for p in e["projects"]]
    totals = {
        "distinct_project_count": len({p["project_id"] for p in all_cells}),
        "participating_vehicle_count": sum(p["vehicle_count"] for p in all_cells),
        "total_reduction": _sum_opt((p["total_reduction"] for p in all_cells), 3),
        "effective_reduction": _sum_opt(
            (p["effective_reduction"] for p in all_cells), 3
        ),
        "expected_payout": _sum_opt((p["expected_payout"] for p in all_cells), 2),
        # 예상수익 총계 — 셀 값 None-안전 합(셀→운수사→총계 정합).
        "expected_revenue": _sum_opt((p["expected_revenue"] for p in all_cells), 0),
    }

    return {
        "items": items,
        "total": len(items),
        "totals": totals,
        "market_rate_avg6": float(avg6) if avg6 is not None else None,
    }
