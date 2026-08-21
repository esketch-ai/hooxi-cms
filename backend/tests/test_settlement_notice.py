"""운수사 정산내역 능동 통지(P3) — 대상 선정·본문 렌더(스코프 격리) 단위 검증.

increment 1 범위: services.settlement_notice 순수 함수만(HTTP·발송 없음).
- 스코프 격리(최중요): render는 그 운수사 1건만 입력받아 타 운수사 수치가 본문에 부재.
- (미지정) client_id=None 제외, expected_payout=None → 본문 '산정 중'.
- '예정액(확정 아님)' 고지 문구 항상 포함.
- render_template 경유 — 미지원 {변수}는 원문 유지(str.format이면 KeyError로 실패).
"""

import models
from services import email_service, integration_config, kakao_service
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
    # dev-login은 내부 전용(외부는 매직링크 전용)이므로 테스트 토큰은 직접 발급
    from auth import create_access_token

    db2 = models.SessionLocal()
    try:
        u2 = db2.query(models.User).filter(models.User.email == email).first()
        assert u2 is not None, email
        return {"Authorization": "Bearer {0}".format(create_access_token(u2))}
    finally:
        db2.close()


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


# ═══════════════════════════════════════════════════════════════════════════
# 증분 3 — 확정 정산 통지 연계(P4): notice_type=CONFIRMED
# 확정 header(tb_settlement.confirmed_amount 동결값)로 금액 원천 스왑 + 확정 문구.
# 미확정 운수사는 CONFIRMED 대상 제외. EXPECTED(기본)은 불변(무회귀).
# ═══════════════════════════════════════════════════════════════════════════
def _confirm_header(client_id, amount, status="CONFIRMED"):
    """확정 header(tb_settlement) 직접 시드 — confirmed_amount를 동결값으로 고정.

    live 예상지급액과 다른 값을 넣어 '확정 통지가 동결값을 쓰는지' 판별할 수 있게 한다.
    """
    db = models.SessionLocal()
    try:
        pv = (db.query(models.ProjectVehicle)
              .filter(models.ProjectVehicle.client_id == client_id).first())
        s = models.Settlement(
            client_id=client_id, project_id=pv.project_id, period=None,
            status=status, confirmed_amount=amount,
        )
        db.add(s)
        db.commit()
        return s.settlement_id
    finally:
        db.close()


# ── CONFIRMED — 확정 header 동결값 사용·확정 문구·예정 disclaimer 부재 ─────────
def test_confirmed_notice_uses_frozen_amount(client, manager_headers, monkeypatch):
    cf = _mk_carrier(client, manager_headers, "확정CF", email="cf@carrier.example")
    live = _payout_of(client, manager_headers, cf)
    frozen = 777000.0
    assert live is not None and live != frozen  # live와 다른 동결값으로 판별
    _confirm_header(cf, frozen)

    sent = _patch_mail(monkeypatch)
    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [cf], "notice_type": "CONFIRMED"})
    assert r.status_code == 200, r.text
    assert r.json()["sent"] == 1
    body = sent[0]["body"]
    # 금액 = 확정 header confirmed_amount(동결값), live 예상지급액 아님
    assert "확정 정산액: {0:,.0f}원".format(frozen) in body
    assert "{0:,.0f}원".format(live) not in body
    # 확정 문구 포함, 예정 disclaimer 부재
    assert "확정 정산액입니다" in body
    assert "확정 정산 명세" in body
    assert "정산 예정액이며 확정 금액이 아닙니다" not in body
    # 활동 이력 '확정 명세' [자동]
    db = models.SessionLocal()
    try:
        ah = (db.query(models.ActivityHistory)
              .filter(models.ActivityHistory.client_id == cf,
                      models.ActivityHistory.activity_type == "EMAIL").one())
        assert ah.title.startswith("[자동]") and "확정" in ah.title
    finally:
        db.close()


