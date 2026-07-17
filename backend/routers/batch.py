"""월초 배치 — 공공기관 계정(ETAS·BMS) 점검 → 점검 이슈 자동 생성.

설계(승인 플랜):
- 자동 로그인·자격증명 복호화는 하지 않는다(계정 잠금 리스크 원천 차단).
  배치는 site_url 도달성만 확인하고, 실제 로그인 확인은 담당자가 수행한다.
- 대상: agency_name에 점검 키워드(tb_config account_check_agencies, 기본 ETAS·BMS)
  포함 + auth_type != NONE(계정 보유) 자산.
- 각 대상마다 ISSUE 자동 생성: 사이트 장애면 URGENT, 정상 접속이면 NORMAL.
  담당 PM = client.manager_id(없으면 시드 ADMIN). (asset, period) 멱등.
- 인증: ?secret=BATCH_SECRET (Cloud Scheduler용) 또는 ADMIN 토큰(화면 수동 실행).
"""

import json
import os
from datetime import date
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

import schemas
from auth import ROLE_LEVEL, bearer_scheme, decode_token, _verify_user_from_payload
from models import ActivityHistory, Asset, Client, Config, ReportDelivery, User, get_db
from routers import common
from routers.reports import generate_for_period
from services.audit_logger import AuditLogger
from services.report_sender import SendPrecondition, send_report_core

router = APIRouter(prefix="/batch", tags=["batch"])

# 점검 대상 좁히기용 기관 키워드 — 비어 있으면(기본) 로그인 계정 보유 자산 전체.
# 운수사(ETAS·BMS)뿐 아니라 건물(태양광 발전사·히트펌프 등) 계정도 모두 대상이므로
# 기본은 전체. 특정 기관만 점검하려면 config account_check_agencies에 키워드 지정.
DEFAULT_CHECK_AGENCIES = []
_SITE_TIMEOUT = 5.0
_UA = "Mozilla/5.0 (compatible; HooxiCMS-AccountCheck/1.0)"


def _batch_secret() -> Optional[str]:
    return os.getenv("BATCH_SECRET")


def _authorize(secret: Optional[str], db: Session, credentials_user: Optional[User]):
    """시크릿 일치(Scheduler) 또는 ADMIN 토큰(화면 수동)만 허용."""
    expected = _batch_secret()
    if expected and secret == expected:
        return
    if credentials_user and ROLE_LEVEL.get(credentials_user.role, 0) >= ROLE_LEVEL["ADMIN"]:
        return
    raise HTTPException(status_code=403, detail="배치 실행 권한이 없습니다 (시크릿 또는 ADMIN 필요)")


def check_agencies(db: Session) -> list:
    """점검 대상 좁히기 키워드 — tb_config account_check_agencies(JSON 배열).

    비어 있으면 [] = 로그인 계정 보유 자산 전체 점검. 키워드가 있으면
    agency_name에 해당 키워드가 포함된 자산만 점검(특정 기관 한정).
    """
    row = db.get(Config, "account_check_agencies")
    if row and row.config_value:
        try:
            parsed = json.loads(row.config_value)
            return [str(k).strip() for k in parsed if str(k).strip()]
        except ValueError:
            pass
    return DEFAULT_CHECK_AGENCIES


def _site_reachable(url: Optional[str]) -> Optional[bool]:
    """site_url 도달성 — 로그인 없이 GET. None=URL 없음(판정 보류), True/False=도달 여부."""
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        resp = httpx.get(
            url, timeout=_SITE_TIMEOUT, follow_redirects=True, headers={"User-Agent": _UA}
        )
        return resp.status_code < 500
    except Exception:
        return False


def _seed_admin_id(db: Session) -> Optional[str]:
    email = os.getenv("SEED_ADMIN_EMAIL", "hooxi006@hooxipartners.com").strip().lower()
    admin = (
        db.query(User)
        .filter(User.email == email)
        .first()
        or db.query(User).filter(User.role == "ADMIN", User.status == "ACTIVE").first()
    )
    return admin.user_id if admin else None


def _marker(asset_id: str, period: str) -> str:
    """멱등·추적용 태그 — 이슈 content 말미에 삽입."""
    return "[점검:{0}:{1}]".format(asset_id, period)


def _optional_admin(
    credentials: Optional[HTTPAuthorizationCredentials], db: Session
) -> Optional[User]:
    """토큰이 있으면 사용자 해석, 없으면 None (시크릿 경로 허용용 — 401 안 던짐)."""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials, "access")
        return _verify_user_from_payload(payload, db)
    except HTTPException:
        return None


