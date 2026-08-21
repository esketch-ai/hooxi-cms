"""K1 챗봇 '포털' 셀프 발급 — 승인·매칭 자동발급, 재발화 재발급, 미매칭/비활성 안내."""

import models

WEBHOOK = "/api/v1/kakao/webhook?secret=test-webhook-secret"


def _payload(user_key, utterance):
    return {"userRequest": {"user": {"id": user_key}, "utterance": utterance}}


def _cleanup(db):
    db.query(models.ChatMessage).filter(models.ChatMessage.thread_id.in_(
        db.query(models.ChatThread.thread_id).join(
            models.KakaoContact,
            models.ChatThread.kakao_contact_id == models.KakaoContact.contact_id
        ).filter(models.KakaoContact.kakao_user_key.like("t-kps-%"))
    )).delete(synchronize_session=False)
    db.query(models.ChatThread).filter(models.ChatThread.kakao_contact_id.in_(
        db.query(models.KakaoContact.contact_id).filter(
            models.KakaoContact.kakao_user_key.like("t-kps-%"))
    )).delete(synchronize_session=False)
    db.query(models.ActivityHistory).filter(
        models.ActivityHistory.title.like("%TESTKPS%")).delete(synchronize_session=False)
    db.query(models.User).filter(
        models.User.email.like("kakao-%@portal.local"),
        models.User.name.like("TESTKPS%")).delete(synchronize_session=False)
    db.query(models.KakaoContact).filter(
        models.KakaoContact.kakao_user_key.like("t-kps-%")).delete(synchronize_session=False)
    db.query(models.Client).filter(
        models.Client.company_name.like("TESTKPS%")).delete(synchronize_session=False)
    db.commit()


def test_portal_utterance_issues_pass(client, monkeypatch):
    monkeypatch.setenv("KAKAO_WEBHOOK_SECRET", "test-webhook-secret")
    db = models.SessionLocal()
    try:
        _cleanup(db)
        c = models.Client(client_type="TRANSPORT", company_name="TESTKPS운수", region="서울")
        db.add(c); db.commit()
        contact = models.KakaoContact(
            kakao_user_key="t-kps-ok", name="TESTKPS김대표",
            status="APPROVED", client_id=c.client_id, phone="010-1111-2222",
        )
        db.add(contact); db.commit()
        cid, contact_id = c.client_id, contact.contact_id
    finally:
        db.close()
    # '포털' 발화 → 링크 회신 + 계정 자동 생성(1개월권)
    r = client.post(WEBHOOK, json=_payload("t-kps-ok", "포털 접속하고 싶어요"))
    assert r.status_code == 200, r.text
    text = r.json()["template"]["outputs"][0]["simpleText"]["text"]
    assert "portal/login?token=" in text and "1개월권" in text
    db = models.SessionLocal()
    try:
        acc = db.query(models.User).filter_by(
            email=f"kakao-{contact_id}@portal.local").first()
        assert acc is not None and acc.role == "PARTNER" and acc.client_id == cid
        assert acc.portal_expires_at is not None
        uid = acc.user_id
        # 스레드 SYSTEM 흔적에 링크 미포함(R2-E6)
        sysmsg = (db.query(models.ChatMessage)
                  .filter(models.ChatMessage.sender_type == "SYSTEM",
                          models.ChatMessage.content.like("%포털 이용권%")).first())
        assert sysmsg is not None and "token" not in (sysmsg.content or "")
        # 활동 이력 [자동]
        hist = (db.query(models.ActivityHistory)
                .filter_by(client_id=cid, activity_type="PORTAL").first())
        assert hist is not None and "챗봇" in hist.title
    finally:
        db.close()
    # 재발화 → 같은 계정 재발급(행 미증가)
    r2 = client.post(WEBHOOK, json=_payload("t-kps-ok", "포털"))
    assert "portal/login?token=" in r2.json()["template"]["outputs"][0]["simpleText"]["text"]
    db = models.SessionLocal()
    try:
        cnt = db.query(models.User).filter_by(
            email=f"kakao-{contact_id}@portal.local").count()
        assert cnt == 1
        # 비활성화 → 자동 재발급 거부
        acc = db.query(models.User).filter_by(user_id=uid).first()
        acc.status = "INACTIVE"; db.commit()
    finally:
        db.close()
    r3 = client.post(WEBHOOK, json=_payload("t-kps-ok", "포털"))
    assert "제한" in r3.json()["template"]["outputs"][0]["simpleText"]["text"]
    db = models.SessionLocal()
    try:
        _cleanup(db)
    finally:
        db.close()


