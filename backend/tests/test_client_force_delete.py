"""고객사 강제 삭제(종속 캐스케이드) — 재확인 + 담당자 명의 확인 + 사업/정산 차단.

SQLite는 FK를 강제하지 않으므로 '무엇이 삭제되는가(완전성)'를 검증한다. FK 의존 순서 자체의
실효(순환/자기참조 정리)는 운영 Postgres에서 별도 확인.
"""

from datetime import datetime

import models

API = "/api/v1"


def _seed_rich_client(cid):
    """종속 데이터가 풍부한 고객사를 DB로 구성 (사업/정산 제외)."""
    db = models.SessionLocal()
    try:
        db.add(models.Client(client_id=cid, client_type="TRANSPORT",
                             company_name="강제삭제테스트", contract_status="ACTIVE"))
        db.flush()
        db.add(models.ActivityHistory(history_id=cid + "-h1", client_id=cid, manager_id="u-admin",
               activity_date=datetime(2026, 8, 1), activity_type="CALL", title="이력"))
        db.add(models.IssueComment(comment_id=cid + "-c1", history_id=cid + "-h1",
               manager_id="u-admin", content="코멘트"))
        db.add(models.Asset(asset_id=cid + "-a1", client_id=cid, asset_group="MOBILITY"))
        db.add(models.ReportSubscription(sub_id=cid + "-sub1", client_id=cid, report_type="월간"))
        db.add(models.ReportRecipient(recipient_id=cid + "-r1", client_id=cid,
               email="a@b.com", sub_id=cid + "-sub1"))
        db.add(models.ReportDelivery(report_id=cid + "-d1", client_id=cid,
               period="2026-08", report_type="월간"))
        db.flush()
        db.add(models.Document(doc_id=cid + "-doc1", client_id=cid, doc_type="ETC", title="문서",
               file_url="x", history_id=cid + "-h1", asset_id=cid + "-a1", report_id=cid + "-d1"))
        db.flush()
        db.add(models.ReportSendLog(send_id=cid + "-sl1", report_id=cid + "-d1", seq=1,
               sent_doc_id=cid + "-doc1"))
        d = db.get(models.ReportDelivery, cid + "-d1")
        d.doc_id = cid + "-doc1"
        d.pinned_doc_id = cid + "-doc1"  # 순환참조
        db.add(models.Schedule(schedule_id=cid + "-s1", client_id=cid, manager_id="u-admin",
               schedule_type="MEETING", title="일정", start_at=datetime(2026, 8, 2), history_id=cid + "-h1"))
        db.add(models.Schedule(schedule_id=cid + "-s2", client_id=cid, manager_id="u-admin",
               schedule_type="MEETING", title="자식일정", start_at=datetime(2026, 8, 3),
               parent_schedule_id=cid + "-s1"))  # 자기참조
        db.add(models.KakaoContact(contact_id=cid + "-k1", kakao_user_key=cid + "-kuk1",
               client_id=cid, status="APPROVED"))
        db.add(models.ChatThread(thread_id=cid + "-t1", client_id=cid,
               kakao_contact_id=cid + "-k1", mode="AI", status="OPEN"))
        db.flush()
        db.add(models.ChatMessage(message_id=cid + "-m1", thread_id=cid + "-t1",
               sender_type="CUSTOMER", content="msg"))
        db.add(models.SegmentSend(send_id=cid + "-ss1"))
        db.flush()
        db.add(models.SegmentSendLog(log_id=cid + "-ssl1", send_id=cid + "-ss1", client_id=cid))
        db.commit()
    finally:
        db.close()


def test_force_delete_cascades_all_dependents(client, admin_headers):
    cid = "fc-1"
    _seed_rich_client(cid)

    # 종속 있으니 일반 삭제 409
    r = client.delete(API + "/clients/" + cid, headers=admin_headers)
    assert r.status_code == 409

    # 강제지만 담당자 이름 불일치 → 403
    r = client.delete(API + "/clients/" + cid + "?force=true&confirm_name=아무개", headers=admin_headers)
    assert r.status_code == 403

    # 강제 + 담당자 본인 이름(관리자) → 200
    r = client.delete(API + "/clients/" + cid + "?force=true&confirm_name=관리자", headers=admin_headers)
    assert r.status_code == 200, r.text
    assert "강제 삭제" in r.json()["message"]

    # 전 종속 제거 검증
    db = models.SessionLocal()
    try:
        checks = [
            (models.Client, models.Client.client_id == cid),
            (models.ActivityHistory, models.ActivityHistory.client_id == cid),
            (models.IssueComment, models.IssueComment.history_id == cid + "-h1"),
            (models.Asset, models.Asset.client_id == cid),
            (models.Document, models.Document.doc_id == cid + "-doc1"),
            (models.ReportDelivery, models.ReportDelivery.client_id == cid),
            (models.ReportSendLog, models.ReportSendLog.send_id == cid + "-sl1"),
            (models.ReportRecipient, models.ReportRecipient.client_id == cid),
            (models.ReportSubscription, models.ReportSubscription.client_id == cid),
            (models.Schedule, models.Schedule.client_id == cid),
            (models.ChatThread, models.ChatThread.client_id == cid),
            (models.ChatMessage, models.ChatMessage.thread_id == cid + "-t1"),
            (models.KakaoContact, models.KakaoContact.client_id == cid),
            (models.SegmentSendLog, models.SegmentSendLog.client_id == cid),
        ]
        for m, cond in checks:
            assert db.query(m).filter(cond).count() == 0, "남은 종속: " + m.__name__
    finally:
        db.close()


def test_force_delete_blocked_by_project_or_settlement(client, admin_headers):
    """사업 참여(참여 차량)가 있으면 강제여도 409 — 공유 사업 보호."""
    db = models.SessionLocal()
    try:
        db.add(models.Client(client_id="fc-2", client_type="TRANSPORT",
                             company_name="사업참여고객", contract_status="ACTIVE"))
        db.add(models.Project(project_id="fc-p1", project_name="사업", project_status="모니터링"))
        db.flush()
        db.add(models.ProjectVehicle(vehicle_id="fc-pv1", project_id="fc-p1", client_id="fc-2",
               vehicle_no="12가3456"))
        db.commit()
    finally:
        db.close()

    r = client.delete(API + "/clients/fc-2?force=true&confirm_name=관리자", headers=admin_headers)
    assert r.status_code == 409
    assert "사업 참여" in r.json()["detail"]

    # 고객사는 그대로 존재
    db = models.SessionLocal()
    try:
        assert db.query(models.Client).filter(models.Client.client_id == "fc-2").count() == 1
    finally:
        db.close()
