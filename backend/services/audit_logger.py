"""중앙 집중식 감사 로그 기록기 — R2-E6 민감 정보 보호 로직 포함.

모든 감사 기록은 이 모듈을 경유한다. action·target_type 값은 기존 기록·프론트
감사 로그 탭 라벨과의 정합을 위해 절대 임의 변경하지 않는다:

  REVEAL_AUTH/ASSET · SETTLEMENT_CHANGE/PROJECT_CLIENT_MAP · REPORT_VIEW/REPORT
  CONFIG_CHANGE/CONFIG · KAKAO_APPROVAL/KAKAO_CONTACT · DOCUMENT_DOWNLOAD/DOCUMENT
  USER_APPROVE·USER_ROLE_CHANGE·USER_DEACTIVATE·USER_PIN_RESET/USER

커밋은 호출부 책임(기존 패턴 유지) — 본 모듈은 db.add까지만 수행한다.
"""

from typing import Optional

from sqlalchemy.orm import Session

from models import AuditLog

# 값 원문에 포함되면 안 되는 민감 패턴 — 매칭 시 값 전체를 가림 (R2-E6 안전망)
SENSITIVE_KEYWORDS = [
    "password",
    "token",
    "secret",
    "api_key",
    "private_key",
    "credential",
    "auth_token",
]


def redact_sensitive_info(value: Optional[str]) -> Optional[str]:
    """민감 정보 자동 redact (R2-E6 준수)."""
    if not value:
        return None
    lower_value = value.lower()
    if any(keyword in lower_value for keyword in SENSITIVE_KEYWORDS):
        return "[REDACTED]"
    return value


class AuditLogger:
    """중앙 집중식 감사 로그 기록기."""

    @staticmethod
    def log_action(
        db: Session,
        actor_id: str,
        action: str,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
    ) -> AuditLog:
        """감사 로그 기록 — 값은 redact 후 저장, created_at은 모델 default(utcnow)."""
        audit_log = AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            old_value=redact_sensitive_info(old_value),
            new_value=redact_sensitive_info(new_value),
        )
        db.add(audit_log)
        return audit_log

    # ── 자산 (SCR-04) ──────────────────────────────────────────────
    @staticmethod
    def reveal_auth_access(db: Session, actor_id: str, asset_id: str) -> AuditLog:
        """인증 정보 열람 — 값은 절대 기록 금지(누가·언제·어떤 자산만)."""
        return AuditLogger.log_action(
            db, actor_id, "REVEAL_AUTH", target_type="ASSET", target_id=asset_id
        )

    # ── 정산 (SCR-07) ──────────────────────────────────────────────
    @staticmethod
    def settlement_change(
        db: Session, actor_id: str, map_id: str, old_status: str, new_status: str
    ) -> AuditLog:
        """정산 상태 변경 — 금액 원문 기록 금지, 상태만."""
        return AuditLogger.log_action(
            db,
            actor_id,
            "SETTLEMENT_CHANGE",
            target_type="PROJECT_CLIENT_MAP",
            target_id=map_id,
            old_value=old_status,
            new_value=new_status,
        )

    # ── 보고서 열람 추적 (SCR-12 /r/{token}) ───────────────────────
    @staticmethod
    def report_view(db: Session, actor_id: str, report_id: str) -> AuditLog:
        """열람 링크 접속 — actor는 발송 담당자 기준(무인증 열람, tb_user FK 제약)."""
        return AuditLogger.log_action(
            db, actor_id, "REPORT_VIEW", target_type="REPORT", target_id=report_id
        )

    # ── 문서 (SCR-13) ──────────────────────────────────────────────
    @staticmethod
    def document_download(db: Session, actor_id: str, doc_id: str) -> AuditLog:
        return AuditLogger.log_action(
            db, actor_id, "DOCUMENT_DOWNLOAD", target_type="DOCUMENT", target_id=doc_id
        )

    # ── 내부 사용자 관리 (SCR-14 계정 관리) ─────────────────────────
    @staticmethod
    def user_approve(db: Session, actor_id: str, user_id: str, role: str) -> AuditLog:
        """가입 승인: PENDING → ACTIVE(+role)."""
        return AuditLogger.log_action(
            db,
            actor_id,
            "USER_APPROVE",
            target_type="USER",
            target_id=user_id,
            old_value="PENDING",
            new_value="ACTIVE({0})".format(role),
        )

    @staticmethod
    def user_role_change(
        db: Session, actor_id: str, user_id: str, old_role: str, new_role: str
    ) -> AuditLog:
        return AuditLogger.log_action(
            db,
            actor_id,
            "USER_ROLE_CHANGE",
            target_type="USER",
            target_id=user_id,
            old_value=old_role,
            new_value=new_role,
        )

    @staticmethod
    def user_deactivate(db: Session, actor_id: str, user_id: str, old_status: str) -> AuditLog:
        return AuditLogger.log_action(
            db,
            actor_id,
            "USER_DEACTIVATE",
            target_type="USER",
            target_id=user_id,
            old_value=old_status,
            new_value="INACTIVE",
        )

    @staticmethod
    def user_pin_reset(db: Session, actor_id: str, user_id: str) -> AuditLog:
        """PIN 초기화 — 해시·값은 기록하지 않는다."""
        return AuditLogger.log_action(
            db, actor_id, "USER_PIN_RESET", target_type="USER", target_id=user_id
        )

    # ── 시스템 설정 (SCR-14) ───────────────────────────────────────
    @staticmethod
    def config_change(
        db: Session,
        actor_id: str,
        config_key: str,
        old_value: Optional[str],
        new_value: Optional[str],
    ) -> AuditLog:
        return AuditLogger.log_action(
            db,
            actor_id,
            "CONFIG_CHANGE",
            target_type="CONFIG",
            target_id=config_key,
            old_value=old_value,
            new_value=new_value,
        )

    # ── 카카오 연락처 승인 게이트 (CR-3) ────────────────────────────
    @staticmethod
    def kakao_approval(
        db: Session,
        actor_id: str,
        contact_id: str,
        old_status: Optional[str],
        new_status: Optional[str],
    ) -> AuditLog:
        return AuditLogger.log_action(
            db,
            actor_id,
            "KAKAO_APPROVAL",
            target_type="KAKAO_CONTACT",
            target_id=contact_id,
            old_value=old_status,
            new_value=new_status,
        )
