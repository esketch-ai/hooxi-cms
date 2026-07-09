"""데모 시드 데이터 — 수동 실행 전용 (자동 실행 금지).

실행: cd backend && python scripts/seed_demo.py
멱등: 고정 PK(demo-*)로 존재 여부를 확인해 재실행 시 중복 생성하지 않는다.

내용: 데모 사용자 3명 · 고객사 8곳(TRANSPORT/FACILITY, ACTIVE/HOLD/END 혼합) ·
활동 이력 30건(ISSUE 상태 분포 + 코멘트) · 당월 일정 15건(REPORT_DUE 포함) ·
당월 보고서 대상 8건(상태 분포) · 문서 10건(더미 file_url) · 구독·수신자 설정.

P2 확장: 자산 12건(고객사 분산·인증 방식 혼합 — ASSET_ENC_KEY 미설정 시 인증정보 비움) ·
감축 사업 4건(상태 분포·단가 입력/미입력 혼합) · 참여 고객사 매핑 10건(배분율 합계 100% 이하,
정산 상태 분포). expected_amount는 §10.3 산식으로 적재.
"""

import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import (  # noqa: E402
    ActivityHistory,
    Asset,
    Client,
    Document,
    IssueComment,
    Project,
    ProjectClientMap,
    ReportDelivery,
    ReportRecipient,
    ReportSubscription,
    Schedule,
    SessionLocal,
    User,
    init_db,
    utcnow,
)
from routers.common import compute_expected_amount  # noqa: E402
from services import crypto  # noqa: E402

NOW = utcnow()
PERIOD = NOW.strftime("%Y-%m")
MONTH_START = datetime(NOW.year, NOW.month, 1)


def _day(day: int, hour: int = 10) -> datetime:
    """당월 day일 hour시 (말일 보정)."""
    import calendar

    last = calendar.monthrange(NOW.year, NOW.month)[1]
    return datetime(NOW.year, NOW.month, min(day, last), hour)


USERS = [
    {"user_id": "demo-user-01", "email": "demo.manager@hooxipartners.com", "name": "김팀장", "role": "MANAGER"},
    {"user_id": "demo-user-02", "email": "demo.staff1@hooxipartners.com", "name": "이주임", "role": "STAFF"},
    {"user_id": "demo-user-03", "email": "demo.staff2@hooxipartners.com", "name": "박대리", "role": "STAFF"},
]

CLIENTS = [
    ("demo-cl-01", "TRANSPORT", "한빛운수", "ACTIVE", "demo-user-01", "서울", "Y"),
    ("demo-cl-02", "TRANSPORT", "미래교통", "ACTIVE", "demo-user-02", "경기", "Y"),
    ("demo-cl-03", "FACILITY", "그린에너지솔루션", "ACTIVE", "demo-user-02", "인천", "Y"),
    ("demo-cl-04", "FACILITY", "에코팜스", "ACTIVE", "demo-user-03", "충남", "Y"),
    ("demo-cl-05", "TRANSPORT", "대성로지스", "HOLD", "demo-user-01", "부산", "Y"),
    ("demo-cl-06", "FACILITY", "서해태양광", "ACTIVE", "demo-user-03", "전북", "Y"),
    ("demo-cl-07", "TRANSPORT", "청록버스", "END", "demo-user-01", "대구", "N"),
    ("demo-cl-08", "FACILITY", "누리히트펌프", "ACTIVE", "demo-user-02", "강원", "Y"),
]