@router.post("/account-check", response_model=schemas.AccountCheckResponse)
def account_check(
    secret: Optional[str] = Query(None, description="BATCH_SECRET (Cloud Scheduler)"),
    period: Optional[str] = Query(None, description="YYYY-MM (기본 당월)"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """월초 계정 점검 실행 — 대상 자산별 점검 이슈 생성 (멱등).

    자동 로그인·복호화 없음. site_url 도달성만 확인하고 점검 이슈를 만든다.
    """
    actor = _optional_admin(credentials, db)
    _authorize(secret, db, actor)

    period = common.validate_period(period) if period else common.current_period()
    actor_id = (actor.user_id if actor else None) or _seed_admin_id(db)
    if not actor_id:
        raise HTTPException(status_code=503, detail="이슈 담당자로 지정할 관리자 계정이 없습니다")

    keywords = [k.upper() for k in check_agencies(db)]
    # 대상 = 로그인 계정 보유 자산(auth_type != NONE). 운수사·건물 구분 없이 전체.
    assets = (
        db.query(Asset)
        .filter(Asset.auth_type.isnot(None), Asset.auth_type != "NONE")
        .all()
    )
    if keywords:
        # 특정 기관만 좁혀 점검 (선택적)
        targets = [
            a for a in assets
            if a.agency_name and any(kw in a.agency_name.upper() for kw in keywords)
        ]
    else:
        targets = assets

    created = 0
    skipped = 0
    unreachable = 0
    now = common.now_kst()  # activity_date는 '저장값=KST 벽시계' 규약 (created_at은 UTC 유지)
    due = date(int(period[:4]), int(period[5:7]), 5)  # 당월 5일까지 처리

    for asset in targets:
        marker = _marker(asset.asset_id, period)
        exists = (
            db.query(ActivityHistory)
            .filter(
                ActivityHistory.activity_type == "ISSUE",
                ActivityHistory.content.like("%{0}%".format(marker)),
            )
            .first()
        )
        if exists:
            skipped += 1
            continue

        client = db.get(Client, asset.client_id) if asset.client_id else None
        company = client.company_name if client else "미지정 고객사"
        manager_id = (client.manager_id if client else None) or actor_id

        reachable = _site_reachable(asset.site_url)
        if reachable is False:
            unreachable += 1
            status_line = "⚠ 사이트 접속 불가 — 기관 시스템 점검/차단 가능성. 우선 확인 필요."
            priority = "URGENT"
        elif reachable is True:
            status_line = "사이트 정상 접속됨 — 로그인 유효성은 담당자가 직접 확인해 주세요."
            priority = "NORMAL"
        else:
            status_line = "등록된 사이트 URL이 없어 접속 확인을 건너뜀 — 로그인 직접 확인 필요."
            priority = "NORMAL"

        agency = asset.agency_name or "공공기관"
        content = (
            "{period} 월별 계정 점검 대상입니다.\n"
            "· 기관: {agency}\n"
            "· 계정 ID: {login_id}\n"
            "· 사이트: {site}\n"
            "· 상태: {status}\n\n"
            "담당자는 위 계정으로 직접 로그인해 유효성(암호 변경·계정 삭제 등)을 확인하고, "
            "이상이 있으면 기관에 전화해 재발급/변경을 요청한 뒤 이 이슈를 처리해 주세요.\n"
            "(비밀번호는 자산 상세의 보안 정보 열람으로 확인)\n{marker}"
        ).format(
            period=period,
            agency=agency,
            login_id=asset.login_id or "-",
            site=asset.site_url or "-",
            status=status_line,
            marker=marker,
        )

        db.add(
            ActivityHistory(
                client_id=asset.client_id,
                manager_id=manager_id,
                created_by=actor_id,
                activity_date=now,
                activity_type="ISSUE",
                issue_status="OPEN",
                priority=priority,
                due_date=due,
                next_action="계정 로그인 유효성 확인 후 이상 시 기관 연락",
                title="{0} {1} 계정 월별 점검 — {2}".format(common.AUTO_PREFIX, agency, company),
                content=content,
            )
        )
        created += 1

    AuditLogger.log_action(
        db, actor_id, "BATCH_ACCOUNT_CHECK", target_type="BATCH", target_id=period,
        new_value="created={0}, unreachable={1}".format(created, unreachable),
    )
    db.commit()
    return schemas.AccountCheckResponse(
        period=period,
        targets=len(targets),
        created=created,
        skipped=skipped,
        unreachable=unreachable,
    )


# ---------------------------------------------------------------------------
# 보고서 배치 자동 발송 — 당월 대상 생성(멱등) + 전월 APPROVED 발송
# ---------------------------------------------------------------------------
# 당월(KST)·전월 계산은 common으로 통일 — current_period()가 KST 기준이 되면서
# 배치 전용 _current_period_kst 중복 제거 (기존 이름은 테스트 하위호환 별칭).
_current_period_kst = common.current_period
_previous_period = common.previous_period


@router.post("/report-send", response_model=schemas.ReportSendBatchResponse)
def report_send(
    secret: Optional[str] = Query(None, description="BATCH_SECRET (Cloud Scheduler)"),
    period: Optional[str] = Query(None, description="발송 대상 YYYY-MM (기본: 전월)"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """월초 보고서 배치 — (a) 당월 발송 대상 자동 생성(멱등) + (b) 전월 APPROVED 자동 발송.

    - 발송 코어는 수동 발송과 동일(services.report_sender.send_report_core).
    - 건별 실패 격리: 한 건이 실패해도 나머지는 계속 발송(FAIL은 details에 사유 기록).
    - 단 Gmail 미설정(503)은 모든 건이 실패할 것이므로 감지 즉시 전체 중단(상태 변경 없음).
    """
    actor = _optional_admin(credentials, db)
    _authorize(secret, db, actor)

    current = common.current_period()  # KST 벽시계 기준 당월
    period = common.validate_period(period) if period else common.previous_period(current)
    actor_id = (actor.user_id if actor else None) or _seed_admin_id(db)
    if not actor_id:
        raise HTTPException(status_code=503, detail="배치 실행자로 지정할 관리자 계정이 없습니다")

    # (a) 당월 발송 대상 자동 생성 — reports.generate와 동일 코어 (멱등, commit 포함)
    generated_created, generated_skipped = generate_for_period(db, current, actor_id)

    # (b) 대상 기간 APPROVED(발송승인) 전건 자동 발송 — 건별 실패 격리
    targets = (
        db.query(ReportDelivery)
        .filter(ReportDelivery.period == period, ReportDelivery.status == "APPROVED")
        .order_by(ReportDelivery.created_at.asc())
        .all()
    )
    sent = failed = 0
    details = []
    for delivery in targets:
        report_id = delivery.report_id
        target_client = db.get(Client, delivery.client_id) if delivery.client_id else None
        client_name = target_client.company_name if target_client else None
        try:
            send_report_core(db, delivery, actor_id)  # 성공 시 코어가 commit
        except SendPrecondition as exc:
            db.rollback()  # 미커밋 잔여 상태 폐기 (502 FAIL 로그는 코어가 이미 커밋)
            if exc.code == 503:
                # Gmail 미설정 — 모든 건이 실패할 것이므로 전체 중단 (상태 변경 없음)
                raise HTTPException(status_code=503, detail=exc.detail)
            failed += 1
            details.append(
                schemas.ReportSendBatchDetail(
                    report_id=report_id, client_name=client_name,
                    result="FAIL", detail=exc.detail,
                )
            )
            continue
        except Exception as exc:  # 예기치 못한 오류도 건별 격리 — 배치 전체 중단 금지
            db.rollback()
            failed += 1
            details.append(
                schemas.ReportSendBatchDetail(
                    report_id=report_id, client_name=client_name,
                    result="FAIL", detail=str(exc),
                )
            )
            continue
        sent += 1
        details.append(
            schemas.ReportSendBatchDetail(
                report_id=report_id, client_name=client_name, result="SENT"
            )
        )

    # 배치 완료 감사 — 카운트 요약만 기록 (수신자 이메일 등 개인정보 미기록, R2-E6)
    AuditLogger.log_action(
        db, actor_id, "BATCH_REPORT_SEND", target_type="BATCH", target_id=period,
        new_value="generated={0}, targets={1}, sent={2}, failed={3}".format(
            generated_created, len(targets), sent, failed
        ),
    )
    db.commit()
    return schemas.ReportSendBatchResponse(
        period=period,
        generated_created=generated_created,
        generated_skipped=generated_skipped,
        targets=len(targets),
        sent=sent,
        failed=failed,
        details=details,
    )