# ── CONFIRMED — 미확정 운수사는 preview sendable·send 대상 제외 ───────────────
def test_confirmed_excludes_unconfirmed(client, manager_headers, monkeypatch):
    conf = _mk_carrier(client, manager_headers, "확정있음", email="has-cf@carrier.example")
    _confirm_header(conf, 500000.0)
    noconf = _mk_carrier(client, manager_headers, "확정없음", email="no-cf@carrier.example")

    # preview: CONFIRMED은 확정 header 있는 운수사만 목록·sendable
    r = client.post(PREVIEW, headers=manager_headers, json={"notice_type": "CONFIRMED"})
    assert r.status_code == 200, r.text
    body = r.json()
    ids = [i["client_id"] for i in body["items"]]
    assert conf in ids and noconf not in ids  # 미확정 목록 제외
    by_id = {i["client_id"]: i for i in body["items"]}
    assert by_id[conf]["expected_payout"] == 500000.0  # 확정 금액 노출

    # send: 미확정을 명시 요청해도 발송 안 됨(sendable 밖)
    sent = _patch_mail(monkeypatch)
    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [conf, noconf], "notice_type": "CONFIRMED"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["target_count"] == 1 and res["sent"] == 1
    assert [d["client_id"] for d in res["details"]] == [conf]
    assert "no-cf@carrier.example" not in [m["to"][0] for m in sent]


# ── CONFIRMED — 스코프 격리 유지(각 메일 자기 운수사 확정액만, 타사 부재) ──────
def test_confirmed_scope_isolation(client, manager_headers, monkeypatch):
    a = _mk_carrier(client, manager_headers, "확정격리A", email="cfa@carrier.example")
    b = _mk_carrier(client, manager_headers, "확정격리B", email="cfb@carrier.example")
    _confirm_header(a, 111000.0)
    _confirm_header(b, 222000.0)

    sent = _patch_mail(monkeypatch)
    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [a, b], "notice_type": "CONFIRMED"})
    assert r.status_code == 200, r.text
    assert r.json()["sent"] == 2
    by_to = {m["to"][0]: m["body"] for m in sent}
    body_a = by_to["cfa@carrier.example"]
    body_b = by_to["cfb@carrier.example"]
    # A 본문: 자기 확정액·회사명만, B의 확정액·회사명 부재
    assert "111,000원" in body_a and "통지운수확정격리A" in body_a
    assert "222,000" not in body_a and "통지운수확정격리B" not in body_a
    # 대칭
    assert "222,000원" in body_b and "통지운수확정격리B" in body_b
    assert "111,000" not in body_b and "통지운수확정격리A" not in body_b


# ── CONFIRMED — 감사 금액 원문 미기록 유지(notice_type만 추가) ────────────────
def test_confirmed_audit_no_secret(client, manager_headers, monkeypatch):
    g = _mk_carrier(client, manager_headers, "확정감사", email="cfg@carrier.example")
    _confirm_header(g, 333000.0)
    _patch_mail(monkeypatch)
    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [g], "notice_type": "CONFIRMED"})
    assert r.status_code == 200, r.text
    db = models.SessionLocal()
    try:
        log = (db.query(models.AuditLog)
               .filter(models.AuditLog.action == "SETTLEMENT_NOTICE_SEND")
               .order_by(models.AuditLog.created_at.desc()).first())
        assert log.new_value.startswith("targets=")  # 계약 유지
        assert "CONFIRMED" in log.new_value  # notice_type 기록
        assert "333,000" not in log.new_value and "333000" not in log.new_value
        assert "cfg@carrier.example" not in log.new_value
    finally:
        db.close()


