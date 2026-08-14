"""운수사 정산내역 능동 통지(P3) — 대상 선정·본문 렌더(스코프 격리) 단위 검증.

increment 1 범위: services.settlement_notice 순수 함수만(HTTP·발송 없음).
- 스코프 격리(최중요): render는 그 운수사 1건만 입력받아 타 운수사 수치가 본문에 부재.
- (미지정) client_id=None 제외, expected_payout=None → 본문 '산정 중'.
- '예정액(확정 아님)' 고지 문구 항상 포함.
- render_template 경유 — 미지원 {변수}는 원문 유지(str.format이면 KeyError로 실패).
"""

import models
from services import email_service
from services import settlement_notice as sn

API = "/api/v1"
PROJECTS = API + "/projects"
PREVIEW = API + "/asset-report/settlement-notice/preview"
SEND = API + "/asset-report/settlement-notice/send"
SUMMARY = API + "/asset-report/settlement-summary"

SUBJECT_TPL = sn.DEFAULT_SETTLEMENT_NOTICE_SUBJECT
BODY_TPL = sn.DEFAULT_SETTLEMENT_NOTICE_BODY


def _item(cid, name, payout, projects):
    return {
        "client_id": cid,
        "company_name": name,
        "participating_project_count": len(projects),
        "participating_vehicle_count": sum(p["vehicle_count"] for p in projects),
        "total_reduction": sum(p["total_reduction"] for p in projects),
        "effective_reduction": None,
        "expected_payout": payout,
        "projects": projects,
    }


def _proj(name, vcount, tred, payout):
    return {
        "project_id": "p-" + name,
        "project_name": name,
        "vehicle_count": vcount,
        "total_reduction": tred,
        "effective_reduction": None,
        "expected_payout": payout,
    }


# ── 대상 선정 — (미지정) 제외 ────────────────────────────────────────────────
def test_targets_exclude_unassigned():
    items = [
        _item("c-a", "가운수", 1000.0, [_proj("사업A", 1, 10.0, 1000.0)]),
        _item(None, "(미지정)", 500.0, [_proj("사업U", 1, 5.0, 500.0)]),
        _item("c-b", "나운수", None, [_proj("사업B", 1, 3.0, None)]),
    ]
    targets = sn.settlement_notice_targets(items)
    ids = [t["client_id"] for t in targets]
    assert ids == ["c-a", "c-b"]  # None(미지정) 제외, 순서 유지


# ── 스코프 격리(최중요) — 각 본문에 자기 수치만, 타 운수사 부재 ──────────────
def test_scope_isolation_per_client():
    a = _item("c-a", "가나다운수", 1234000.0, [_proj("에이사업", 2, 20.0, 1234000.0)])
    b = _item("c-b", "라마바운수", 9876000.0, [_proj("비사업", 3, 30.0, 9876000.0)])

    _, body_a = sn.render_settlement_notice(a, subject_tpl=SUBJECT_TPL, body_tpl=BODY_TPL)
    _, body_b = sn.render_settlement_notice(b, subject_tpl=SUBJECT_TPL, body_tpl=BODY_TPL)

    # A 본문: 자기 회사명·금액·사업명만
    assert "가나다운수" in body_a and "1,234,000원" in body_a and "에이사업" in body_a
    # A 본문에 B의 회사명·금액·사업명 절대 부재(스코프 격리)
    assert "라마바운수" not in body_a
    assert "9,876,000" not in body_a
    assert "비사업" not in body_a
    # 대칭 확인 — B 본문에 A 데이터 부재
    assert "라마바운수" in body_b and "9,876,000원" in body_b
    assert "가나다운수" not in body_b
    assert "1,234,000" not in body_b
    assert "에이사업" not in body_b


# ── expected_payout=None → 본문 '산정 중' ────────────────────────────────────
def test_none_payout_renders_pending():
    item = _item("c-n", "미산정운수", None, [_proj("미산정사업", 1, 7.0, None)])
    _, body = sn.render_settlement_notice(item, subject_tpl=SUBJECT_TPL, body_tpl=BODY_TPL)
    assert "산정 중" in body