# (id, client, manager, days_ago, type, retention, issue_status, priority, title)
HISTORIES = [
    ("demo-h-01", "demo-cl-01", "demo-user-01", 1, "CALL", "활용", None, None, "월간 운행 데이터 회수 통화"),
    ("demo-h-02", "demo-cl-01", "demo-user-02", 3, "MEETING", "재계약", None, None, "재계약 조건 협의 미팅"),
    ("demo-h-03", "demo-cl-01", "demo-user-01", 5, "ISSUE", None, "OPEN", "URGENT", "충전기 연동 데이터 누락 문의"),
    ("demo-h-04", "demo-cl-02", "demo-user-02", 2, "EMAIL", "활용", None, None, "6월 정산 자료 송부"),
    ("demo-h-05", "demo-cl-02", "demo-user-02", 6, "ISSUE", None, "IN_PROGRESS", "NORMAL", "FMS 로그인 오류 접수"),
    ("demo-h-06", "demo-cl-02", "demo-user-03", 9, "SITE_VISIT", "온보딩", None, None, "차고지 현장 실사"),
    ("demo-h-07", "demo-cl-03", "demo-user-02", 1, "KAKAO", "활용", None, None, "설비 점검 일정 카톡 안내"),
    ("demo-h-08", "demo-cl-03", "demo-user-02", 4, "ISSUE", None, "HOLD", "NORMAL", "계량기 교체 승인 대기"),
    ("demo-h-09", "demo-cl-03", "demo-user-01", 8, "MEETING", "확장", None, None, "태양광 증설 제안 미팅"),
    ("demo-h-10", "demo-cl-04", "demo-user-03", 2, "CALL", "온보딩", None, None, "온보딩 체크리스트 안내"),
    ("demo-h-11", "demo-cl-04", "demo-user-03", 7, "ISSUE", None, "CLOSED", "NORMAL", "월간 보고서 수신자 변경 요청"),
    ("demo-h-12", "demo-cl-04", "demo-user-01", 12, "MEETING", "구매결정", None, None, "계약 조건 최종 협의"),
    ("demo-h-13", "demo-cl-05", "demo-user-01", 3, "CALL", "검토", None, None, "계약 재개 검토 통화"),
    ("demo-h-14", "demo-cl-05", "demo-user-01", 10, "ISSUE", None, "OPEN", "NORMAL", "정산 기준 재협의 요청"),
    ("demo-h-15", "demo-cl-05", "demo-user-02", 15, "EMAIL", "검토", None, None, "서비스 재개 제안서 송부"),
    ("demo-h-16", "demo-cl-06", "demo-user-03", 1, "SITE_VISIT", "활용", None, None, "발전소 정기 점검 방문"),
    ("demo-h-17", "demo-cl-06", "demo-user-03", 5, "ISSUE", None, "IN_PROGRESS", "URGENT", "인버터 통신 장애"),
    ("demo-h-18", "demo-cl-06", "demo-user-02", 11, "CALL", "활용", None, None, "발전량 리포트 문의 응대"),
    ("demo-h-19", "demo-cl-07", "demo-user-01", 20, "CALL", "인지", None, None, "계약 종료 후 재영업 콜"),
    ("demo-h-20", "demo-cl-07", "demo-user-01", 25, "EMAIL", "관심", None, None, "신규 감축 사업 소개 메일"),
    ("demo-h-21", "demo-cl-08", "demo-user-02", 2, "MEETING", "온보딩", None, None, "히트펌프 모니터링 온보딩"),
    ("demo-h-22", "demo-cl-08", "demo-user-02", 6, "ISSUE", None, "OPEN", "NORMAL", "계측 데이터 단위 오류 문의"),
    ("demo-h-23", "demo-cl-08", "demo-user-03", 13, "KAKAO", "온보딩", None, None, "설치 일정 카톡 협의"),
    ("demo-h-24", "demo-cl-01", "demo-user-02", 16, "EMAIL", "활용", None, None, "5월 보고서 정정본 송부"),
    ("demo-h-25", "demo-cl-02", "demo-user-01", 18, "MEETING", "활용", None, None, "분기 성과 리뷰 미팅"),
    ("demo-h-26", "demo-cl-03", "demo-user-03", 21, "CALL", "활용", None, None, "요금제 변경 문의 응대"),
    ("demo-h-27", "demo-cl-04", "demo-user-02", 24, "ISSUE", None, "CLOSED", "URGENT", "보고서 오발송 정정"),
    ("demo-h-28", "demo-cl-06", "demo-user-01", 27, "MEETING", "확장", None, None, "ESS 연계 확장 제안"),
    ("demo-h-29", None, "demo-user-03", 4, "CALL", "인지", None, None, "신규 문의 인바운드 콜(미지정 고객)"),
    ("demo-h-30", "demo-cl-08", "demo-user-02", 29, "SITE_VISIT", "검토", None, None, "설치 전 현장 조사"),
]