def test_portal_utterance_without_client_match(client, monkeypatch):
    monkeypatch.setenv("KAKAO_WEBHOOK_SECRET", "test-webhook-secret")
    db = models.SessionLocal()
    try:
        _cleanup(db)
        contact = models.KakaoContact(
            kakao_user_key="t-kps-nomatch", name="TESTKPS미매칭",
            status="APPROVED", client_id=None,
        )
        db.add(contact); db.commit()
    finally:
        db.close()
    r = client.post(WEBHOOK, json=_payload("t-kps-nomatch", "포털"))
    text = r.json()["template"]["outputs"][0]["simpleText"]["text"]
    assert "확인" in text and "token" not in text  # 발급 안 됨
    db = models.SessionLocal()
    try:
        assert db.query(models.User).filter(
            models.User.email.like("kakao-%@portal.local"),
            models.User.name.like("TESTKPS미매칭%")).count() == 0
        _cleanup(db)
    finally:
        db.close()


def test_escalate_thread_to_issue(client, staff_headers, monkeypatch):
    """K3 상담→이슈 승격 — 생성·중복 방지·SYSTEM 메시지·양방향 키."""
    db = models.SessionLocal()
    try:
        _cleanup(db)
        c = models.Client(client_type="TRANSPORT", company_name="TESTKPS승격운수", region="부산")
        db.add(c); db.commit()
        contact = models.KakaoContact(kakao_user_key="t-kps-esc", name="TESTKPS문의자",
                                      status="APPROVED", client_id=c.client_id)
        db.add(contact); db.commit()
        th = models.ChatThread(client_id=c.client_id, kakao_contact_id=contact.contact_id,
                               mode="HUMAN", status="WAITING")
        db.add(th); db.commit()
        db.add(models.ChatMessage(thread_id=th.thread_id, sender_type="CUSTOMER",
                                  content="정산 금액이 이상해요 TESTKPS"))
        db.commit()
        tid, cid = th.thread_id, c.client_id
    finally:
        db.close()
    r = client.post(f"/api/v1/chat/threads/{tid}/escalate", headers=staff_headers)
    assert r.status_code == 200, r.text
    issue = r.json()
    assert issue["activity_type"] == "ISSUE" and issue["issue_status"] == "OPEN"
    assert issue["chat_thread_id"] == tid
    assert "TESTKPS승격운수" in issue["title"]
    assert "정산 금액이 이상해요" in issue["content"]
    # 중복 승격 → 동일 이슈 반환
    r2 = client.post(f"/api/v1/chat/threads/{tid}/escalate", headers=staff_headers)
    assert r2.json()["history_id"] == issue["history_id"]
    db = models.SessionLocal()
    try:
        assert (db.query(models.ActivityHistory)
                .filter_by(chat_thread_id=tid).count()) == 1
        sysmsg = (db.query(models.ChatMessage)
                  .filter_by(thread_id=tid, sender_type="SYSTEM").first())
        assert sysmsg is not None and "이슈로 등록" in sysmsg.content
        db.query(models.ActivityHistory).filter_by(chat_thread_id=tid).delete(
            synchronize_session=False)
        db.commit()
        _cleanup(db)
    finally:
        db.close()
