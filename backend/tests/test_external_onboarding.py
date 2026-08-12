"""외부계정 온보딩(provision) + 매직링크 + 변동 타임라인 — Phase 4 INC-6 / 부록 N.8 D3.

핵심:
- provision: 내부 MANAGER만 외부역할(PARTNER/INVESTOR) 계정 생성 → magic_link 반환.
  STAFF는 403. 역할별 필수(client_id/buyer_id) 누락 422, email 중복 409.
- 매직링크: /portal/auth/verify로 access 획득 → /portal/projects 스코프 동작.
- 비활성(DELETE): token_version 증가로 기발급 토큰 즉시 무효화(401).
- 타임라인: participation 스냅샷을 역할별 게이팅 —
  PARTNER는 effective_reduction·expected_payout, INVESTOR는 effective_reduction만(payout 키 부재).
"""

import models

API = "/api/v1"
PORTAL = API + "/portal"
PROJECTS = API + "/projects"
EXTERNAL = API + "/external-accounts"


# ---------------------------------------------------------------------------
# 마스터/프로젝트 헬퍼 (내부 STAFF API 재사용 — test_portal_endpoints와 동일 관용구)
# ---------------------------------------------------------------------------
def _mk_client(client, headers, name):
    r = client.post(API + "/clients", headers=headers, json={"client_type": "TRANSPORT", "company_name": name})
    assert r.status_code == 201, r.text
    return r.json()["client_id"]


def _mk_buyer(client, headers, name):
    r = client.post(API + "/buyers", headers=headers, json={"name": name, "buyer_type": "투자사"})
    assert r.status_code == 201, r.text
    return r.json()["buyer_id"]


def _mk_project(client, headers, name):
    r = client.post(PROJECTS, headers=headers, json={"project_name": name, "project_status": "기획"})
    assert r.status_code == 201, r.text
    return r.json()["project_id"]


def _mk_kakao_contact(client_id, phone, status="APPROVED"):
    """승인 카카오 연락처 직접 적재(테스트용) — provision phone 보완 경로 검증."""
    db = models.SessionLocal()
    try:
        contact = models.KakaoContact(
            kakao_user_key="kuk-{0}".format(models.gen_uuid()),
            client_id=client_id, name="연락처", phone=phone, status=status,
        )
        db.add(contact)
        db.commit()
        return contact.contact_id
    finally:
        db.close()


def _user_phone(user_id):
    """DB에 저장된 user.phone 조회(발급 후 영속 확인용)."""
    db = models.SessionLocal()
    try:
        user = db.get(models.User, user_id)
        return user.phone if user else None
    finally:
        db.close()


def _capped_vehicle(client_id, per_year):
    """잔여차령 8 캡 노후차 — y1..y8 동일값(잔여반영=Σ). 등록 2016-01-01, 운수사 지정."""
    p = {"registered_at": "2016-01-01", "client_id": client_id}
    for i in range(1, 9):
        p[f"reduction_y{i}"] = per_year
    return p


def _token_from_link(link):
    assert link and "token=" in link, link
    return link.split("token=", 1)[1]


def _bearer(access_token):
    return {"Authorization": "Bearer {0}".format(access_token)}


def _verify_access(client, magic_link):
    """magic_link → /portal/auth/verify → access_token."""
    token = _token_from_link(magic_link)
    r = client.post(f"{PORTAL}/auth/verify", json={"token": token})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# 1. provision — PARTNER
