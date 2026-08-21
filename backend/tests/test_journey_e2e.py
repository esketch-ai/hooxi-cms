"""관점별 통합 여정 E2E — 파트너(카카오→포털→상담→이슈) · 투자사 격리 · 내부 관리자.

사용자 정의 여정을 한 테스트에서 끝까지 검증한다(개별 기능 테스트와 별개의 배선 검증).
"""

import models
from auth import create_access_token

WEBHOOK = "/api/v1/kakao/webhook?secret=test-webhook-secret"


def _cleanup(db):
    db.query(models.ChatMessage).delete(synchronize_session=False) if False else None
    for q in [
        db.query(models.ActivityHistory).filter(models.ActivityHistory.title.like("%TESTJRN%")),
        db.query(models.ActivityHistory).filter(models.ActivityHistory.content.like("%TESTJRN%")),
    ]:
        q.delete(synchronize_session=False)
    ths = [t.thread_id for t in db.query(models.ChatThread).join(
        models.KakaoContact, models.ChatThread.kakao_contact_id == models.KakaoContact.contact_id
    ).filter(models.KakaoContact.kakao_user_key.like("t-jrn-%")).all()]
    if ths:
        db.query(models.ActivityHistory).filter(
            models.ActivityHistory.chat_thread_id.in_(ths)).delete(synchronize_session=False)
        db.query(models.ChatMessage).filter(
            models.ChatMessage.thread_id.in_(ths)).delete(synchronize_session=False)
        db.query(models.ChatThread).filter(
            models.ChatThread.thread_id.in_(ths)).delete(synchronize_session=False)
    db.query(models.KakaoContact).filter(
        models.KakaoContact.kakao_user_key.like("t-jrn-%")).delete(synchronize_session=False)
    db.query(models.User).filter(
        models.User.email.like("%jrn-test.example%")).delete(synchronize_session=False)
    db.query(models.User).filter(
        models.User.name.like("TESTJRN%")).delete(synchronize_session=False)
    db.query(models.FleetStatus).filter(
        models.FleetStatus.company_name.like("TESTJRN%")).delete(synchronize_session=False)
    db.query(models.ProjectVehicle).filter(models.ProjectVehicle.project_id.in_(
        db.query(models.Project.project_id).filter(models.Project.project_name.like("TESTJRN%"))
    )).delete(synchronize_session=False)
    db.query(models.Project).filter(
        models.Project.project_name.like("TESTJRN%")).delete(synchronize_session=False)
    db.query(models.Client).filter(
        models.Client.company_name.like("TESTJRN%")).delete(synchronize_session=False)
    db.commit()


