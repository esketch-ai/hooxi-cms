"""세그먼트 mail-merge — 수신자별 개별 첨부, FAIL 격리, 가드/검증."""

import json

import models
from services import client_folders, dropbox_storage, email_service
from services import storage as storage_mod

API = "/api/v1"


def _mk_client(client, headers, name, region, email):
    resp = client.post(
        API + "/clients", headers=headers,
        json={"client_type": "TRANSPORT", "company_name": name,
              "region": region, "main_contact_email": email},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["client_id"]


def test_mailmerge_per_recipient_with_fail_isolation(client, admin_headers, monkeypatch):
    monkeypatch.setenv("GMAIL_SENDER", "s@x.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "p")
    monkeypatch.setattr(email_service, "is_configured", lambda: True)
    calls = []
    monkeypatch.setattr(
        email_service, "send_mail",
        lambda **kw: calls.append({"to": kw["to"], "atts": kw["attachments"]})
        or {"sender": "x", "recipients": kw["to"]},
    )
    monkeypatch.setattr(dropbox_storage, "is_configured", lambda: True)
    monkeypatch.setattr(storage_mod, "read_file", lambda url: b"MERGE")

    # A는 개별 파일 있음((경로,size)), B는 없음(None) → B는 FAIL 격리
    def fake_resolve(db, c, code, name_contains=None):
        return ("/{0}_xxxx/보고서/r.pdf".format(c.company_name), 100) if c.company_name == "병합A" else None

    monkeypatch.setattr(client_folders, "resolve_recipient_file", fake_resolve)

    _mk_client(client, admin_headers, "병합A", "병합존", "a@x.com")
    _mk_client(client, admin_headers, "병합B", "병합존", "b@x.com")

    resp = client.post(
        API + "/segments/send", headers=admin_headers,
        json={"criteria": {"region": ["병합존"]}, "merge_folder_code": "REPORT"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["sent_count"] == 1  # A만 발송
    assert body["failed_count"] == 1  # B는 개별 파일 없음 → FAIL
    assert len(calls) == 1
    # A의 첨부는 개별 파일 1개(공통 없음)
    assert [a[0] for a in calls[0]["atts"]] == ["r.pdf"]


def test_mailmerge_stores_rule_and_requires_selection(client, admin_headers, monkeypatch):
    # email 설정(503 게이트 통과) — 가드/검증(422)에 도달하도록
    monkeypatch.setenv("GMAIL_SENDER", "s@x.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "p")
    monkeypatch.setattr(email_service, "is_configured", lambda: True)
    monkeypatch.setattr(dropbox_storage, "is_configured", lambda: True)  # merge 503 가드 통과

    # 가드: doc_ids·dropbox_paths·merge_folder_code 모두 없으면 422
    resp = client.post(
        API + "/segments/send", headers=admin_headers,
        json={"criteria": {"region": ["없는존"]}},
    )
    assert resp.status_code == 422

    # 잘못된 merge_folder_code → 422 (validate_active_code)
    resp = client.post(
        API + "/segments/send", headers=admin_headers,
        json={"criteria": {"region": ["없는존"]}, "merge_folder_code": "NOPE"},
    )
    assert resp.status_code == 422

    # 정상 merge 규칙 → 대상 0건이어도 발송 성공 + merge_rule 스냅샷 저장
    resp = client.post(
        API + "/segments/send", headers=admin_headers,
        json={"criteria": {"region": ["없는존"]}, "merge_folder_code": "REPORT",
              "merge_name_contains": "2026-07"},
    )
    assert resp.status_code == 200, resp.text
    send_id = resp.json()["send_id"]
    db = models.SessionLocal()
    try:
        row = db.get(models.SegmentSend, send_id)
        rule = json.loads(row.merge_rule)
        assert rule["folder_code"] == "REPORT" and rule["name_contains"] == "2026-07"
    finally:
        db.close()