# ---------------------------------------------------------------------------
def test_provision_partner_and_portal_access(client, manager_headers, staff_headers):
    ca = _mk_client(client, staff_headers, "온보딩운수사갑")
    p = _mk_project(client, staff_headers, "온보딩P1")
    client.post(f"{PROJECTS}/{p}/vehicles", headers=staff_headers, json=_capped_vehicle(ca, 30))

    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "onboard-partner@portal.example", "name": "갑담당", "role": "PARTNER", "client_id": ca,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == "PARTNER"
    assert body["client_id"] == ca
    assert body["status"] == "ACTIVE"
    assert body["magic_link"] and "token=" in body["magic_link"]

    # 매직링크 → access → 스코프 조회 통과(자기 프로젝트 포함)
    access = _verify_access(client, body["magic_link"])
    r2 = client.get(f"{PORTAL}/projects", headers=_bearer(access))
    assert r2.status_code == 200, r2.text
    assert p in {x["project_id"] for x in r2.json()}


def test_provision_partner_requires_client_id(client, manager_headers):
    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "partner-noclient@portal.example", "role": "PARTNER",
    })
    assert r.status_code == 422, r.text


def test_provision_staff_forbidden(client, staff_headers):
    """내부 STAFF는 provision 403(MANAGER 이상)."""
    r = client.post(EXTERNAL, headers=staff_headers, json={
        "email": "byStaff@portal.example", "role": "INVESTOR", "buyer_id": "x",
    })
    assert r.status_code == 403, r.text


def test_provision_duplicate_email_conflict(client, manager_headers, staff_headers):
    ca = _mk_client(client, staff_headers, "온보딩운수사중복")
    payload = {"email": "dup-onboard@portal.example", "role": "PARTNER", "client_id": ca}
    r1 = client.post(EXTERNAL, headers=manager_headers, json=payload)
    assert r1.status_code == 201, r1.text
    r2 = client.post(EXTERNAL, headers=manager_headers, json=payload)
    assert r2.status_code == 409, r2.text


# ---------------------------------------------------------------------------
# 2. provision — INVESTOR
# ---------------------------------------------------------------------------
def test_provision_investor_and_portal_access(client, manager_headers, staff_headers):
    bx = _mk_buyer(client, staff_headers, "온보딩투자엑스")
    p = _mk_project(client, staff_headers, "온보딩P2")
    ca = _mk_client(client, staff_headers, "온보딩운수사을")
    client.post(f"{PROJECTS}/{p}/vehicles", headers=staff_headers, json=_capped_vehicle(ca, 20))
    client.post(f"{PROJECTS}/{p}/sales", headers=staff_headers, json={
        "buyer_name": "온보딩투자엑스", "buyer_id": bx, "sale_invoice_amount": 1000000, "ownership_pct": 100,
    })

    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "onboard-investor@portal.example", "role": "INVESTOR", "buyer_id": bx,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["role"] == "INVESTOR"
    assert body["buyer_id"] == bx
    assert body["client_id"] is None

    access = _verify_access(client, body["magic_link"])
    r2 = client.get(f"{PORTAL}/projects", headers=_bearer(access))
    assert r2.status_code == 200, r2.text
    assert p in {x["project_id"] for x in r2.json()}


def test_provision_investor_requires_buyer_id(client, manager_headers):
    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "investor-nobuyer@portal.example", "role": "INVESTOR",
    })
    assert r.status_code == 422, r.text


def test_provision_invalid_role_422(client, manager_headers):
    """외부역할 정규식 밖(내부역할 격리) — STAFF 부여 시도는 422."""
    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "role-staff@portal.example", "role": "STAFF",
    })
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# 3. resend-link / list / deactivate
# ---------------------------------------------------------------------------
def test_resend_link_and_list(client, manager_headers, staff_headers):
    ca = _mk_client(client, staff_headers, "온보딩운수사재발급")
    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "resend@portal.example", "role": "PARTNER", "client_id": ca,
    })
    uid = r.json()["user_id"]

    r2 = client.post(f"{EXTERNAL}/{uid}/resend-link", headers=manager_headers)
    assert r2.status_code == 200, r2.text
    assert "token=" in r2.json()["magic_link"]
    # 재발급 링크로도 로그인 가능
    _verify_access(client, r2.json()["magic_link"])

    # 목록은 외부역할만 + magic_link 미포함
    r3 = client.get(EXTERNAL, headers=manager_headers)
    assert r3.status_code == 200, r3.text
    rows = r3.json()
    assert uid in {x["user_id"] for x in rows}
    assert all(x["role"] in ("PARTNER", "INVESTOR") for x in rows)
    assert all(x["magic_link"] is None for x in rows)


