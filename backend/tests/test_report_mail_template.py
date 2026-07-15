"""보고서 메일 템플릿 (B3+B4) — 전역 기본(tb_config) + 고객사(구독)별 오버라이드.

검증 포인트:
- 기본값 렌더 == 기존 하드코딩 발송 문구 (바이트 단위 동일 — 회귀 없음)
- tb_config(report_mail_subject/report_mail_body) 커스텀 템플릿 → 발송 반영
- 구독 오버라이드(mail_subject/mail_body) 우선, 미설정 고객사는 전역 기본
- {고객사명} 등 변수 치환 + 미지원 {없는변수}는 원문 유지 (정규식 치환)
- tb_config 값 검증: 빈 문자열/비문자열 422
"""

import io
import json

from services import email_service

API = "/api/v1"
PERIOD = "2027-03"  # 타 테스트 모듈과 겹치지 않는 전용 기간
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


def _create_client(client, headers, name, email, subscription):
    resp = client.post(
        API + "/clients",
        headers=headers,
        json={
            "client_type": "TRANSPORT",
            "company_name": name,
            "contract_status": "ACTIVE",
            "report_yn": "Y",
            "main_contact_email": email,
            "manager_id": "u-manager",
            "subscription": subscription,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["client_id"]


def _report_of(client, headers, client_id):
    resp = client.get(API + "/reports", params={"period": PERIOD}, headers=headers)
    assert resp.status_code == 200, resp.text
    mine = [i for i in resp.json()["items"] if i["client_id"] == client_id]
    assert len(mine) == 1
    return mine[0]


def _send_and_capture(client, headers, report_id, monkeypatch):
    """send_mail 모킹으로 제목/본문 캡처 — 발송 성공 200 확인."""
    monkeypatch.setenv("GMAIL_SENDER", "hooxi12345@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "app-password")
    sent = {}

    def fake_send_mail(to, subject, body, cc=None, attachments=None, reply_to=None, html=False):
        sent.update({"to": to, "subject": subject, "body": body})
        return {"sender": "hooxi12345@gmail.com", "recipients": list(to) + list(cc or [])}

    monkeypatch.setattr(email_service, "send_mail", fake_send_mail)
    resp = client.post(API + "/reports/{0}/send".format(report_id), headers=headers)
    assert resp.status_code == 200, resp.text
    return sent


def test_setup_clients_and_reports(client, staff_headers):
    # plain: 오버라이드 없는 고객사 (전역 기본/tb_config 적용 대상)
    S["plain"] = _create_client(
        client, staff_headers, "템플릿기본운수", "plain@mail-template.example.com",
        {"report_type": "월간 운행 보고서", "channel": "EMAIL", "due_day": 25},
    )
    # override: 구독별 메일 템플릿 오버라이드 고객사
    S["override"] = _create_client(
        client, staff_headers, "템플릿지정운수", "override@mail-template.example.com",
        {
            "report_type": "월간 운행 보고서", "channel": "EMAIL", "due_day": 25,
            "mail_subject": "[지정] {고객사명} {기간} 보고서",
            "mail_body": "{고객사명} / {담당자명} / {없는변수} / {보고서유형}",
        },
    )
    resp = client.post(
        API + "/reports/generate", params={"period": PERIOD}, headers=staff_headers
    )
    assert resp.status_code == 200, resp.text

    # 구독 오버라이드 저장 확인 (상세 응답 노출)
    detail = client.get(API + "/clients/" + S["override"], headers=staff_headers).json()
    assert detail["subscriptions"][0]["mail_subject"] == "[지정] {고객사명} {기간} 보고서"

    # 발송 준비: 파일 업로드 (STANDBY → WRITING, 파일 없으면 발송 409)
    for key in ("plain", "override"):
        row = _report_of(client, staff_headers, S[key])
        S[key + "_report"] = row["report_id"]
        resp = client.post(
            API + "/reports/{0}/file".format(row["report_id"]),
            headers=staff_headers,
            files={"file": ("report.pdf", io.BytesIO(b"PDF-TPL"), "application/pdf")},
        )
        assert resp.status_code == 201, resp.text


def test_default_render_matches_legacy_hardcoded(client, staff_headers, monkeypatch):
    """tb_config·구독 오버라이드 미설정 → 기존 하드코딩 문구와 바이트 단위 동일 (회귀 없음)."""
    sent = _send_and_capture(client, staff_headers, S["plain_report"], monkeypatch)
    assert sent["subject"] == "[Hooxi Partners] 템플릿기본운수 3월 월간 운행 보고서 보고서"
    assert sent["body"] == (
        "안녕하세요, 템플릿기본운수 담당자님.\n\n"
        "2027년 3월 월간 운행 보고서 보고서를 첨부와 같이 발송드립니다.\n"
        "확인 부탁드리며, 문의 사항은 본 메일에 회신해 주세요.\n\n"
        "감사합니다.\nHooxi Partners 드림"
    )


def test_subscription_override_wins(client, staff_headers, monkeypatch):
    """구독 오버라이드 우선 — {고객사명} 치환 + 미지원 {없는변수} 원문 유지."""
    sent = _send_and_capture(client, staff_headers, S["override_report"], monkeypatch)
    assert sent["subject"] == "[지정] 템플릿지정운수 {0} 보고서".format(PERIOD)
    # 담당자명 = 고객사 담당 매니저(u-manager, 팀장), 미지원 변수는 원문 유지
    assert sent["body"] == "템플릿지정운수 / 팀장 / {없는변수} / 월간 운행 보고서"


def test_config_template_applies_to_plain_client(client, staff_headers, admin_headers, monkeypatch):
    """tb_config 전역 커스텀 템플릿 저장 → 오버라이드 없는 고객사 발송에 반영."""
    resp = client.put(
        API + "/config/report_mail_subject",
        headers=admin_headers,
        json={"config_value": json.dumps("[전역] {고객사명} {연도}-{월} {보고서유형}")},
    )
    assert resp.status_code == 200, resp.text
    resp = client.put(
        API + "/config/report_mail_body",
        headers=admin_headers,
        json={"config_value": json.dumps("{기간} 보고서입니다. 담당: {담당자명}")},
    )
    assert resp.status_code == 200, resp.text

    sent = _send_and_capture(client, staff_headers, S["plain_report"], monkeypatch)
    assert sent["subject"] == "[전역] 템플릿기본운수 2027-3 월간 운행 보고서"
    assert sent["body"] == "{0} 보고서입니다. 담당: 팀장".format(PERIOD)

    # 구독 오버라이드 고객사는 여전히 오버라이드가 우선 (전역 무시)
    sent = _send_and_capture(client, staff_headers, S["override_report"], monkeypatch)
    assert sent["subject"] == "[지정] 템플릿지정운수 {0} 보고서".format(PERIOD)


def test_config_default_exposed_and_validated(client, admin_headers):
    """미저장 시 기본값(미저장) 노출 + 빈 문자열/비문자열 422."""
    # report_mail_body는 위 테스트에서 저장됨 — 별도 키로 기본값 노출 확인 불가하므로
    # 목록에서 두 키가 모두 존재하는지만 확인 (subject/body 저장분 포함)
    keys = {c["config_key"] for c in client.get(API + "/config", headers=admin_headers).json()}
    assert {"report_mail_subject", "report_mail_body"} <= keys

    resp = client.put(
        API + "/config/report_mail_subject",
        headers=admin_headers,
        json={"config_value": json.dumps("   ")},
    )
    assert resp.status_code == 422
    resp = client.put(
        API + "/config/report_mail_body",
        headers=admin_headers,
        json={"config_value": json.dumps(["배열은", "불가"])},
    )
    assert resp.status_code == 422