# ── '예정액(확정 아님)' 고지 문구 항상 포함 ──────────────────────────────────
def test_disclaimer_always_present():
    item = _item("c-a", "고지운수", 1000.0, [_proj("사업A", 1, 10.0, 1000.0)])
    # 템플릿에 고지가 없어도(기본 본문에 없음) 코드가 부착
    _, body = sn.render_settlement_notice(item, subject_tpl=SUBJECT_TPL, body_tpl=BODY_TPL)
    assert "정산 예정액이며 확정 금액이 아닙니다" in body


# ── render_template 경유 — 미지원 {변수}는 원문 유지(str.format이면 KeyError) ──
def test_render_template_passthrough_unknown_var():
    item = _item("c-a", "치환운수", 1000.0, [_proj("사업A", 1, 10.0, 1000.0)])
    subject, body = sn.render_settlement_notice(
        item,
        subject_tpl="{운수사명} {없는변수}",
        body_tpl="<p>{운수사명} {또다른없는변수}</p>",
    )
    # 지원 변수는 치환, 미지원 변수는 원문 유지(예외 없이)
    assert subject == "치환운수 {없는변수}"
    assert "치환운수" in body and "{또다른없는변수}" in body


# ═══════════════════════════════════════════════════════════════════════════
# Increment 2 — 엔드포인트 통합(스코프 격리·실패격리·인가·감사·Gmail 미설정)
# 실발송 없음: email_service.send_mail/is_configured를 전부 monkeypatch.
# ═══════════════════════════════════════════════════════════════════════════
def _mk_carrier(client, headers, tag, per_year=30, vehicles=1, email=None):
    """운수사 + 사업 + 차량 + 지급파라미터(→expected_payout 산정) 시드. main_contact_email 옵션."""
    r = client.post(API + "/clients", headers=headers,
                    json={"client_type": "TRANSPORT", "company_name": "통지운수" + tag})
    assert r.status_code == 201, r.text
    cid = r.json()["client_id"]
    r = client.post(PROJECTS, headers=headers,
                    json={"project_name": "통지사업" + tag, "project_status": "기획"})
    assert r.status_code == 201, r.text
    pid = r.json()["project_id"]
    veh = {"registered_at": "2016-01-01", "client_id": cid}
    for i in range(1, 9):
        veh["reduction_y{0}".format(i)] = per_year
    for _ in range(vehicles):
        r = client.post("{0}/{1}/vehicles".format(PROJECTS, pid), headers=headers, json=veh)
        assert r.status_code == 201, r.text
    r = client.put("{0}/{1}/payout-params".format(PROJECTS, pid), headers=headers,
                   json={"max_payment": 1200000, "approved_at": "2016-02-01"})
    assert r.status_code == 200, r.text
    if email is not None:
        _set_attr(cid, main_contact_email=email)
    return cid


def _set_attr(client_id, **attrs):
    db = models.SessionLocal()
    try:
        c = db.get(models.Client, client_id)
        for k, v in attrs.items():
            setattr(c, k, v)
        db.commit()
    finally:
        db.close()


def _login_role(client, user_id, email, role):
    db = models.SessionLocal()
    try:
        u = db.get(models.User, user_id)
        if u is None:
            u = models.User(user_id=user_id, email=email, name=email.split("@")[0])
            db.add(u)
        u.role = role
        u.status = "ACTIVE"
        db.commit()
    finally:
        db.close()
    tok = client.post(API + "/auth/dev-login", json={"email": email})
    assert tok.status_code == 200, tok.text
    return {"Authorization": "Bearer {0}".format(tok.json()["access_token"])}


def _payout_of(client, headers, cid):
    body = client.get(SUMMARY, headers=headers, params={"client_id": cid}).json()
    return body["items"][0]["expected_payout"]


def _patch_mail(monkeypatch, fail_to=None):
    """send_mail 캡처(실발송 없음) — fail_to 이메일이 to에 있으면 예외(건별 실패 유발)."""
    sent = []

    def fake_send(to, subject, body, cc=None, attachments=None, reply_to=None, html=False):
        if fail_to is not None and fail_to in to:
            raise RuntimeError("smtp boom")
        sent.append({"to": list(to), "subject": subject, "body": body, "html": html})
        return {"sender": "x@y", "recipients": list(to)}

    monkeypatch.setattr(email_service, "is_configured", lambda: True)
    monkeypatch.setattr(email_service, "send_mail", fake_send)
    return sent