def test_deactivate_invalidates_tokens(client, manager_headers, staff_headers):
    ca = _mk_client(client, staff_headers, "온보딩운수사비활성")
    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "deact@portal.example", "role": "PARTNER", "client_id": ca,
    })
    uid = r.json()["user_id"]
    access = _verify_access(client, r.json()["magic_link"])
    # 비활성 전에는 통과
    assert client.get(f"{PORTAL}/projects", headers=_bearer(access)).status_code == 200

    d = client.delete(f"{EXTERNAL}/{uid}", headers=manager_headers)
    assert d.status_code == 200, d.text
    assert d.json()["status"] == "INACTIVE"

    # token_version 증가 + INACTIVE → 기발급 access 무효(401)
    assert client.get(f"{PORTAL}/projects", headers=_bearer(access)).status_code == 401


# ---------------------------------------------------------------------------
# 4. 변동 타임라인 — 역할별 게이팅
# ---------------------------------------------------------------------------
def test_timeline_role_gating(client, manager_headers, staff_headers):
    ca = _mk_client(client, staff_headers, "타임라인운수사")
    bx = _mk_buyer(client, staff_headers, "타임라인투자")
    p = _mk_project(client, staff_headers, "타임라인P")
    # 차량 등록 → 스냅샷1(payout None) / payout-params → 스냅샷2(payout 산정)
    client.post(f"{PROJECTS}/{p}/vehicles", headers=staff_headers, json=_capped_vehicle(ca, 30))
    client.put(f"{PROJECTS}/{p}/payout-params", headers=staff_headers,
               json={"max_payment": 1200000, "approved_at": "2016-02-01"})
    client.post(f"{PROJECTS}/{p}/sales", headers=staff_headers, json={
        "buyer_name": "타임라인투자", "buyer_id": bx, "sale_invoice_amount": 3000000, "ownership_pct": 100,
    })

    partner = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "tl-partner@portal.example", "role": "PARTNER", "client_id": ca,
    }).json()
    investor = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "tl-investor@portal.example", "role": "INVESTOR", "buyer_id": bx,
    }).json()
    p_access = _verify_access(client, partner["magic_link"])
    i_access = _verify_access(client, investor["magic_link"])

    # PARTNER: effective_reduction·expected_payout 시계열
    rp = client.get(f"{PORTAL}/projects/{p}/timeline", headers=_bearer(p_access))
    assert rp.status_code == 200, rp.text
    prows = rp.json()
    assert len(prows) >= 2
    assert all("effective_reduction" in r and "expected_payout" in r for r in prows)
    # 마지막(payout-params 반영) 스냅샷은 감축량·지급액 모두 산정됨
    assert prows[-1]["effective_reduction"] == 240.0  # per_year 30 × 캡 8
    assert prows[-1]["expected_payout"] is not None and prows[-1]["expected_payout"] > 0

    # INVESTOR: effective_reduction만 — expected_payout 키 원천 부재
    ri = client.get(f"{PORTAL}/projects/{p}/timeline", headers=_bearer(i_access))
    assert ri.status_code == 200, ri.text
    irows = ri.json()
    assert len(irows) >= 2
    assert all("effective_reduction" in r for r in irows)
    for r in irows:
        assert "expected_payout" not in r
        assert "client_id" not in r