# ── EXPECTED(기본) — notice_type 미전달 시 기존 예정 통지 불변(무회귀) ─────────
def test_expected_default_unchanged(client, manager_headers, monkeypatch):
    e = _mk_carrier(client, manager_headers, "예정기본", email="exp@carrier.example")
    _confirm_header(e, 999000.0)  # 확정 header가 있어도 EXPECTED은 live 예정액 사용
    live = _payout_of(client, manager_headers, e)
    sent = _patch_mail(monkeypatch)
    r = client.post(SEND, headers=manager_headers, json={"client_ids": [e]})  # notice_type 미전달
    assert r.status_code == 200, r.text
    body = sent[0]["body"]
    assert "{0:,.0f}원".format(live) in body  # live 예정액
    assert "999,000원" not in body  # 확정 header 무시(EXPECTED)
    assert "정산 예정액이며 확정 금액이 아닙니다" in body  # 예정 disclaimer
    assert "확정 정산액입니다" not in body


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


# ═══════════════════════════════════════════════════════════════════════════
# 증분(P3 백엔드) — 카카오 알림톡 채널(channel EMAIL|ALIMTALK|BOTH)
# 알림톡 본문 금액 미포함(운수사명·기준일·통지유형만). 수신번호 = KakaoContact
# (APPROVED·phone) 우선 → Client.main_contact_phone 폴백. 채널별 독립 실패격리.
# 실발송 없음: kakao_service.send_alimtalk/is_configured_alimtalk·integration_config.resolve
# 를 전부 monkeypatch.
# ═══════════════════════════════════════════════════════════════════════════
def _approve_contact(client_id, phone, suffix=""):
    """승인(APPROVED) 카카오 연락처 시드 — 알림톡 수신번호 원천."""
    db = models.SessionLocal()
    try:
        db.add(models.KakaoContact(
            kakao_user_key="kuk-" + client_id + suffix,
            client_id=client_id, name="담당", phone=phone,
            status="APPROVED", approved_at=models.utcnow(),
        ))
        db.commit()
    finally:
        db.close()


def _patch_alimtalk(monkeypatch, template="TMPL_SETTLE", fail=False):
    """알림톡 설정 mock — send_alimtalk 호출 인자 캡처(실발송 없음). fail=True면 KakaoSendError."""
    calls = []

    def fake_resolve(key):
        return template if key == "KAKAO_TEMPLATE_SETTLEMENT" else ""

    def fake_send(to, template_code, variables=None, buttons=None):
        calls.append({"to": to, "template_code": template_code,
                      "variables": dict(variables or {})})
        if fail:
            raise kakao_service.KakaoSendError("boom")
        return {"ok": True}

    monkeypatch.setattr(kakao_service, "is_configured_alimtalk", lambda: True)
    monkeypatch.setattr(integration_config, "resolve", fake_resolve)
    monkeypatch.setattr(kakao_service, "send_alimtalk", fake_send)
    return calls


# ── (a) 채널 미지정=이메일만(기존 무회귀) — alimtalk 필드 None·카운트 0 ─────────
def test_channel_default_email_only(client, manager_headers, monkeypatch):
    a = _mk_carrier(client, manager_headers, "기본채널", email="ch-def@carrier.example")
    _approve_contact(a, "010-0000-1111")  # 연락처 있어도 EMAIL 채널이면 알림톡 미발송
    _patch_mail(monkeypatch)
    r = client.post(SEND, headers=manager_headers, json={"client_ids": [a]})  # channel 미지정
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["sent"] == 1 and res["alimtalk_sent"] == 0 and res["alimtalk_failed"] == 0
    d = res["details"][0]
    assert d["result"] == "SENT" and d["email_result"] == "SENT"
    assert d["alimtalk_result"] is None


# ── (b) BOTH + 알림톡 미설정 → 이메일만·알림톡 스킵 ──────────────────────────
def test_both_alimtalk_unconfigured(client, manager_headers, monkeypatch):
    a = _mk_carrier(client, manager_headers, "BOTH미설정", email="both-nc@carrier.example")
    sent = _patch_mail(monkeypatch)
    monkeypatch.setattr(kakao_service, "is_configured_alimtalk", lambda: False)
    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [a], "channel": "BOTH"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["sent"] == 1 and res["alimtalk_sent"] == 0 and res["alimtalk_failed"] == 0
    assert len(sent) == 1
    d = res["details"][0]
    assert d["result"] == "SENT" and d["alimtalk_result"] is None  # 게이트 off → 미대상