def test_partner_full_journey(client, staff_headers, monkeypatch):
    """파트너사(운수사) 관점: 채널 승인 → '포털' 셀프 발급 → 포털 열람(P1) → 상담 → 이슈."""
    monkeypatch.setenv("KAKAO_WEBHOOK_SECRET", "test-webhook-secret")
    db = models.SessionLocal()
    try:
        _cleanup(db)
        mgr = db.query(models.User).filter(models.User.role == "MANAGER").first()
        c = models.Client(client_type="TRANSPORT", company_name="TESTJRN운수",
                          region="서울", manager_id=mgr.user_id)
        db.add(c); db.commit()
        db.add(models.FleetStatus(client_id=c.client_id, region="서울", industry="CITY",
                                  company_name="TESTJRN운수", period="2026-06",
                                  license_count=60, total_count=60, electric=25))
        contact = models.KakaoContact(kakao_user_key="t-jrn-partner", name="TESTJRN김과장",
                                      status="APPROVED", client_id=c.client_id,
                                      phone="010-3333-4444")
        db.add(contact); db.commit()
        cid, contact_id = c.client_id, contact.contact_id
    finally:
        db.close()

    # ① 챗봇 '포털' → 링크 회신
    r = client.post(WEBHOOK, json={"userRequest": {"user": {"id": "t-jrn-partner"},
                                                   "utterance": "포털 부탁해요"}})
    text = r.json()["template"]["outputs"][0]["simpleText"]["text"]
    assert "portal/login?token=" in text
    token = text.split("token=")[1].split()[0].strip()

    # ② 매직링크 검증 → 포털 세션
    rv = client.post("/api/v1/portal/auth/verify", json={"token": token})
    assert rv.status_code == 200, rv.text
    ph = {"Authorization": "Bearer " + rv.json()["access_token"]}

    # ③ 포털에서 자기 데이터 열람(P1) — 계약대수·자기 스코프
    me = client.get("/api/v1/portal/me", headers=ph).json()
    assert me["role"] == "PARTNER" and me["org_name"] == "TESTJRN운수"
    fleet = client.get("/api/v1/portal/fleet-status", headers=ph).json()
    assert len(fleet) == 1 and fleet[0]["electric"] == 25
    # 내부 API는 여전히 차단(격리)
    assert client.get("/api/v1/clients", headers=ph).status_code == 403

    # ④ 문의(상담) → 담당자 연결
    client.post(WEBHOOK, json={"userRequest": {"user": {"id": "t-jrn-partner"},
                                               "utterance": "정산 문의 TESTJRN 상담"}})
    db = models.SessionLocal()
    try:
        th = (db.query(models.ChatThread)
              .join(models.KakaoContact,
                    models.ChatThread.kakao_contact_id == models.KakaoContact.contact_id)
              .filter(models.KakaoContact.kakao_user_key == "t-jrn-partner").first())
        assert th is not None and th.status == "WAITING"  # 핸드오프됨
        tid = th.thread_id
    finally:
        db.close()

    # ⑤ 내부 담당자: 상담 → 이슈 승격 → 이슈에 스레드 연결
    ri = client.post(f"/api/v1/chat/threads/{tid}/escalate", headers=staff_headers)
    assert ri.status_code == 200
    assert ri.json()["chat_thread_id"] == tid
    assert "TESTJRN운수" in ri.json()["title"]

    db = models.SessionLocal()
    try:
        db.query(models.ActivityHistory).filter_by(chat_thread_id=tid).delete(
            synchronize_session=False)
        db.commit()
        _cleanup(db)
    finally:
        db.close()


def test_investor_scope_and_isolation(client, staff_headers, manager_headers):
    """투자사 관점: 자기 거래 사업만 + 운수사 전용 P1 403 + 내부 차단."""
    db = models.SessionLocal()
    try:
        _cleanup(db)
        b = models.Buyer(name="TESTJRN증권", buyer_type="증권사")
        p = models.Project(project_name="TESTJRN사업", project_status="추진")
        db.add_all([b, p]); db.commit()
        db.add(models.ProjectSale(project_id=p.project_id, buyer_id=b.buyer_id,
                                  buyer_name="TESTJRN증권"))
        inv = models.User(email="inv@jrn-test.example", name="TESTJRN투자역",
                          role="INVESTOR", status="ACTIVE", buyer_id=b.buyer_id)
        db.add(inv); db.commit()
        db.refresh(inv); db.expunge(inv)
        bid = b.buyer_id
    finally:
        db.close()
    h = {"Authorization": "Bearer " + create_access_token(inv)}
    projects = client.get("/api/v1/portal/projects", headers=h).json()
    assert [x["project_name"] for x in projects] == ["TESTJRN사업"]
    # 운수사 전용(P1) 403 · 내부 403
    assert client.get("/api/v1/portal/fleet-status", headers=h).status_code == 403
    assert client.get("/api/v1/portal/settlements", headers=h).status_code == 403
    assert client.get("/api/v1/finance-ledger", headers=h).status_code == 403
    db = models.SessionLocal()
    try:
        db.query(models.ProjectSale).filter_by(buyer_id=bid).delete(synchronize_session=False)
        db.query(models.Buyer).filter_by(buyer_id=bid).delete(synchronize_session=False)
        db.commit()
        _cleanup(db)
    finally:
        db.close()


def test_admin_ops_perspective(client, admin_headers):
    """내부 관리자 관점: 접근그룹 메타·경영 관찰·발급 미리보기 API가 전부 응답."""
    assert client.get("/api/v1/access-groups/meta", headers=admin_headers).status_code == 200
    assert client.get("/api/v1/observe/summary?months=12", headers=admin_headers).status_code == 200
    assert client.get("/api/v1/observe/detail?topic=rate", headers=admin_headers).status_code == 200
    assert client.get("/api/v1/external-accounts", headers=admin_headers).status_code == 200
    assert client.get("/api/v1/histories/export", headers=admin_headers).status_code == 400  # 무필터 금지
