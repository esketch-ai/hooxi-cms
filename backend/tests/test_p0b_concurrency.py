"""P0-B 상태 변경 동시성 방어 — 조건부 UPDATE(낙관적 동시성) 스모크.

검증 포인트 (시나리오 #5 반려 사항):
- 이슈 상태: 스냅샷 이후 다른 사용자가 상태를 바꾼 경우 409 + 코멘트/감사 미적재(phantom 전이 방지)
- 보고서 상태: 승인 vs 취소 동시 요청 시 늦은 쪽 409 (lost update 소멸)
- CANCELED 부수 필드 원자성: 전이 실패 시 canceled_reason 미기록
- tb_document (report_id, version) 유니크 인덱스 존재 + ensure_schema 멱등
- 업로드 버전 경합: IntegrityError 1회 재계산 재시도로 201 (500 방지)

스레드 없이 결정적으로 재현: get_or_404 스냅샷 직후 같은 커넥션 raw UPDATE로
'다른 사용자의 선행 커밋'을 주입 → 조건부 UPDATE rowcount 0 경로 강제.
"""

import io

from sqlalchemy import func as sa_func, inspect as sa_inspect, text as sa_text

import models
from routers import common as rcommon

API = "/api/v1"
PERIOD = "2027-02"  # 타 테스트 모듈과 겹치지 않는 전용 기간
CONFLICT_DETAIL = "다른 사용자가 방금 상태를 변경했습니다. 새로고침 후 다시 시도하세요"
S = {}  # 테스트 간 공유 상태 (생성된 리소스 id)


def _inject_after_snapshot(monkeypatch, model, target_id, sql, params):
    """get_or_404 스냅샷 직후 raw UPDATE 1회 주입 — 동시 변경 인터리빙 재현."""
    orig = rcommon.get_or_404
    fired = {"done": False}

    def stale_get(db, m, pk, label):
        obj = orig(db, m, pk, label)
        if m is model and pk == target_id and not fired["done"]:
            fired["done"] = True
            db.execute(sa_text(sql), params)
        return obj

    monkeypatch.setattr(rcommon, "get_or_404", stale_get)