def test_timeline_out_of_scope_404(client, manager_headers, staff_headers):
    """스코프 밖 프로젝트 타임라인은 404(존재 여부 비노출)."""
    other = _mk_project(client, staff_headers, "타임라인스코프밖")
    ca = _mk_client(client, staff_headers, "타임라인격리운수사")
    partner = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "tl-oos@portal.example", "role": "PARTNER", "client_id": ca,
    }).json()
    access = _verify_access(client, partner["magic_link"])
    r = client.get(f"{PORTAL}/projects/{other}/timeline", headers=_bearer(access))
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# 5. 매직링크 알림톡 자동발송 (INC-9) — phone 영속 + best-effort delivery
# ---------------------------------------------------------------------------
def test_provision_with_phone_persists(client, manager_headers, staff_headers):
    """payload.phone → 응답 phone 세팅 + DB user.phone 저장. 알림톡 미설정 → delivery NOT_CONFIGURED(발급은 201)."""
    ca = _mk_client(client, staff_headers, "폰저장운수사")
    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "phone-partner@portal.example", "role": "PARTNER", "client_id": ca,
        "phone": "010-9876-5432",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["phone"] == "010-9876-5432"
    assert body["delivery"] == "NOT_CONFIGURED"  # 테스트 환경 알림톡 미설정 — 발급은 성공
    assert body["magic_link"] and "token=" in body["magic_link"]  # 수동 복사 폴백 유지
    assert _user_phone(body["user_id"]) == "010-9876-5432"


def test_provision_phone_from_kakao_contact(client, manager_headers, staff_headers):
    """payload.phone 없고 kakao_contact_id(승인+phone) → 연락처 번호로 보완·저장."""
    ca = _mk_client(client, staff_headers, "폰보완운수사")
    contact_id = _mk_kakao_contact(ca, "010-1111-2222")
    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "phone-bridge@portal.example", "role": "PARTNER",
        "client_id": ca, "kakao_contact_id": contact_id,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["phone"] == "010-1111-2222"
    assert _user_phone(body["user_id"]) == "010-1111-2222"


def test_list_delivery_is_none(client, manager_headers, staff_headers):
    """목록 응답의 delivery는 항상 None(발급/재발급 응답 전용 필드)."""
    ca = _mk_client(client, staff_headers, "딜리버리목록운수사")
    client.post(EXTERNAL, headers=manager_headers, json={
        "email": "delivery-list@portal.example", "role": "PARTNER", "client_id": ca,
    })
    r = client.get(EXTERNAL, headers=manager_headers)
    assert r.status_code == 200, r.text
    assert all(x["delivery"] is None for x in r.json())


def test_send_portal_invite_sent(monkeypatch):
    """알림톡 설정+템플릿+phone 갖춤 → send_alimtalk 호출·SENT. WL 버튼은 절대 링크."""
    from routers import external_accounts as ea

    sent = {}

    def fake_send(to, template_code, variables, buttons):
        sent.update(to=to, template=template_code, variables=variables, buttons=buttons)
        return {"ok": True}

    monkeypatch.setattr(ea.kakao_service, "is_configured_alimtalk", lambda: True)
    monkeypatch.setattr(ea, "resolve_integration", lambda key: "TPL_INVITE")
    monkeypatch.setattr(ea.kakao_service, "send_alimtalk", fake_send)

    user = models.User(name="갑담당", phone="010-1234-5678")
    result = ea._send_portal_invite(user, "https://app.example/portal/login?token=abc")
    assert result == "SENT"
    assert sent["to"] == "010-1234-5678"
    assert sent["template"] == "TPL_INVITE"
    assert sent["variables"] == {"이름": "갑담당"}
    assert sent["buttons"][0]["buttonType"] == "WL"
    assert sent["buttons"][0]["linkMo"].startswith("https://")