# 이슈 코멘트 (history_id → 코멘트들)
COMMENTS = [
    ("demo-c-01", "demo-h-03", "demo-user-01", "COMMENT", "충전 사업자 측에 원본 로그 요청함"),
    ("demo-c-02", "demo-h-03", "demo-user-02", "COMMENT", "6/30~7/2 구간 누락 확인, 재수집 예정"),
    ("demo-c-03", "demo-h-05", "demo-user-02", "STATUS_CHANGE", "상태 변경: OPEN → IN_PROGRESS"),
    ("demo-c-04", "demo-h-08", "demo-user-02", "COMMENT", "고객사 내부 결재 대기 중 — 다음 주 확인"),
    ("demo-c-05", "demo-h-11", "demo-user-03", "STATUS_CHANGE", "상태 변경: OPEN → CLOSED — 수신자 변경 완료"),
    ("demo-c-06", "demo-h-17", "demo-user-03", "COMMENT", "제조사 AS 접수 완료, 부품 교체 예정"),
    ("demo-c-07", "demo-h-27", "demo-user-02", "STATUS_CHANGE", "상태 변경: IN_PROGRESS → CLOSED — 정정본 재발송"),
]

# (id, client, manager, day, hour, type, title, status)
SCHEDULES = [
    ("demo-s-01", "demo-cl-01", "demo-user-01", 2, 10, "MEETING", "한빛운수 월간 리뷰 미팅", "DONE"),
    ("demo-s-02", "demo-cl-02", "demo-user-02", 3, 14, "CALL", "미래교통 정산 확인 콜", "DONE"),
    ("demo-s-03", "demo-cl-03", "demo-user-02", 5, 11, "SITE_VISIT", "그린에너지 설비 점검", "PLANNED"),
    ("demo-s-04", "demo-cl-04", "demo-user-03", 8, 15, "MEETING", "에코팜스 온보딩 미팅", "PLANNED"),
    ("demo-s-05", "demo-cl-05", "demo-user-01", 10, 10, "CALL", "대성로지스 재개 협의 콜", "PLANNED"),
    ("demo-s-06", "demo-cl-06", "demo-user-03", 12, 9, "SITE_VISIT", "서해태양광 인버터 점검", "PLANNED"),
    ("demo-s-07", "demo-cl-08", "demo-user-02", 15, 13, "MEETING", "누리히트펌프 데이터 검수", "PLANNED"),
    ("demo-s-08", None, "demo-user-01", 7, 9, "INTERNAL", "주간 팀 회의", "DONE"),
    ("demo-s-09", None, "demo-user-01", 14, 9, "INTERNAL", "주간 팀 회의", "PLANNED"),
    ("demo-s-10", "demo-cl-01", "demo-user-01", 25, 9, "REPORT_DUE", "[자동] 보고서 마감: 한빛운수 월간 운행 보고서", "PLANNED"),
    ("demo-s-11", "demo-cl-02", "demo-user-02", 25, 9, "REPORT_DUE", "[자동] 보고서 마감: 미래교통 월간 운행 보고서", "PLANNED"),
    ("demo-s-12", "demo-cl-03", "demo-user-02", 20, 9, "REPORT_DUE", "[자동] 보고서 마감: 그린에너지솔루션 월간 발전 보고서", "PLANNED"),
    ("demo-s-13", "demo-cl-06", "demo-user-03", 20, 9, "REPORT_DUE", "[자동] 보고서 마감: 서해태양광 월간 발전 보고서", "PLANNED"),
    ("demo-s-14", "demo-cl-04", "demo-user-03", 18, 16, "CALL", "에코팜스 계량 데이터 확인 콜", "PLANNED"),
    ("demo-s-15", "demo-cl-07", "demo-user-01", 22, 11, "MEETING", "청록버스 재계약 제안 미팅", "PLANNED"),
]

# (client, report_type, due_day, channel)
SUBSCRIPTIONS = [
    ("demo-cl-01", "월간 운행 보고서", 25, "EMAIL"),
    ("demo-cl-02", "월간 운행 보고서", 25, "EMAIL"),
    ("demo-cl-03", "월간 발전 보고서", 20, "BOTH"),
    ("demo-cl-04", "월간 설비 보고서", 15, "EMAIL"),
    ("demo-cl-05", "월간 운행 보고서", 25, "EMAIL"),
    ("demo-cl-06", "월간 발전 보고서", 20, "EMAIL"),
    ("demo-cl-08", "월간 설비 보고서", 15, "KAKAO"),
    ("demo-cl-01", "분기 감축 실적 보고서", 28, "EMAIL"),
]