# ── (c) 알림톡 설정 mock → send_alimtalk 인자 검증·금액 변수 부재 ─────────────
def test_alimtalk_args_no_amount(client, manager_headers, monkeypatch):
    a = _mk_carrier(client, manager_headers, "알림톡C", email="atc@carrier.example")
    pay = _payout_of(client, manager_headers, a)
    _approve_contact(a, "010-1234-5678")
    _patch_mail(monkeypatch)
    calls = _patch_alimtalk(monkeypatch)
    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [a], "channel": "BOTH"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["sent"] == 1 and res["alimtalk_sent"] == 1
    assert res["details"][0]["alimtalk_result"] == "SENT"
    assert len(calls) == 1
    c0 = calls[0]
    assert c0["to"] == "010-1234-5678"  # KakaoContact APPROVED phone
    assert c0["template_code"] == "TMPL_SETTLE"
    assert set(c0["variables"].keys()) == {"운수사명", "기준일", "통지유형"}
    assert c0["variables"]["운수사명"] == "통지운수알림톡C"
    assert c0["variables"]["통지유형"] == "예정"
    # 금액 변수·금액값 부재(유출 리스크 최소)
    assert "예상지급액" not in c0["variables"] and "금액" not in c0["variables"]
    assert "{0:,.0f}".format(pay) not in str(c0["variables"])
    assert str(int(pay)) not in str(c0["variables"])


# ── (c') main_contact_phone 폴백 — KakaoContact 없으면 주 담당자 전화 사용 ─────
def test_alimtalk_phone_fallback(client, manager_headers, monkeypatch):
    a = _mk_carrier(client, manager_headers, "폴백전화", email="fb@carrier.example")
    _set_attr(a, main_contact_phone="010-7777-8888")  # KakaoContact 없음 → 폴백
    _patch_mail(monkeypatch)
    calls = _patch_alimtalk(monkeypatch)
    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [a], "channel": "ALIMTALK"})
    assert r.status_code == 200, r.text
    assert r.json()["alimtalk_sent"] == 1
    assert calls[0]["to"] == "010-7777-8888"


# ── (d) 알림톡 예외 → 이메일 SENT 유지·detail alimtalk FAILED ─────────────────
def test_alimtalk_failure_keeps_email(client, manager_headers, monkeypatch):
    a = _mk_carrier(client, manager_headers, "알림톡실패", email="atf@carrier.example")
    _approve_contact(a, "010-9999-0000")
    _patch_mail(monkeypatch)
    _patch_alimtalk(monkeypatch, fail=True)
    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [a], "channel": "BOTH"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["sent"] == 1 and res["alimtalk_sent"] == 0 and res["alimtalk_failed"] == 1
    d = res["details"][0]
    assert d["result"] == "SENT"  # 기존 계약 — 이메일 결과 유지
    assert d["email_result"] == "SENT" and d["alimtalk_result"] == "FAILED"
    db = models.SessionLocal()
    try:
        assert db.query(models.ActivityHistory).filter(
            models.ActivityHistory.client_id == a,
            models.ActivityHistory.activity_type == "EMAIL").count() == 1
        assert db.query(models.ActivityHistory).filter(
            models.ActivityHistory.client_id == a,
            models.ActivityHistory.activity_type == "KAKAO").count() == 0
    finally:
        db.close()