def test_send_portal_invite_no_phone(monkeypatch):
    """phone 없으면 발송 시도 없이 NO_PHONE."""
    from routers import external_accounts as ea

    def must_not_call(**kwargs):  # pragma: no cover - 호출되면 실패
        raise AssertionError("phone 없으면 발송하지 않아야 한다")

    monkeypatch.setattr(ea.kakao_service, "is_configured_alimtalk", lambda: True)
    monkeypatch.setattr(ea, "resolve_integration", lambda key: "TPL_INVITE")
    monkeypatch.setattr(ea.kakao_service, "send_alimtalk", must_not_call)

    user = models.User(name="무번호", phone=None)
    assert ea._send_portal_invite(user, "https://app.example/x") == "NO_PHONE"


def test_send_portal_invite_failed_is_swallowed(monkeypatch):
    """발송 예외는 밖으로 새지 않고 FAILED로 흡수(계정 발급 보호)."""
    from routers import external_accounts as ea

    def boom(**kwargs):
        raise ea.kakao_service.KakaoSendError("발송 실패")

    monkeypatch.setattr(ea.kakao_service, "is_configured_alimtalk", lambda: True)
    monkeypatch.setattr(ea, "resolve_integration", lambda key: "TPL_INVITE")
    monkeypatch.setattr(ea.kakao_service, "send_alimtalk", boom)

    user = models.User(name="실패", phone="010-0000-0000")
    assert ea._send_portal_invite(user, "https://app.example/x") == "FAILED"


def test_send_portal_invite_no_template(monkeypatch):
    """알림톡 설정됐어도 템플릿 코드 미설정이면 NO_TEMPLATE."""
    from routers import external_accounts as ea

    monkeypatch.setattr(ea.kakao_service, "is_configured_alimtalk", lambda: True)
    monkeypatch.setattr(ea, "resolve_integration", lambda key: None)

    user = models.User(name="무템플릿", phone="010-2222-3333")
    assert ea._send_portal_invite(user, "https://app.example/x") == "NO_TEMPLATE"


# ---------------------------------------------------------------------------
# 6. 매직링크 이메일 자동발송 (INC-10) — 이메일 주 채널 + 카카오 폴백 정규화
# ---------------------------------------------------------------------------
def test_send_portal_invite_email_not_configured():
    """이메일(Gmail) 미설정 → NOT_CONFIGURED(발송 시도 없음). 테스트 기본 환경."""
    from routers import external_accounts as ea

    user = models.User(name="갑담당", email="e@portal.example")
    assert ea._send_portal_invite_email(user, "https://app.example/x") == "NOT_CONFIGURED"


def test_send_portal_invite_email_sent(monkeypatch):
    """이메일 설정 → send_mail을 user.email로 1회 호출·SENT. html=True + abs_link 포함."""
    from routers import external_accounts as ea

    sent = {}

    def fake_send_mail(to, subject, body, html=False, **kwargs):
        sent.update(to=to, subject=subject, body=body, html=html, calls=sent.get("calls", 0) + 1)
        return {"sender": "s@hooxipartners.com", "recipients": to}

    monkeypatch.setattr(ea.email_service, "is_configured", lambda: True)
    monkeypatch.setattr(ea.email_service, "send_mail", fake_send_mail)

    user = models.User(name="갑담당", email="invite@portal.example")
    link = "https://app.example/portal/login?token=abc"
    assert ea._send_portal_invite_email(user, link) == "SENT"
    assert sent["to"] == ["invite@portal.example"]
    assert sent["calls"] == 1
    assert sent["html"] is True
    assert link in sent["body"]


def test_send_portal_invite_email_failed_is_swallowed(monkeypatch):
    """발송 예외는 밖으로 새지 않고 FAILED로 흡수(계정 발급 보호)."""
    from routers import external_accounts as ea

    def boom(**kwargs):
        raise ea.email_service.EmailConfigError("발송 실패")

    monkeypatch.setattr(ea.email_service, "is_configured", lambda: True)
    monkeypatch.setattr(ea.email_service, "send_mail", boom)

    user = models.User(name="실패", email="fail@portal.example")
    assert ea._send_portal_invite_email(user, "https://app.example/x") == "FAILED"


