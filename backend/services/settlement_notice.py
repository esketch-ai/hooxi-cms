"""운수사 정산내역 능동 통지(P3) — 대상 선정·본문 렌더 코어 (스코프 격리 최우선).

settlement_summary(단일 진실원)의 운수사별 롤업 item을 입력으로, 각 운수사에게
'자기 수치만' 담은 이메일 정산 명세 본문을 렌더한다(재계산 없음). 외부(운수사)로
금액 정보를 보내므로 스코프 격리가 최우선 — render_settlement_notice는 그 운수사
1건(client_item)만 입력받아, 타 운수사 수치가 구조적으로 섞일 수 없게 한다.

금액/감축량은 표시용 포맷만 하고 감사에는 기록하지 않는다(R2-E6, 카운트 요약만).
본문에는 반드시 '예정액(확정 아님)' 고지 문구를 포함한다(코드가 항상 부착).
템플릿 치환은 report_sender.render_template(정규식 안전 치환)만 사용한다 —
str.format이면 미지원 {변수}에서 KeyError로 발송이 막히므로 금지(규약).
"""

import html
from datetime import datetime
from typing import List, Optional, Tuple

from routers import common
from services.report_sender import render_template

# tb_config 오버라이드 키(routers/config.py KNOWN_DEFAULTS와 공유 예정) — 미저장 시 아래 기본값.
DEFAULT_SETTLEMENT_NOTICE_SUBJECT = "[Hooxi Partners] {운수사명} 정산 예정 명세 안내"
# 본문은 HTML — {사업내역표}에 사업별 드릴다운 표가 치환된다. 고지 문구는 코드가 항상 부착.
DEFAULT_SETTLEMENT_NOTICE_BODY = (
    "<p>{운수사명} 담당자님, 안녕하세요.</p>"
    "<p>후시파트너스입니다. {기준일} 기준 정산 예정 명세를 안내드립니다.</p>"
    "<ul>"
    "<li>참여 사업수: {참여사업수}</li>"
    "<li>참여 차량수: {참여차량수}</li>"
    "<li>총감축량: {총감축량}</li>"
    "<li>잔여반영감축량: {잔여반영감축량}</li>"
    "<li>예상지급액: {예상지급액}</li>"
    "</ul>"
    "<p>사업별 내역은 아래와 같습니다.</p>"
    "{사업내역표}"
    "<p>문의 사항은 본 메일로 회신 주시기 바랍니다. 감사합니다.</p>"
)

# 필수 고지 — 코드가 렌더 결과에 항상 부착(템플릿 오버라이드와 무관하게 누락 방지).
SETTLEMENT_NOTICE_DISCLAIMER = (
    "본 금액은 정산 예정액이며 확정 금액이 아닙니다. "
    "실제 지급액은 사업 진행·검증 결과에 따라 변동될 수 있습니다."
)
_DISCLAIMER_HTML = (
    '<p style="color:#b45309;font-size:12px">※ ' + html.escape(SETTLEMENT_NOTICE_DISCLAIMER) + "</p>"
)


def settlement_notice_targets(summary_items: List[dict]) -> List[dict]:
    """통지 대상 운수사 — client_id 있는 운수사만((미지정)=None 제외). 입력 순서 유지.

    expected_payout=None(미산정) 운수사도 대상엔 포함한다(본문은 '산정 중' 표기).
    실효 발송 대상(sendable) 판정은 호출부(preview/send)에서 expected_payout·수신여부로 별도 수행.
    """
    return [it for it in summary_items if it.get("client_id") is not None]


def _fmt_money(value: Optional[float]) -> str:
    """예상지급액 표시 — None은 '산정 중', 값은 원화 천단위 포맷(원)."""
    if value is None:
        return "산정 중"
    return "{0:,.0f}원".format(value)


def _fmt_reduction(value: Optional[float]) -> str:
    """감축량 표시 — None은 '-', 값은 천단위 소수 3자리(집계 규약과 동일 자리수)."""
    if value is None:
        return "-"
    return "{0:,.3f}".format(value)


def _project_table_html(projects: List[dict]) -> str:
    """사업별 드릴다운 표(HTML) — 그 운수사 projects만. 사업명은 HTML 이스케이프."""
    header = (
        "<tr>"
        "<th>사업명</th><th>차량수</th><th>총감축량</th>"
        "<th>잔여반영감축량</th><th>예상지급액</th>"
        "</tr>"
    )
    rows = []
    for p in projects:
        rows.append(
            "<tr>"
            "<td>{0}</td><td>{1}</td><td>{2}</td><td>{3}</td><td>{4}</td>"
            "</tr>".format(
                html.escape(p.get("project_name") or ""),
                int(p.get("vehicle_count") or 0),
                _fmt_reduction(p.get("total_reduction")),
                _fmt_reduction(p.get("effective_reduction")),
                _fmt_money(p.get("expected_payout")),
            )
        )
    return (
        '<table border="1" cellpadding="4" cellspacing="0">'
        + header
        + "".join(rows)
        + "</table>"
    )


def render_settlement_notice(
    client_item: dict,
    *,
    subject_tpl: str,
    body_tpl: str,
    now: Optional[datetime] = None,
) -> Tuple[str, str]:
    """정산 명세 메일 (제목, HTML 본문) 렌더 — 스코프 격리 코어.

    client_item(그 운수사 1건 롤업)만 입력받아, 그 운수사 수치·projects만으로 렌더한다.
    타 운수사 데이터는 애초에 함수에 들어오지 않으므로 유출이 구조적으로 불가능하다.
    치환은 render_template(정규식 안전) — 미지원 {변수}는 원문 유지(str.format 금지 규약).
    고지 문구(_DISCLAIMER_HTML)는 템플릿 오버라이드와 무관하게 본문 끝에 항상 부착한다.
    """
    base_date = (now or common.now_kst()).strftime("%Y-%m-%d")
    variables = {
        "운수사명": client_item.get("company_name") or "",
        "기준일": base_date,
        "참여사업수": str(client_item.get("participating_project_count") or 0),
        "참여차량수": str(client_item.get("participating_vehicle_count") or 0),
        "총감축량": _fmt_reduction(client_item.get("total_reduction")),
        "잔여반영감축량": _fmt_reduction(client_item.get("effective_reduction")),
        "예상지급액": _fmt_money(client_item.get("expected_payout")),
        "사업내역표": _project_table_html(client_item.get("projects") or []),
    }
    subject = render_template(subject_tpl, variables)
    body = render_template(body_tpl, variables) + _DISCLAIMER_HTML
    return subject, body