# (id, client, report_type, status, due_day, manager)
REPORTS = [
    ("demo-r-01", "demo-cl-01", "월간 운행 보고서", "SENT", 25, "demo-user-01"),
    ("demo-r-02", "demo-cl-02", "월간 운행 보고서", "WRITING", 25, "demo-user-02"),
    ("demo-r-03", "demo-cl-03", "월간 발전 보고서", "REVIEW", 20, "demo-user-02"),
    ("demo-r-04", "demo-cl-04", "월간 설비 보고서", "CONFIRMED", 15, "demo-user-03"),
    ("demo-r-05", "demo-cl-05", "월간 운행 보고서", "STANDBY", 25, "demo-user-01"),
    ("demo-r-06", "demo-cl-06", "월간 발전 보고서", "STANDBY", 20, "demo-user-03"),
    ("demo-r-07", "demo-cl-08", "월간 설비 보고서", "WRITING", 15, "demo-user-02"),
    ("demo-r-08", "demo-cl-01", "분기 감축 실적 보고서", "STANDBY", 28, "demo-user-01"),
]

# (id, client, doc_type, title, report_id)
DOCUMENTS = [
    ("demo-d-01", "demo-cl-01", "REPORT", "한빛운수 7월 운행 보고서 v1", "demo-r-01"),
    ("demo-d-02", "demo-cl-03", "REPORT", "그린에너지 7월 발전 보고서 v1", "demo-r-03"),
    ("demo-d-03", "demo-cl-04", "REPORT", "에코팜스 7월 설비 보고서 v1", "demo-r-04"),
    ("demo-d-04", "demo-cl-01", "CONTRACT", "한빛운수 운영 계약서", None),
    ("demo-d-05", "demo-cl-02", "CONTRACT", "미래교통 운영 계약서", None),
    ("demo-d-06", "demo-cl-06", "CONTRACT", "서해태양광 위탁 계약서", None),
    ("demo-d-07", None, "FORM", "KOC 표준 모니터링 양식", None),
    ("demo-d-08", None, "FORM", "VCM 검증 체크리스트", None),
    ("demo-d-09", "demo-cl-06", "PHOTO", "서해태양광 현장 점검 사진", None),
    ("demo-d-10", "demo-cl-08", "PHOTO", "누리히트펌프 설치 현장 사진", None),
]


# ---------------------------------------------------------------------------
# P2 — 자산·감축 사업·정산 매핑 (SCR-04/06/07)
# ---------------------------------------------------------------------------
# (id, client, group, type, qty, spec, telemetry, agency, auth_type, login_id, secret)
# secret은 ASSET_ENC_KEY가 설정된 경우에만 암호화 저장 — 미설정 시 인증정보 비움
ASSETS = [
    ("demo-a-01", "demo-cl-01", "MOBILITY", "ICE", 45, "경유 시내버스", "Y", "한국환경공단", "ID_PW", "hanbit-admin", "demo-pw-01!"),
    ("demo-a-02", "demo-cl-01", "MOBILITY", "EV", 12, "전기 저상버스", "Y", "스마트FMS관제", "API_KEY", None, "demo-token-02"),
    ("demo-a-03", "demo-cl-02", "MOBILITY", "ICE", 30, "경유 광역버스", "Y", "한국환경공단", "ID_PW", "mirae-fleet", "demo-pw-03!"),
    ("demo-a-04", "demo-cl-02", "MOBILITY", "EV", 8, "전기 마을버스", "Y", "스마트FMS관제", "API_KEY", None, "demo-token-04"),
    ("demo-a-05", "demo-cl-03", "FACILITY", "SOLAR", 1, "500kW 태양광 발전소", "Y", "한국에너지공단 RPS", "API_KEY", None, "demo-token-05"),
    ("demo-a-06", "demo-cl-03", "FACILITY", "SOLAR", 1, "100kW 지붕형 태양광", "N", None, "NONE", None, None),
    ("demo-a-07", "demo-cl-04", "FACILITY", "HEATPUMP", 3, "농업용 히트펌프 30RT", "Y", "설비 원격관제", "ID_PW", "ecofarms-hp", "demo-pw-07!"),
    ("demo-a-08", "demo-cl-05", "MOBILITY", "ICE", 25, "경유 화물트럭", "N", None, "NONE", None, None),
    ("demo-a-09", "demo-cl-06", "FACILITY", "SOLAR", 2, "1MW 지상형 태양광", "Y", "한국에너지공단 RPS", "API_KEY", None, "demo-token-09"),
    ("demo-a-10", "demo-cl-07", "MOBILITY", "ICE", 18, "경유 시외버스", "N", None, "NONE", None, None),
    ("demo-a-11", "demo-cl-08", "FACILITY", "HEATPUMP", 5, "산업용 히트펌프 50RT", "Y", "설비 원격관제", "ID_PW", "nuri-hp", "demo-pw-11!"),
    ("demo-a-12", "demo-cl-06", "FACILITY", "SOLAR", 1, "ESS 연계 태양광", "N", "한국에너지공단 RPS", "API_KEY", None, "demo-token-12"),
]