def test_deliver_prefers_email_over_kakao(monkeypatch):
    """이메일 성공하면 카카오는 시도하지 않는다(중복 발송 방지) → EMAIL_SENT."""
    from routers import external_accounts as ea

    monkeypatch.setattr(ea.email_service, "is_configured", lambda: True)
    monkeypatch.setattr(ea.email_service, "send_mail", lambda **kw: {"recipients": kw["to"]})

    def must_not_call(user, abs_link):  # pragma: no cover - 호출되면 실패
        raise AssertionError("이메일 성공 시 카카오는 시도하지 않아야 한다")

    monkeypatch.setattr(ea, "_send_portal_invite", must_not_call)

    user = models.User(name="갑", email="pref@portal.example", phone="010-0000-0000")
    assert ea._deliver_magic_link(user, "https://app.example/x") == "EMAIL_SENT"


def test_deliver_falls_back_to_kakao(monkeypatch):
    """이메일 미설정 + 카카오 SENT → KAKAO_SENT(폴백)."""
    from routers import external_accounts as ea

    monkeypatch.setattr(ea.email_service, "is_configured", lambda: False)
    monkeypatch.setattr(ea, "_send_portal_invite", lambda user, abs_link: "SENT")

    user = models.User(name="갑", email="fb@portal.example", phone="010-0000-0000")
    assert ea._deliver_magic_link(user, "https://app.example/x") == "KAKAO_SENT"


def test_deliver_email_failed_normalized(monkeypatch):
    """이메일 FAILED + 카카오 발송 불가 → EMAIL_FAILED로 정규화."""
    from routers import external_accounts as ea

    monkeypatch.setattr(ea.email_service, "is_configured", lambda: True)
    monkeypatch.setattr(ea, "_send_portal_invite_email", lambda user, abs_link: "FAILED")
    monkeypatch.setattr(ea, "_send_portal_invite", lambda user, abs_link: "NOT_CONFIGURED")

    user = models.User(name="갑", email="ef@portal.example")
    assert ea._deliver_magic_link(user, "https://app.example/x") == "EMAIL_FAILED"


def test_provision_delivery_email_sent(client, manager_headers, staff_headers, monkeypatch):
    """엔드포인트 통합: 이메일 설정 → 발급 delivery EMAIL_SENT + send_mail이 user.email로 호출."""
    from routers import external_accounts as ea

    sent = {}

    def fake_send_mail(to, subject, body, html=False, **kwargs):
        sent.update(to=to, calls=sent.get("calls", 0) + 1)
        return {"recipients": to}

    monkeypatch.setattr(ea.email_service, "is_configured", lambda: True)
    monkeypatch.setattr(ea.email_service, "send_mail", fake_send_mail)

    ca = _mk_client(client, staff_headers, "이메일발송운수사")
    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "email-sent@portal.example", "role": "PARTNER", "client_id": ca,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["delivery"] == "EMAIL_SENT"
    assert body["magic_link"] and "token=" in body["magic_link"]  # 폴백 문자열 유지
    assert sent["to"] == ["email-sent@portal.example"]
    assert sent["calls"] == 1


def test_provision_delivery_email_failed_still_201(client, manager_headers, staff_headers, monkeypatch):
    """엔드포인트 통합: send_mail 예외여도 계정 발급은 201·magic_link 유지 → delivery EMAIL_FAILED."""
    from routers import external_accounts as ea

    def boom(**kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(ea.email_service, "is_configured", lambda: True)
    monkeypatch.setattr(ea.email_service, "send_mail", boom)

    ca = _mk_client(client, staff_headers, "이메일실패운수사")
    r = client.post(EXTERNAL, headers=manager_headers, json={
        "email": "email-failed@portal.example", "role": "PARTNER", "client_id": ca,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["delivery"] == "EMAIL_FAILED"
    assert body["magic_link"] and "token=" in body["magic_link"]
