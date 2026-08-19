"""폴더명 규칙 교정(reconcile) 배치 — preview/apply 안전 불변식 검증.

불변식: 삭제 없음·move만·미리보기 후 적용·건별 실패 격리·confinement·멱등·NULL 스킵.
Dropbox·root는 monkeypatch로 결정적으로 통제하고, 실제 이동/삭제는 가짜로 대체한다.
"""

import models
from services import client_folders, dropbox_storage

PREVIEW = "/api/v1/batch/reconcile-dropbox-folders/preview"
APPLY = "/api/v1/batch/reconcile-dropbox-folders/apply"


def _clear_all_folders(db):
    """세션 공유 DB 격리 — 전역 카운트가 이번 테스트 시드만 반영하도록 폴더 경로 초기화."""
    db.query(models.Client).update({models.Client.dropbox_folder: None})
    db.commit()


def _mk(db, region, name, folder, ctype="TRANSPORT"):
    c = models.Client(
        client_type=ctype, company_name=name, region=region, dropbox_folder=folder
    )
    db.add(c)
    db.flush()
    return c.client_id


def _configure_dropbox(monkeypatch):
    """Dropbox 설정됨 + root='' 로 고정 — 실제 네트워크·SDK 접근 없음."""
    monkeypatch.setattr(dropbox_storage, "is_configured", lambda: True)
    monkeypatch.setattr(dropbox_storage, "root", lambda: "")


def _guard_no_delete(monkeypatch):
    """삭제 절대 없음 — delete 호출 시 즉시 테스트 실패로 검출."""
    def _boom(*a, **k):
        raise AssertionError("dropbox_storage.delete가 호출됨 — reconcile은 삭제 금지")

    monkeypatch.setattr(dropbox_storage, "delete", _boom)