# (id, name, reg_code, status, expected_credits, unit_price, mon_cycle,
#  issue_in_days(예상 발급일 오프셋), issued_credits, manager)
PROJECTS = [
    ("demo-p-01", "수도권 전기버스 전환 감축사업", "R-2024-KR-03-000101", "모니터링",
     12000, 15000, "분기", 45, None, "demo-user-01"),
    ("demo-p-02", "서해권 태양광 발전 감축사업", "R-2023-KR-03-000202", "검증",
     8000, None, "반기", 90, None, "demo-user-02"),  # 단가 미입력 — 금액 '미정'
    ("demo-p-03", "히트펌프 보일러 대체 감축사업", "R-2025-KR-03-000303", "기획",
     3000, None, "월간", None, None, "demo-user-03"),
    ("demo-p-04", "노후 화물차 EV 전환 감축사업", "R-2022-KR-03-000404", "발급완료",
     15000, 12000, "분기", -30, 14200, "demo-user-01"),
]

# (id, project, client, asset, allocation_ratio, success_fee_rate, settlement_status)
# 사업별 배분율 합계 100% 이하 유지
PROJECT_MAPS = [
    ("demo-m-01", "demo-p-01", "demo-cl-01", "demo-a-02", 40, 10, "STANDBY"),
    ("demo-m-02", "demo-p-01", "demo-cl-02", "demo-a-04", 35, 12, "STANDBY"),
    ("demo-m-03", "demo-p-01", "demo-cl-05", "demo-a-08", 25, 10, "STANDBY"),
    ("demo-m-04", "demo-p-02", "demo-cl-03", "demo-a-05", 60, 15, "STANDBY"),
    ("demo-m-05", "demo-p-02", "demo-cl-06", "demo-a-09", 40, 15, "STANDBY"),
    ("demo-m-06", "demo-p-03", "demo-cl-08", "demo-a-11", 50, 20, "STANDBY"),
    ("demo-m-07", "demo-p-03", "demo-cl-04", "demo-a-07", 30, 20, "STANDBY"),
    ("demo-m-08", "demo-p-04", "demo-cl-01", "demo-a-01", 50, 10, "BILLED"),
    ("demo-m-09", "demo-p-04", "demo-cl-02", "demo-a-03", 30, 12, "COMPLETED"),
    ("demo-m-10", "demo-p-04", "demo-cl-07", "demo-a-10", 20, 10, "STANDBY"),
]