# ── (d') KakaoSendError 아닌 예외(httpx 타임아웃 등)도 전면 삼킴 — 500 없음·격리 보존 ──
# send_alimtalk은 httpx.post(타임아웃/연결오류)·resp.json()(파싱오류) 등 KakaoSendError
# 아닌 예외를 던질 수 있다. 이게 send 루프로 전파되면 HTTP 500·세션 롤백으로 이미 발송된
# 이메일 활동이력이 유실되고 나머지 대상이 미발송된다(채널 격리 붕괴). 전면 포착 검증.
def test_alimtalk_generic_exception_isolated(client, manager_headers, monkeypatch):
    import httpx

    a = _mk_carrier(client, manager_headers, "알림톡예외A", email="age-a@carrier.example")
    b = _mk_carrier(client, manager_headers, "알림톡예외B", email="age-b@carrier.example")
    _approve_contact(a, "010-3333-4444")
    _approve_contact(b, "010-5555-7777")
    sent = _patch_mail(monkeypatch)

    def fake_resolve(key):
        return "TMPL_SETTLE" if key == "KAKAO_TEMPLATE_SETTLEMENT" else ""

    def boom_send(to, template_code, variables=None, buttons=None):
        raise httpx.TimeoutException("connect timeout")  # KakaoSendError 아님

    monkeypatch.setattr(kakao_service, "is_configured_alimtalk", lambda: True)
    monkeypatch.setattr(integration_config, "resolve", fake_resolve)
    monkeypatch.setattr(kakao_service, "send_alimtalk", boom_send)

    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [a, b], "channel": "BOTH"})
    assert r.status_code == 200, r.text  # 500 아님 — 예외 전파 차단
    res = r.json()
    # 이메일은 두 건 모두 SENT(채널 격리) — 알림톡 예외가 이메일/나머지 대상을 되돌리지 않음
    assert res["sent"] == 2 and res["failed"] == 0
    assert res["alimtalk_sent"] == 0 and res["alimtalk_failed"] == 2
    assert len(sent) == 2  # 두 운수사 이메일 모두 발송
    by_id = {d["client_id"]: d for d in res["details"]}
    for cid in (a, b):
        assert by_id[cid]["email_result"] == "SENT"
        assert by_id[cid]["alimtalk_result"] == "FAILED"
        assert by_id[cid]["result"] == "SENT"  # 기존 계약 — 이메일 결과 유지
    # 이메일 활동이력 보존(각 1건), 알림톡 KAKAO 미적재
    db = models.SessionLocal()
    try:
        assert db.query(models.ActivityHistory).filter(
            models.ActivityHistory.client_id.in_([a, b]),
            models.ActivityHistory.activity_type == "EMAIL").count() == 2
        assert db.query(models.ActivityHistory).filter(
            models.ActivityHistory.client_id.in_([a, b]),
            models.ActivityHistory.activity_type == "KAKAO").count() == 0
    finally:
        db.close()


# ── 알림톡 성공 → KAKAO 활동 이력 [자동] 적재(전화 원문 미기록) ───────────────
def test_alimtalk_success_activity(client, manager_headers, monkeypatch):
    a = _mk_carrier(client, manager_headers, "알림톡성공", email="ats@carrier.example")
    _approve_contact(a, "010-2222-3333")
    _patch_mail(monkeypatch)
    _patch_alimtalk(monkeypatch)
    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [a], "channel": "ALIMTALK"})
    assert r.status_code == 200, r.text
    assert r.json()["alimtalk_sent"] == 1
    db = models.SessionLocal()
    try:
        ah = (db.query(models.ActivityHistory)
              .filter(models.ActivityHistory.client_id == a,
                      models.ActivityHistory.activity_type == "KAKAO").one())
        assert ah.title.startswith("[자동]")
        assert "010-2222-3333" not in (ah.content or "")
        assert "01022223333" not in (ah.content or "")
    finally:
        db.close()


# ── (e) ALIMTALK 단독 + 알림톡 미설정 → 503(발송·감사 0) ──────────────────────
def test_alimtalk_only_unconfigured_503(client, manager_headers, monkeypatch):
    a = _mk_carrier(client, manager_headers, "단독미설정", email="ao@carrier.example")
    monkeypatch.setattr(kakao_service, "is_configured_alimtalk", lambda: False)
    db = models.SessionLocal()
    try:
        before = db.query(models.AuditLog).filter(
            models.AuditLog.action == "SETTLEMENT_NOTICE_SEND").count()
    finally:
        db.close()
    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [a], "channel": "ALIMTALK"})
    assert r.status_code == 503, r.text
    db = models.SessionLocal()
    try:
        assert db.query(models.AuditLog).filter(
            models.AuditLog.action == "SETTLEMENT_NOTICE_SEND").count() == before
    finally:
        db.close()


