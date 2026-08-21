"""경영 관찰(Executive View) API — OB-R1 (OBSERVE_REDESIGN_PLAN).

- GET /observe/summary?months=6|12|24 : 한눈(KPI Δ·추이·퍼널·시세·전환·신호) 1콜.
- GET /observe/detail?topic=&key= : 개요 드로어 — 상위 구성(≤20행)+합계+해설+담당자 이름.
읽기 전용. OBSERVER 화이트리스트(/api/v1/observe 프리픽스)와 '경영진/경영전략실' 그룹
(/observe 메뉴)에서 접근한다. 내부 3역할도 조회 가능(읽기 전용 집계).
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth import get_current_user
from models import User, get_db
from services import observe as observe_service

router = APIRouter(prefix="/observe", tags=["observe"])


@router.get("/summary")
def observe_summary(
    months: int = Query(12, description="추이 기간(6/12/24개월)"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if months not in observe_service.ALLOWED_MONTHS:
        raise HTTPException(status_code=422, detail="months는 6/12/24 중 하나입니다")
    return observe_service.build_summary(db, months)


@router.get("/detail")
def observe_detail(
    topic: str = Query(..., description="revenue|margin|month|inventory|receivable|payout|funnel|rate|ev|project|signal"),
    key: Optional[str] = Query(None, description="topic별 보조 키(월·단계·상태 등)"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """개요 드로어 — 경영자가 '누구에게 물어볼지'까지 확인할 수 있게 담당자 이름 포함."""
    try:
        return observe_service.build_detail(db, topic, key)
    except ValueError:
        raise HTTPException(status_code=422, detail="지원하지 않는 topic입니다")
