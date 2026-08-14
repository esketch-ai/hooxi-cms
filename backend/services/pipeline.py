"""부서 워크플로우 파이프라인 조회층 — 수집→결산→정산→보고→통지 5단계 파생(P4 증분4).

그레인 = (운수사 client_id × 사업 project_id) — P2 settlement_summary 셀과 동일 축.
신규 테이블/컬럼 없이 기존 데이터에서 각 단계 진행상태를 파생한다(현황판용 조회 전용).

5단계 신호 원천과 신호 강약(중요 — 필드 의미로 명시):
- 수집(collect): (client,project) ProjectVehicle 존재 → 셀당 정확 신호.
- 결산(accounting): 그 셀에 expected_payout non-null 차량 존재 → 셀당 정확 신호.
- 정산(settlement): tb_settlement 헤더 존재/status → (client,project[,period]) 정확 신호.
  헤더 없으면 '예정'(settlement_status=None). period가 여럿이면 최근 생성 헤더 status.
- 보고(report): DATA_EXPORT(target_type ASSET_REPORT) 감사 존재 → **전역(약한) 신호**.
  정산요약 반출은 셀 단위 target이 없어, 한 번이라도 반출되면 모든 셀이 reported=True.
- 통지(notice): 운수사별 ActivityHistory([자동]…정산… EMAIL)는 셀→운수사 단위 정확 신호,
  SETTLEMENT_NOTICE_SEND 감사는 배치 요약(target 없음) → **전역(약한) 신호**. 둘 중 하나면 통지로 본다.

쿼리 수는 행 수와 무관하게 상수(집계 1 + 헤더 1 + 통지활동 1 + 전역감사 2 = 5) — N+1 없음.
"""

from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import ActivityHistory, AuditLog, Client, Project, ProjectVehicle, Settlement
from routers.common import AUTO_PREFIX
from services.settlement_summary import UNASSIGNED_LABEL

# 단계 코드(현재 최고 도달 단계) — 프론트가 라벨로 매핑. 순서가 곧 진행 순서다.
STAGE_ORDER = ["none", "collect", "accounting", "settlement", "report", "notice"]

# 단계별 '다음 할일' — 아직 도달하지 못한 바로 다음 단계를 문자열로 안내.
_NEXT_ACTION = {
    "none": "차량 수집 필요",
    "collect": "예상지급액 산정 필요",
    "accounting": "정산 확정 필요",
    "settlement": "보고서 반출 필요",
    "report": "정산 통지 필요",
    "notice": "완료",
}


def _derive_stage(
    vehicle_count: int,
    has_accounting: bool,
    settlement_status: Optional[str],
    reported: bool,
    notified: bool,
) -> str:
    """5단계 중 현재 최고 도달 단계 — collect부터 연속으로 충족된 최상단(비연속 승격 금지).

    각 단계는 직전 단계 완료를 전제한다(수집 없이 결산·정산 승격 불가). 확정 시점에
    expected_payout이 반드시 있으므로 정상 흐름에선 연속성이 보장된다(약한 전역 신호가
    미수집 셀을 잘못 끌어올리지 않도록 하는 가드이기도 하다).
    """
    if vehicle_count <= 0:
        return "none"
    if not has_accounting:
        return "collect"
    if settlement_status is None:
        return "accounting"
    if not reported:
        return "settlement"
    if not notified:
        return "report"
    return "notice"