# ---------------------------------------------------------------------------
# preview — 읽기 전용(이동/삭제 0회), 판정·카운트 정확, NULL 제외
# ---------------------------------------------------------------------------
def test_preview_classifies_and_never_moves(client, admin_headers, monkeypatch):
    _configure_dropbox(monkeypatch)
    _guard_no_delete(monkeypatch)

    move_calls = []
    monkeypatch.setattr(
        dropbox_storage, "move",
        lambda *a, **k: move_calls.append(a) or a[1],  # 호출되면 기록(=검출)
    )

    db = models.SessionLocal()
    try:
        _clear_all_folders(db)
        # (a) 이미 규칙 일치
        ids = {}
        ids["skip"] = _mk(db, "서울", "Aco", "/서울_Aco_운수")
        # (b) 루트 평탄화 필요 — leaf 동일 → root_changed
        ids["root"] = _mk(db, "서울", "Bco", "/Hooxi-CMS/서울_Bco_운수")
        # (c) 개명 — leaf 상이 → name_changed
        ids["name"] = _mk(db, "서울", "Cco", "/서울_Old_운수")
        # (d) 다른 고객사가 목표 경로 점유 → conflict + 점유자 자신은 skip
        ids["conf"] = _mk(db, "부산", "Dco", "/부산_Old_운수")
        _mk(db, "부산", "Dco", "/부산_Dco_운수")  # 점유자(자기 규칙과 일치 → skip)
        # (e) NULL — 대상 제외
        _mk(db, "대구", "Eco", None)
        db.commit()
        by_id = {k: v for k, v in ids.items()}
    finally:
        db.close()

    resp = client.post(PREVIEW, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # move는 단 한 번도 호출되지 않아야 한다(읽기 전용)
    assert move_calls == []

    # NULL 제외 → total 5, move 2, conflict 1, skip 2
    assert body["total"] == 5
    assert body["move_count"] == 2
    assert body["conflict_count"] == 1
    assert body["skip_count"] == 2

    items = {it["client_id"]: it for it in body["items"]}
    # NULL 고객사는 items에 없음
    assert all(it["current_path"] for it in body["items"])

    assert items[by_id["skip"]]["action"] == "skip_match"
    assert items[by_id["root"]]["action"] == "move"
    assert items[by_id["root"]]["reason"] == "root_changed"
    assert items[by_id["root"]]["proposed_path"] == "/서울_Bco_운수"
    assert items[by_id["name"]]["action"] == "move"
    assert items[by_id["name"]]["reason"] == "name_changed"
    assert items[by_id["conf"]]["action"] == "conflict"


def test_preview_requires_dropbox_configured(client, admin_headers):
    # conftest는 Dropbox env 미설정 → 503 게이트
    assert dropbox_storage.is_configured() is False
    resp = client.post(PREVIEW, headers=admin_headers)
    assert resp.status_code == 503


def test_preview_secret_gate(client):
    # 토큰·시크릿 없음 → 403
    assert client.post(PREVIEW).status_code == 403


# ---------------------------------------------------------------------------
# apply — move만 수행, moved/conflicts/failed 격리, 삭제 없음, 감사 로그, 멱등
# ---------------------------------------------------------------------------
def test_apply_moves_isolates_and_audits(client, admin_headers, monkeypatch):
    _configure_dropbox(monkeypatch)
    _guard_no_delete(monkeypatch)

    moved_pairs = []

    def _fake_move(src, dst):
        # dst 마커로 성공/conflict/일반예외를 분기해 격리 정확성을 검증
        if "Dbxconf" in dst:
            raise dropbox_storage.DropboxConflict(dst)
        if "Failing" in dst:
            raise RuntimeError("boom")
        moved_pairs.append((src, dst))
        return dst

    monkeypatch.setattr(dropbox_storage, "move", _fake_move)

    db = models.SessionLocal()
    try:
        _clear_all_folders(db)
        m_ok = _mk(db, "서울", "Moveok", "/old_ok")
        m_conf = _mk(db, "서울", "Dbxconf", "/old_conf")
        m_fail = _mk(db, "서울", "Failing", "/old_fail")
        db.commit()
    finally:
        db.close()

    before_audit = _count_audit(models.SessionLocal())

    resp = client.post(APPLY, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["total_candidates"] == 3
    assert body["moved"] == 1
    assert body["conflicts"] == 1
    assert body["failed"] == 1

    # move 성공 건만 dropbox_folder 갱신, 나머지는 원본 유지
    db = models.SessionLocal()
    try:
        assert db.get(models.Client, m_ok).dropbox_folder == "/서울_Moveok_운수"
        assert db.get(models.Client, m_conf).dropbox_folder == "/old_conf"
        assert db.get(models.Client, m_fail).dropbox_folder == "/old_fail"

        # 성공 건 CLIENT_FOLDER_RENAME 감사 + 요약 DROPBOX_RECONCILE 감사
        renames = (
            db.query(models.AuditLog)
            .filter(
                models.AuditLog.action == "CLIENT_FOLDER_RENAME",
                models.AuditLog.target_id == m_ok,
            )
            .all()
        )
        assert len(renames) == 1
        assert renames[0].new_value == "/old_ok -> /서울_Moveok_운수"
        summary = (
            db.query(models.AuditLog)
            .filter(models.AuditLog.action == "DROPBOX_RECONCILE")
            .order_by(models.AuditLog.created_at.desc())
            .first()
        )
        assert summary is not None
        assert "moved=1" in summary.new_value
        assert "conflicts=1" in summary.new_value
        assert "failed=1" in summary.new_value
    finally:
        db.close()

    # 실제 이동은 성공 건 1회뿐
    assert moved_pairs == [("/old_ok", "/서울_Moveok_운수")]


def test_apply_is_idempotent(client, admin_headers, monkeypatch):
    _configure_dropbox(monkeypatch)
    _guard_no_delete(monkeypatch)
    monkeypatch.setattr(dropbox_storage, "move", lambda src, dst: dst)  # 전건 성공

    db = models.SessionLocal()
    try:
        _clear_all_folders(db)
        _mk(db, "서울", "Idem", "/Hooxi-CMS/서울_Idem_운수")  # 루트 평탄화 필요
        _mk(db, "부산", "Kco", "/부산_Kco_운수")  # 이미 일치
        db.commit()
    finally:
        db.close()

    r1 = client.post(APPLY, headers=admin_headers)
    assert r1.status_code == 200
    assert r1.json()["moved"] == 1

    # 재적용 없이 preview 재호출 → 전부 skip_match(멱등)
    r2 = client.post(PREVIEW, headers=admin_headers)
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["move_count"] == 0
    assert b2["conflict_count"] == 0
    assert all(it["action"] == "skip_match" for it in b2["items"])

    # apply 재호출도 대상 0
    r3 = client.post(APPLY, headers=admin_headers)
    assert r3.json()["total_candidates"] == 0
    assert r3.json()["moved"] == 0


def test_apply_requires_dropbox_configured(client, admin_headers):
    assert dropbox_storage.is_configured() is False
    resp = client.post(APPLY, headers=admin_headers)
    assert resp.status_code == 503


def _count_audit(db):
    try:
        return db.query(models.AuditLog).count()
    finally:
        db.close()