# ---------------------------------------------------------------------------
# 1) 이슈 상태 — 스냅샷 불일치 409 + phantom 전이 기록 없음
# ---------------------------------------------------------------------------
def test_setup_issue(client, staff_headers):
    resp = client.post(
        API + "/histories",
        headers=staff_headers,
        json={
            "activity_date": "2027-02-01T09:00:00",
            "activity_type": "ISSUE",
            "title": "동시성 방어 테스트 이슈",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["issue_status"] == "OPEN"
    S["history_id"] = resp.json()["history_id"]


def test_issue_status_stale_conflict_409(client, staff_headers, monkeypatch):
    """스냅샷(OPEN) 이후 다른 사용자가 CLOSED로 바꾼 상황 → 조건부 UPDATE 0건 → 409."""
    _inject_after_snapshot(
        monkeypatch,
        models.ActivityHistory,
        S["history_id"],
        "UPDATE tb_activity_history SET issue_status='CLOSED' WHERE history_id=:h",
        {"h": S["history_id"]},
    )
    resp = client.put(
        API + "/histories/{0}/status".format(S["history_id"]),
        headers=staff_headers,
        json={"issue_status": "IN_PROGRESS", "comment": "경합 시도"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == CONFLICT_DETAIL


def test_issue_no_phantom_comment_or_audit(client, staff_headers):
    """409 반려 건은 실제 전이가 아니므로 코멘트·감사 로그가 없어야 한다."""
    resp = client.get(
        API + "/histories/{0}/comments".format(S["history_id"]), headers=staff_headers
    )
    assert resp.status_code == 200
    assert [c for c in resp.json() if c["comment_type"] == "STATUS_CHANGE"] == []

    db = models.SessionLocal()
    try:
        logs = (
            db.query(models.AuditLog)
            .filter(
                models.AuditLog.action == "ISSUE_STATUS_CHANGE",
                models.AuditLog.target_id == S["history_id"],
            )
            .count()
        )
    finally:
        db.close()
    assert logs == 0


def test_issue_status_normal_path_still_works(client, staff_headers):
    """경합 없는 정상 전이는 그대로 200 + 코멘트 적재 (기존 동작 무손상)."""
    resp = client.put(
        API + "/histories/{0}/status".format(S["history_id"]),
        headers=staff_headers,
        json={"issue_status": "IN_PROGRESS"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["issue_status"] == "IN_PROGRESS"

    resp = client.get(
        API + "/histories/{0}/comments".format(S["history_id"]), headers=staff_headers
    )
    changes = [c for c in resp.json() if c["comment_type"] == "STATUS_CHANGE"]
    assert len(changes) == 1
    assert "OPEN → IN_PROGRESS" in changes[0]["content"]


# ---------------------------------------------------------------------------
# 2) 보고서 상태 — 승인 vs 취소 동시 요청 (늦은 쪽 409, 부수 필드 원자성)
# ---------------------------------------------------------------------------
def test_setup_report(client, staff_headers):
    resp = client.post(
        API + "/clients",
        headers=staff_headers,
        json={
            "client_type": "TRANSPORT",
            # 주의: p1 스모크의 search="테스트운수" 단건 검증과 겹치지 않는 이름
            "company_name": "동시성방어운수",
            "contract_status": "ACTIVE",
            "report_yn": "Y",
            "subscription": {"report_type": "월간 운행 보고서", "channel": "EMAIL", "due_day": 25},
        },
    )
    assert resp.status_code == 201, resp.text
    S["client_id"] = resp.json()["client_id"]

    resp = client.post(
        API + "/reports/generate", params={"period": PERIOD}, headers=staff_headers
    )
    assert resp.status_code == 200, resp.text

    resp = client.get(API + "/reports", params={"period": PERIOD}, headers=staff_headers)
    mine = [i for i in resp.json()["items"] if i["client_id"] == S["client_id"]]
    assert len(mine) == 1
    S["report_id"] = mine[0]["report_id"]

    # 파일 업로드(STANDBY→WRITING) — APPROVED 전이 전제 확보
    resp = client.post(
        API + "/reports/{0}/file".format(S["report_id"]),
        headers=staff_headers,
        files={"file": ("report.pdf", io.BytesIO(b"PDF-P0B"), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["version"] == 1


def test_report_approve_vs_cancel_conflict_409(client, staff_headers, monkeypatch):
    """스냅샷(WRITING) 이후 다른 사용자가 취소한 상황에서 승인 시도 → 409 (오발송 경로 차단)."""
    _inject_after_snapshot(
        monkeypatch,
        models.ReportDelivery,
        S["report_id"],
        "UPDATE tb_report_delivery SET status='CANCELED', canceled_reason='먼저 취소' "
        "WHERE report_id=:r",
        {"r": S["report_id"]},
    )
    resp = client.put(
        API + "/reports/{0}/status".format(S["report_id"]),
        headers=staff_headers,
        json={"status": "APPROVED"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == CONFLICT_DETAIL


def test_report_cancel_conflict_reason_not_written(client, staff_headers, monkeypatch):
    """CANCELED 전이 실패 시 canceled_reason도 원자적으로 미기록 (phantom 사유 방지)."""
    _inject_after_snapshot(
        monkeypatch,
        models.ReportDelivery,
        S["report_id"],
        "UPDATE tb_report_delivery SET status='REVIEW' WHERE report_id=:r",
        {"r": S["report_id"]},
    )
    resp = client.put(
        API + "/reports/{0}/status".format(S["report_id"]),
        headers=staff_headers,
        json={"status": "CANCELED", "canceled_reason": "경합 취소 시도"},
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == CONFLICT_DETAIL

    resp = client.get(API + "/reports/{0}".format(S["report_id"]), headers=staff_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "WRITING"  # 주입분 포함 롤백 — 상태·사유 무변
    assert resp.json().get("canceled_reason") in (None, "")


def test_report_status_normal_path_still_works(client, staff_headers):
    """경합 없는 전이는 기존과 동일 — 검증 순서(사유 422·전이 409)도 보존."""
    # 사유 없는 취소 422 (전이 검증보다 먼저)
    resp = client.put(
        API + "/reports/{0}/status".format(S["report_id"]),
        headers=staff_headers,
        json={"status": "CANCELED"},
    )
    assert resp.status_code == 422
    assert "사유" in resp.json()["detail"]

    # 전이 사전 위반 409 (WRITING→CONFIRMED)
    resp = client.put(
        API + "/reports/{0}/status".format(S["report_id"]),
        headers=staff_headers,
        json={"status": "CONFIRMED"},
    )
    assert resp.status_code == 409
    assert "변경할 수 없습니다" in resp.json()["detail"]

    # 정상 전이: WRITING→REVIEW→APPROVED (승인 성공 시 canceled_reason 없음)
    for status in ("REVIEW", "APPROVED"):
        resp = client.put(
            API + "/reports/{0}/status".format(S["report_id"]),
            headers=staff_headers,
            json={"status": status},
        )
        assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "APPROVED"
    assert resp.json().get("canceled_reason") in (None, "")


# ---------------------------------------------------------------------------
# 3) tb_document (report_id, version) 유니크 — 인덱스 존재·멱등 + 업로드 경합 재시도
# ---------------------------------------------------------------------------
def test_document_unique_index_present_and_idempotent(client):
    target_cols = {"report_id", "version"}

    def _has_unique():
        insp = sa_inspect(models.engine)
        return any(
            set(uc.get("column_names") or []) == target_cols
            for uc in insp.get_unique_constraints("tb_document")
        ) or any(
            ix.get("unique") and set(ix.get("column_names") or []) == target_cols
            for ix in insp.get_indexes("tb_document")
        )

    assert _has_unique()
    models.ensure_schema()  # 재실행해도 예외·중복 생성 없음 (멱등)
    assert _has_unique()


def test_upload_version_conflict_retries_once(client, staff_headers, monkeypatch):
    """동시 업로드가 같은 max+1을 계산한 경합 — IntegrityError 재계산 재시도로 201."""
    import routers.reports as reports_router

    orig = reports_router._next_document_version
    calls = {"n": 0}

    def stale_version(db, report_id):
        calls["n"] += 1
        real = orig(db, report_id)
        if calls["n"] == 1:
            return real - 1  # 이미 사용된 버전(1) — 유니크 충돌 유도
        return real

    monkeypatch.setattr(reports_router, "_next_document_version", stale_version)
    resp = client.post(
        API + "/reports/{0}/file".format(S["report_id"]),
        headers=staff_headers,
        files={"file": ("report_v2.pdf", io.BytesIO(b"PDF-P0B-2"), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    assert calls["n"] == 2  # 1회 재시도 발생
    assert resp.json()["version"] == 2

    # 상세의 문서 버전 히스토리도 중복 없이 1·2
    resp = client.get(API + "/reports/{0}".format(S["report_id"]), headers=staff_headers)
    versions = sorted(d["version"] for d in resp.json()["documents"])
    assert versions == [1, 2]


def test_document_seed_duplicate_version_rejected():
    """유니크 인덱스 실효성 — 같은 (report_id, version) 직접 INSERT는 IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    db = models.SessionLocal()
    try:
        db.add(
            models.Document(
                client_id=S["client_id"],
                doc_type="REPORT",
                title="중복 버전",
                file_url="local:/dup.pdf",
                version=1,
                report_id=S["report_id"],
                uploaded_by="u-staff",
            )
        )
        try:
            db.commit()
            raised = False
        except IntegrityError:
            db.rollback()
            raised = True
    finally:
        db.close()
    assert raised

    # report_id NULL은 유니크 충돌 대상 아님 — 일반 문서(version 기본 1) 다수 허용
    db = models.SessionLocal()
    try:
        max_ver = db.query(sa_func.max(models.Document.version)).filter(
            models.Document.report_id.is_(None)
        ).scalar()
        db.add_all(
            [
                models.Document(
                    doc_type="ETC", title="NULL 보고서 {0}".format(i),
                    file_url="local:/n{0}.pdf".format(i), version=(max_ver or 0) + 1,
                )
                for i in range(2)
            ]
        )
        db.commit()
    finally:
        db.close()