def settlement_pipeline(
    db: Session,
    *,
    client_id: Optional[str] = None,
    project_id: Optional[str] = None,
    settlement_status: Optional[str] = None,
) -> dict:
    """(운수사×사업) 파이프라인 진행표 — 5단계 파생 + 다음 할일 + 단계별 카운트.

    집계 1쿼리(차량수·expected_payout non-null 수)에 정산 헤더·통지 활동·전역 감사(보고/통지)
    신호를 배치 조회로 결합한다(N+1 없음). settlement_status 필터는 파생 후 status 일치 행만 남긴다.
    """
    # 1) 셀 집계 — (client_id, project_id)별 차량수 + expected_payout non-null 수(=결산 신호).
    #    Project는 필수 조인, Client는 outer(미지정 client_id 보존). settlement_summary와 동일 관용구.
    q = (
        db.query(
            ProjectVehicle.client_id,
            Client.company_name,
            ProjectVehicle.project_id,
            Project.project_name,
            func.count(ProjectVehicle.vehicle_id),
            func.count(ProjectVehicle.expected_payout),  # non-null만 카운트 → 결산 완료 신호
        )
        .join(Project, Project.project_id == ProjectVehicle.project_id)
        .outerjoin(Client, Client.client_id == ProjectVehicle.client_id)
        .group_by(
            ProjectVehicle.client_id,
            Client.company_name,
            ProjectVehicle.project_id,
            Project.project_name,
        )
    )
    if client_id:
        q = q.filter(ProjectVehicle.client_id == client_id)
    if project_id:
        q = q.filter(ProjectVehicle.project_id == project_id)

    # 2) 정산 헤더 — (client_id, project_id)별 status. period가 여럿이면 최근 생성분으로 대표.
    hq = db.query(
        Settlement.client_id, Settlement.project_id, Settlement.status
    ).order_by(Settlement.created_at.asc())
    if client_id:
        hq = hq.filter(Settlement.client_id == client_id)
    if project_id:
        hq = hq.filter(Settlement.project_id == project_id)
    header_status: dict = {}
    for cid, pid, status in hq.all():
        header_status[(cid, pid)] = status  # asc 정렬 → 마지막(최근 생성) status가 최종 반영

    # 3) 통지 활동(운수사 단위 정확 신호) — [자동] 정산 명세 EMAIL 이력이 있는 client_id 집합.
    #    activity_type/제목 패턴은 기존 자동 적재 관용구(asset_report)와 동일한 기존 데이터 조회.
    notice_clients = {
        row[0]
        for row in (
            db.query(ActivityHistory.client_id)
            .filter(
                ActivityHistory.activity_type == "EMAIL",
                ActivityHistory.title.like(AUTO_PREFIX + "%"),
                ActivityHistory.title.like("%정산%"),
                ActivityHistory.client_id.isnot(None),
            )
            .distinct()
            .all()
        )
    }

    # 4) 전역(약한) 신호 — 보고서 반출(DATA_EXPORT/ASSET_REPORT)·정산 통지 배치(SETTLEMENT_NOTICE_SEND)
    #    감사 존재 여부. 셀 단위 target이 없어 한 번이라도 있으면 전 셀 공통으로 적용된다(신호 약함).
    reported_global = (
        db.query(AuditLog.log_id)
        .filter(AuditLog.action == "DATA_EXPORT", AuditLog.target_type == "ASSET_REPORT")
        .first()
        is not None
    )
    notice_audit_global = (
        db.query(AuditLog.log_id)
        .filter(AuditLog.action == "SETTLEMENT_NOTICE_SEND")
        .first()
        is not None
    )

    items = []
    for cid, cname, pid, pname, vcount, payout_cnt in q.all():
        vehicle_count = int(vcount or 0)
        has_accounting = int(payout_cnt or 0) > 0
        status = header_status.get((cid, pid))  # 없으면 None(=예정)
        reported = reported_global
        # 미지정(client_id=None) 셀은 통지 불가(수신 운수사 특정 불가) — notified 강제 False.
        if cid is None:
            notified = False
        else:
            notified = notice_audit_global or (cid in notice_clients)
        stage = _derive_stage(vehicle_count, has_accounting, status, reported, notified)
        items.append(
            {
                "client_id": cid,
                "company_name": cname if cid is not None else UNASSIGNED_LABEL,
                "project_id": pid,
                "project_name": pname,
                "vehicle_count": vehicle_count,
                "has_accounting": has_accounting,
                "settlement_status": status,  # None=예정 / CONFIRMED·BILLED·COMPLETED
                "reported": reported,  # 전역 약한 신호(반출 발생 여부)
                "notified": notified,  # 운수사 활동(정확) or 배치 감사(약한 전역)
                "stage": stage,
                "next_action": _NEXT_ACTION[stage],
            }
        )

    # settlement_status 필터 — 파생 status 일치 행만(정산 헤더 status 기준). None 필터는 미지원.
    if settlement_status:
        items = [it for it in items if it["settlement_status"] == settlement_status]

    items.sort(key=lambda it: ((it["company_name"] or ""), (it["project_name"] or "")))

    # 단계별 요약 카운트 — 모든 단계 키를 0으로 초기화(누락 없이 프론트가 바로 사용).
    stage_counts = {s: 0 for s in STAGE_ORDER}
    for it in items:
        stage_counts[it["stage"]] += 1

    return {"items": items, "total": len(items), "stage_counts": stage_counts}