# ── 통합 스코프 격리(최중요) — 각 메일에 자기 수치만, 타사 부재 ──────────────
def test_send_scope_isolation(client, manager_headers, monkeypatch):
    a = _mk_carrier(client, manager_headers, "격리A", per_year=30, vehicles=1,
                    email="a-iso@carrier.example")
    b = _mk_carrier(client, manager_headers, "격리B", per_year=30, vehicles=2,
                    email="b-iso@carrier.example")
    pay_a = _payout_of(client, manager_headers, a)
    pay_b = _payout_of(client, manager_headers, b)
    assert pay_a is not None and pay_b is not None and pay_a != pay_b

    sent = _patch_mail(monkeypatch)
    r = client.post(SEND, headers=manager_headers, json={"client_ids": [a, b]})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["target_count"] == 2 and res["sent"] == 2 and res["failed"] == 0
    assert all(d["result"] == "SENT" for d in res["details"])
    assert res["details"][0]["reason"] is None

    by_to = {m["to"][0]: m for m in sent}
    body_a = by_to["a-iso@carrier.example"]["body"]
    body_b = by_to["b-iso@carrier.example"]["body"]
    # HTML 발송
    assert by_to["a-iso@carrier.example"]["html"] is True
    # A 본문: 자기 회사명·사업명·금액. B의 것 절대 부재(스코프 격리)
    assert "통지운수격리A" in body_a and "통지사업격리A" in body_a
    assert "통지운수격리B" not in body_a and "통지사업격리B" not in body_a
    assert "{0:,.0f}원".format(pay_a) in body_a
    assert "{0:,.0f}원".format(pay_b) not in body_a
    # 대칭
    assert "통지운수격리B" in body_b and "통지운수격리A" not in body_b
    assert "{0:,.0f}원".format(pay_a) not in body_b
    # 필수 고지 문구 + 활동 이력(각 1건, [자동])
    assert "정산 예정액이며 확정 금액이 아닙니다" in body_a
    db = models.SessionLocal()
    try:
        acts = (db.query(models.ActivityHistory)
                .filter(models.ActivityHistory.client_id.in_([a, b]),
                        models.ActivityHistory.activity_type == "EMAIL").all())
        assert len(acts) == 2
        assert all(ah.title.startswith("[자동]") for ah in acts)
    finally:
        db.close()


# ── 건별 실패 격리 — 한 운수사 send_mail 실패, 나머지 SENT ────────────────────
def test_send_per_item_failure_isolation(client, manager_headers, monkeypatch):
    c = _mk_carrier(client, manager_headers, "실패C", email="c-fail@carrier.example")
    d = _mk_carrier(client, manager_headers, "성공D", email="d-ok@carrier.example")

    _patch_mail(monkeypatch, fail_to="c-fail@carrier.example")
    r = client.post(SEND, headers=manager_headers, json={"client_ids": [c, d]})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["sent"] == 1 and res["failed"] == 1
    by_id = {x["client_id"]: x for x in res["details"]}
    assert by_id[c]["result"] == "FAILED" and by_id[c]["reason"]
    assert by_id[d]["result"] == "SENT"
    # 실패 운수사엔 활동 이력 미적재, 성공 운수사만 적재
    db = models.SessionLocal()
    try:
        assert db.query(models.ActivityHistory).filter(
            models.ActivityHistory.client_id == c,
            models.ActivityHistory.activity_type == "EMAIL").count() == 0
        assert db.query(models.ActivityHistory).filter(
            models.ActivityHistory.client_id == d,
            models.ActivityHistory.activity_type == "EMAIL").count() == 1
    finally:
        db.close()