def seed():
    if not init_db():
        print("✗ DB에 연결할 수 없습니다 — DATABASE_URL 확인")
        sys.exit(1)

    db = SessionLocal()
    created = skipped = 0

    def add_if_absent(model, pk, factory):
        nonlocal created, skipped
        if db.get(model, pk) is not None:
            skipped += 1
            return
        db.add(factory())
        created += 1

    try:
        for u in USERS:
            add_if_absent(
                User, u["user_id"],
                lambda u=u: User(
                    user_id=u["user_id"], email=u["email"], name=u["name"],
                    role=u["role"], status="ACTIVE", auth_provider="NAVER_WORKS",
                ),
            )
        db.flush()

        for cid, ctype, name, cstatus, mgr, region, report_yn in CLIENTS:
            num = cid[-2:]
            add_if_absent(
                Client, cid,
                lambda: Client(
                    client_id=cid, client_type=ctype, company_name=name,
                    biz_reg_no="123-45-678{0}".format(num), region=region,
                    address="{0} 데모로 {1}".format(region, int(num)),
                    ceo_name="대표{0}".format(num),
                    ceo_contact_phone="010-1000-00{0}".format(num),
                    main_contact_name="담당{0}".format(num),
                    main_contact_phone="010-2000-00{0}".format(num),
                    main_contact_email="contact{0}@{1}.example.com".format(num, cid),
                    contract_status=cstatus,
                    contract_date=MONTH_START - timedelta(days=200 + int(num) * 10),
                    keyman="키맨{0}".format(num), manager_id=mgr, report_yn=report_yn,
                ),
            )
        db.flush()

        for hid, cid, mgr, days_ago, atype, stage, istatus, prio, title in HISTORIES:
            activity_date = NOW - timedelta(days=days_ago, hours=int(hid[-2:]) % 8)
            add_if_absent(
                ActivityHistory, hid,
                lambda: ActivityHistory(
                    history_id=hid, client_id=cid, manager_id=mgr, created_by=mgr,
                    activity_date=activity_date, activity_type=atype,
                    retention_stage=stage, issue_status=istatus, priority=prio,
                    due_date=(NOW + timedelta(days=3)).date() if istatus in ("OPEN", "IN_PROGRESS") else None,
                    title=title, content="{0} — 데모 데이터".format(title),
                ),
            )
        db.flush()

        for coid, hid, mgr, ctype, content in COMMENTS:
            add_if_absent(
                IssueComment, coid,
                lambda: IssueComment(
                    comment_id=coid, history_id=hid, manager_id=mgr,
                    comment_type=ctype, content=content,
                ),
            )

        for sid, cid, mgr, day, hour, stype, title, sstatus in SCHEDULES:
            add_if_absent(
                Schedule, sid,
                lambda: Schedule(
                    schedule_id=sid, client_id=cid, manager_id=mgr,
                    schedule_type=stype, title=title, start_at=_day(day, hour),
                    end_at=_day(day, hour + 1), status=sstatus,
                    location="현장 방문지" if stype == "SITE_VISIT" else None,
                ),
            )

        for cid, rtype, due_day, channel in SUBSCRIPTIONS:
            existing = (
                db.query(ReportSubscription)
                .filter(ReportSubscription.client_id == cid, ReportSubscription.report_type == rtype)
                .first()
            )
            if existing:
                skipped += 1
            else:
                db.add(
                    ReportSubscription(
                        client_id=cid, report_type=rtype, channel=channel,
                        due_day=due_day, active="Y",
                    )
                )
                # 대표 수신자 1명 (TO)
                db.add(
                    ReportRecipient(
                        client_id=cid, name="보고서 수신자",
                        email="report.{0}@example.com".format(cid), cc_yn="N",
                    )
                )
                created += 1
        db.flush()

        for rid, cid, rtype, rstatus, due_day, mgr in REPORTS:
            sent = rstatus in ("SENT", "CONFIRMED")
            add_if_absent(
                ReportDelivery, rid,
                lambda: ReportDelivery(
                    report_id=rid, client_id=cid, period=PERIOD, report_type=rtype,
                    status=rstatus, due_date=_day(due_day).date(), manager_id=mgr,
                    sent_at=_day(due_day, 17) if sent else None,
                    sent_channel="EMAIL" if sent else None,
                    confirmed_at=_day(due_day, 18) if rstatus == "CONFIRMED" else None,
                    confirm_basis="회신메일" if rstatus == "CONFIRMED" else None,
                ),
            )
        db.flush()

        for did, cid, dtype, title, rid in DOCUMENTS:
            add_if_absent(
                Document, did,
                lambda: Document(
                    doc_id=did, client_id=cid, doc_type=dtype, title=title,
                    file_url="demo/{0}.pdf".format(did),  # 더미 경로
                    version=1, report_id=rid, uploaded_by="demo-user-01",
                ),
            )
        db.flush()

        # 보고서 최신 파일 연결
        for did, _cid, _dtype, _title, rid in DOCUMENTS:
            if rid:
                delivery = db.get(ReportDelivery, rid)
                if delivery is not None and delivery.doc_id is None:
                    delivery.doc_id = did

        # --- P2: 자산 (SCR-04) — ASSET_ENC_KEY 없으면 인증정보는 비움 ---
        enc_ok = crypto.encryption_available()
        for aid, cid, group, atype, qty, spec, tel, agency, auth, login, secret in ASSETS:
            add_if_absent(
                Asset, aid,
                lambda aid=aid, cid=cid, group=group, atype=atype, qty=qty, spec=spec,
                tel=tel, agency=agency, auth=auth, login=login, secret=secret: Asset(
                    asset_id=aid, client_id=cid, asset_group=group, asset_type=atype,
                    quantity=qty, main_spec=spec, telemetry_yn=tel, status="ACTIVE",
                    agency_name=agency, auth_type=auth, login_id=login,
                    location_info="현장 {0}".format(aid[-2:]),
                    usage_purpose="관제 연동" if tel == "Y" else None,
                    login_password=(
                        crypto.encrypt(secret) if enc_ok and secret and auth == "ID_PW" else None
                    ),
                    api_token=(
                        crypto.encrypt(secret) if enc_ok and secret and auth == "API_KEY" else None
                    ),
                ),
            )
        db.flush()

        # --- P2: 감축 사업 (SCR-06) — 상태 분포·단가 입력/미입력 혼합 ---
        for pid, name, reg, status, credits, price, cycle, issue_days, issued, mgr in PROJECTS:
            issue_date = (NOW + timedelta(days=issue_days)).date() if issue_days is not None else None
            add_if_absent(
                Project, pid,
                lambda pid=pid, name=name, reg=reg, status=status, credits=credits,
                price=price, cycle=cycle, issue_date=issue_date, issued=issued, mgr=mgr: Project(
                    project_id=pid, project_name=name, reg_code=reg, project_status=status,
                    reg_date=(NOW - timedelta(days=400)).date(),
                    credit_start_date=(NOW - timedelta(days=365)).date(),
                    credit_end_date=(NOW + timedelta(days=365 * 4)).date(),
                    credit_period_type="고정형",
                    mon_start_date=(NOW - timedelta(days=180)).date(),
                    mon_end_date=(NOW + timedelta(days=180)).date(),
                    mon_cycle=cycle, expected_issue_date=issue_date,
                    expected_credits=credits, unit_price=price, price_source="MANUAL",
                    issued_credits=issued,
                    issued_at=issue_date if status == "발급완료" else None,
                    manager_id=mgr,
                ),
            )
        db.flush()

        # --- P2: 참여 고객사 매핑 (SCR-06/07) — expected_amount는 §10.3 산식으로 적재 ---
        project_by_id = {p[0]: p for p in PROJECTS}
        for mid, pid, cid, aid, ratio, fee, sstatus in PROJECT_MAPS:
            credits, price = project_by_id[pid][4], project_by_id[pid][5]
            add_if_absent(
                ProjectClientMap, mid,
                lambda mid=mid, pid=pid, cid=cid, aid=aid, ratio=ratio, fee=fee,
                sstatus=sstatus, credits=credits, price=price: ProjectClientMap(
                    map_id=mid, project_id=pid, client_id=cid, asset_id=aid,
                    allocation_ratio=ratio, success_fee_rate=fee,
                    expected_amount=compute_expected_amount(credits, ratio, price, fee),
                    settlement_status=sstatus,
                    billed_at=NOW - timedelta(days=10) if sstatus in ("BILLED", "COMPLETED") else None,
                    billed_by="demo-user-01" if sstatus in ("BILLED", "COMPLETED") else None,
                    completed_at=NOW - timedelta(days=3) if sstatus == "COMPLETED" else None,
                    completed_by="demo-user-01" if sstatus == "COMPLETED" else None,
                    paid_amount=(
                        compute_expected_amount(credits, ratio, price, fee)
                        if sstatus == "COMPLETED" else None
                    ),
                    payment_type="FULL" if sstatus == "COMPLETED" else None,
                ),
            )
        db.flush()

        db.commit()
        print("✓ 데모 시드 완료 — 신규 {0}건, 기존 유지 {1}건 (period={2})".format(created, skipped, PERIOD))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