# ── (f) 감사 new_value — 금액·전화 원문 부재, 채널/알림톡 카운트 포함 ──────────
def test_alimtalk_audit_no_secret(client, manager_headers, monkeypatch):
    a = _mk_carrier(client, manager_headers, "알림톡감사", email="ata2@carrier.example")
    pay = _payout_of(client, manager_headers, a)
    _approve_contact(a, "010-5555-6666")
    _patch_mail(monkeypatch)
    _patch_alimtalk(monkeypatch)
    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [a], "channel": "BOTH"})
    assert r.status_code == 200, r.text
    db = models.SessionLocal()
    try:
        log = (db.query(models.AuditLog)
               .filter(models.AuditLog.action == "SETTLEMENT_NOTICE_SEND")
               .order_by(models.AuditLog.created_at.desc()).first())
        assert log.new_value.startswith("targets=")
        assert "channel=BOTH" in log.new_value and "alimtalk_sent=1" in log.new_value
        assert "010-5555-6666" not in log.new_value and "01055556666" not in log.new_value
        assert "{0:,.0f}".format(pay) not in log.new_value
        assert str(int(pay)) not in log.new_value
    finally:
        db.close()


# ── (g) preview can_receive_alimtalk/sendable_alimtalk_count(미설정 시 0) ──────
def test_preview_alimtalk_counts(client, manager_headers, monkeypatch):
    a = _mk_carrier(client, manager_headers, "미리보기AT", email="pat@carrier.example")
    _approve_contact(a, "010-1111-2222")
    b = _mk_carrier(client, manager_headers, "미리보기무전화", email="pnp@carrier.example")

    # 미설정 → 전부 false·count 0
    monkeypatch.setattr(kakao_service, "is_configured_alimtalk", lambda: False)
    body = client.post(PREVIEW, headers=manager_headers).json()
    assert body["sendable_alimtalk_count"] == 0
    assert all(i["can_receive_alimtalk"] is False and i["alimtalk_to_count"] == 0
               for i in body["items"])

    # 설정 → phone 있는 a만 can_receive_alimtalk True
    _patch_alimtalk(monkeypatch)
    body = client.post(PREVIEW, headers=manager_headers).json()
    by_id = {i["client_id"]: i for i in body["items"]}
    assert by_id[a]["can_receive_alimtalk"] is True and by_id[a]["alimtalk_to_count"] == 1
    assert by_id[b]["can_receive_alimtalk"] is False and by_id[b]["alimtalk_to_count"] == 0
    assert by_id[a]["expected_payout"] is not None
    assert body["sendable_alimtalk_count"] >= 1


# ── (h) 스코프 격리 — 각 알림톡 variables에 자기 운수사만, 타사 부재 ──────────
def test_alimtalk_scope_isolation(client, manager_headers, monkeypatch):
    a = _mk_carrier(client, manager_headers, "AT격리A", email="ata1@carrier.example")
    b = _mk_carrier(client, manager_headers, "AT격리B", email="atb1@carrier.example")
    _approve_contact(a, "010-0000-0001")
    _approve_contact(b, "010-0000-0002")
    _patch_mail(monkeypatch)
    calls = _patch_alimtalk(monkeypatch)
    r = client.post(SEND, headers=manager_headers,
                    json={"client_ids": [a, b], "channel": "ALIMTALK"})
    assert r.status_code == 200, r.text
    assert r.json()["alimtalk_sent"] == 2
    by_to = {c["to"]: c["variables"] for c in calls}
    va = by_to["010-0000-0001"]
    vb = by_to["010-0000-0002"]
    assert va["운수사명"] == "통지운수AT격리A" and "통지운수AT격리B" not in str(va)
    assert vb["운수사명"] == "통지운수AT격리B" and "통지운수AT격리A" not in str(vb)