# ── Gmail 미설정 → 503 즉시 중단(활동 이력·감사 미생성) ──────────────────────
def test_send_gmail_unconfigured(client, manager_headers, monkeypatch):
    e = _mk_carrier(client, manager_headers, "미설정E", email="e-cfg@carrier.example")
    monkeypatch.setattr(email_service, "is_configured", lambda: False)

    db = models.SessionLocal()
    try:
        audits_before = db.query(models.AuditLog).filter(
            models.AuditLog.action == "SETTLEMENT_NOTICE_SEND").count()
    finally:
        db.close()

    r = client.post(SEND, headers=manager_headers, json={"client_ids": [e]})
    assert r.status_code == 503, r.text

    db = models.SessionLocal()
    try:
        assert db.query(models.AuditLog).filter(
            models.AuditLog.action == "SETTLEMENT_NOTICE_SEND").count() == audits_before
        assert db.query(models.ActivityHistory).filter(
            models.ActivityHistory.client_id == e,
            models.ActivityHistory.activity_type == "EMAIL").count() == 0
    finally:
        db.close()


# ── 감사 1건 — 카운트 요약만, 금액·수신 이메일 원문 미기록(R2-E6) ────────────
def test_send_audit_no_secret(client, manager_headers, monkeypatch):
    g = _mk_carrier(client, manager_headers, "감사G", email="g-aud@carrier.example")
    pay = _payout_of(client, manager_headers, g)
    _patch_mail(monkeypatch)
    r = client.post(SEND, headers=manager_headers, json={"client_ids": [g]})
    assert r.status_code == 200, r.text

    db = models.SessionLocal()
    try:
        log = (db.query(models.AuditLog)
               .filter(models.AuditLog.action == "SETTLEMENT_NOTICE_SEND")
               .order_by(models.AuditLog.created_at.desc()).first())
        assert log is not None
        assert log.target_type == "ASSET_REPORT"
        assert log.new_value.startswith("targets=")
        # 금액 원문·수신 이메일 원문 미기록
        assert str(int(pay)) not in log.new_value
        assert "{0:,.0f}".format(pay) not in log.new_value
        assert "g-aud@carrier.example" not in log.new_value
    finally:
        db.close()


