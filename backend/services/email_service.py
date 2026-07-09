"""Gmail SMTP 발송 모듈 — CR-2 (보고서 발송 대표 계정: 지메일).

- env: GMAIL_SENDER / GMAIL_APP_PASSWORD (2단계 인증 후 앱 비밀번호 발급)
- 발신 표시명 "Hooxi Partners" 고정 + Reply-To 담당자 @hooxipartners.com (CR-2 완화책)
- 일 발송 한도: 개인 Gmail 500통/일 — 일괄 발송 UI에서 한도 문구 표기(프론트 책임)
"""

import mimetypes
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from typing import List, Optional, Sequence, Tuple

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # SSL
SENDER_DISPLAY_NAME = "Hooxi Partners"

# 첨부: (filename, content bytes, mime type 예: "application/pdf" — None이면 추정)
Attachment = Tuple[str, bytes, Optional[str]]


class EmailConfigError(RuntimeError):
    """Gmail SMTP 환경변수 미설정."""


def _get_credentials() -> Tuple[str, str]:
    sender = os.getenv("GMAIL_SENDER")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    if not sender or not app_password:
        raise EmailConfigError(
            "Gmail SMTP가 설정되지 않았습니다. "
            "GMAIL_SENDER / GMAIL_APP_PASSWORD 환경변수를 설정하세요 (CR-2). "
            "앱 비밀번호는 발신 계정의 2단계 인증 활성화 후 발급합니다."
        )
    return sender, app_password


def is_configured() -> bool:
    return bool(os.getenv("GMAIL_SENDER") and os.getenv("GMAIL_APP_PASSWORD"))


def send_mail(
    to: List[str],
    subject: str,
    body: str,
    cc: Optional[List[str]] = None,
    attachments: Optional[Sequence[Attachment]] = None,
    reply_to: Optional[str] = None,
    html: bool = False,
) -> dict:
    """메일 발송. 반환: {"sender", "recipients"} — 실패 시 예외 전파(호출부가 send_log 기록).

    reply_to: 담당자의 @hooxipartners.com 주소 — 고객 회신은 회사 메일로 수신 (CR-2)
    """
    sender, app_password = _get_credentials()

    if not to:
        raise ValueError("TO 수신자가 최소 1명 필요합니다 (R2-B5)")

    msg = EmailMessage()
    msg["From"] = formataddr((SENDER_DISPLAY_NAME, sender))
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Subject"] = subject

    if html:
        msg.set_content("HTML 메일입니다. HTML을 지원하는 클라이언트에서 확인하세요.")
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)

    for filename, content, mime_type in attachments or []:
        if not mime_type:
            mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        maintype, _, subtype = mime_type.partition("/")
        msg.add_attachment(
            content, maintype=maintype, subtype=subtype or "octet-stream", filename=filename
        )

    recipients = list(to) + list(cc or [])
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(msg, from_addr=sender, to_addrs=recipients)

    return {"sender": sender, "recipients": recipients}