# ── preview — sendable_count·can_receive·to_count 정확 ───────────────────────
def test_preview_sendable_count(client, manager_headers):
    ok = _mk_carrier(client, manager_headers, "미리보기OK", email="prev-ok@carrier.example")
    # 수신불가(이메일·수신자 없음) — 대상엔 포함되나 sendable에서 제외
    nore = _mk_carrier(client, manager_headers, "미리보기NORE", email=None)

    r = client.post(PREVIEW, headers=manager_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    by_id = {i["client_id"]: i for i in body["items"]}
    assert ok in by_id and nore in by_id  # (미지정) 아닌 운수사는 모두 노출
    assert by_id[ok]["can_receive"] is True and by_id[ok]["to_count"] == 1
    assert by_id[nore]["can_receive"] is False and by_id[nore]["to_count"] == 0
    # sendable_count == 목록에서 expected_payout not None & can_receive 인 수
    expected = sum(1 for i in body["items"]
                   if i["expected_payout"] is not None and i["can_receive"])
    assert body["sendable_count"] == expected
    # (미지정) client_id=None 은 목록에 없음
    assert all(i["client_id"] is not None for i in body["items"])


# ═══════════════════════════════════════════════════════════════════════════
# Increment 3 — reviewer HIGH 2건 계약 일치(오버라이드 반영·필터 스코핑·대상 고정)
# ═══════════════════════════════════════════════════════════════════════════

# ── 오버라이드 반영 — payload.subject/body가 실제 발송에 반영(기본 템플릿 아님) ──
def test_send_subject_body_override(client, manager_headers, monkeypatch):
    ov = _mk_carrier(client, manager_headers, "오버라이드", email="ov@carrier.example")
    sent = _patch_mail(monkeypatch)
    r = client.post(SEND, headers=manager_headers, json={
        "client_ids": [ov],
        "subject": "커스텀제목 {운수사명}",
        "body": "<p>커스텀본문 {운수사명}</p>",
    })
    assert r.status_code == 200, r.text
    m = sent[0]
    # 오버라이드 제목/본문이 반영(client별 변수만 정규식 치환) — 스코프 유출 없음
    assert m["subject"] == "커스텀제목 통지운수오버라이드"
    assert "커스텀본문 통지운수오버라이드" in m["body"]
    # 기본 템플릿 문구는 부재(오버라이드가 실제 반영됨을 확증)
    assert "담당자님, 안녕하세요" not in m["body"]
    # 고지 문구는 오버라이드에도 상시 부착(누락 방지)
    assert "정산 예정액이며 확정 금액이 아닙니다" in m["body"]


# ── 오버라이드 미전달 — tb_config 미저장 시 코드 기본 템플릿 ──────────────────
def test_send_default_template_when_no_override(client, manager_headers, monkeypatch):
    df = _mk_carrier(client, manager_headers, "기본템플릿", email="df@carrier.example")
    sent = _patch_mail(monkeypatch)
    r = client.post(SEND, headers=manager_headers, json={"client_ids": [df]})
    assert r.status_code == 200, r.text
    assert "담당자님, 안녕하세요" in sent[0]["body"]  # 기본 본문 사용


# ── preview 필터 스코핑 — client_id 필터 시 그 운수사만 items(전사 아님) ────────
def test_preview_filter_scoping_client_id(client, manager_headers):
    x = _mk_carrier(client, manager_headers, "필터X", email="fx@carrier.example")
    y = _mk_carrier(client, manager_headers, "필터Y", email="fy@carrier.example")
    r = client.post(PREVIEW, headers=manager_headers, json={"client_id": x})
    assert r.status_code == 200, r.text
    ids = [i["client_id"] for i in r.json()["items"]]
    assert x in ids and y not in ids  # 필터 반영 — y는 스코프 밖


# ── preview 필터 스코핑 — region 필터 반영 ───────────────────────────────────
def test_preview_filter_scoping_region(client, manager_headers):
    z = _mk_carrier(client, manager_headers, "지역Z", email="rz@carrier.example")
    _set_attr(z, region="정산통지테스트지역")
    r = client.post(PREVIEW, headers=manager_headers, json={"region": "정산통지테스트지역"})
    assert r.status_code == 200, r.text
    ids = [i["client_id"] for i in r.json()["items"]]
    assert ids == [z]  # 해당 지역 운수사만


# ── 대상 고정 — send client_ids 부분집합만 발송, 나머지 미발송(표류 차단) ──────
def test_send_target_locked_to_client_ids(client, manager_headers, monkeypatch):
    s1 = _mk_carrier(client, manager_headers, "고정S1", email="s1@carrier.example")
    _mk_carrier(client, manager_headers, "고정S2", email="s2@carrier.example")
    sent = _patch_mail(monkeypatch)
    r = client.post(SEND, headers=manager_headers, json={"client_ids": [s1]})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["target_count"] == 1 and res["sent"] == 1 and res["failed"] == 0
    tos = [m["to"][0] for m in sent]
    assert "s1@carrier.example" in tos
    assert "s2@carrier.example" not in tos  # client_ids 밖은 미발송(preview==send)
    assert [d["client_id"] for d in res["details"]] == [s1]


# ── 인가 — master.write(STAFF 200)·OBSERVER 403·외부역할 403·미인증 401 ──────
def test_authz_preview_and_send(client, staff_headers, monkeypatch):
    # STAFF(master.write 보유) 200
    assert client.post(PREVIEW, headers=staff_headers).status_code == 200
    _patch_mail(monkeypatch)
    assert client.post(SEND, headers=staff_headers, json={"client_ids": []}).status_code == 200

    # OBSERVER 403(master.write 미보유 + 화이트리스트 미포함)
    obs = _login_role(client, "u-sn-obs", "sn-obs@hooxipartners.com", "OBSERVER")
    assert client.post(PREVIEW, headers=obs).status_code == 403
    assert client.post(SEND, headers=obs, json={}).status_code == 403

    # 외부역할 403
    par = _login_role(client, "u-sn-par", "sn-par@carrier.example", "PARTNER")
    inv = _login_role(client, "u-sn-inv", "sn-inv@fund.example", "INVESTOR")
    assert client.post(PREVIEW, headers=par).status_code == 403
    assert client.post(SEND, headers=inv, json={}).status_code == 403

    # 미인증 401
    assert client.post(PREVIEW).status_code == 401
    assert client.post(SEND, json={}).status_code == 401
