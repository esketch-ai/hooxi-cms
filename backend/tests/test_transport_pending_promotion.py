"""운수사 대기/정식 상태머신 — 사업자번호 게이트·승격·빈칸병합.

- 사업자번호 없는 회사명만 → 대기: Dropbox 폴더 미생성.
- 사업자번호 채워지면 → 정식 승격: 폴더 provision.
- 중복 매칭 시 빈 칸만 채움(기존 유지), 중복/신규 생성 없음.
"""

import io

import openpyxl

import models
from services import client_folders, dropbox_storage


def _std_xlsx(rows):
    hdr = ["회사명", "사업자등록번호", "법인등록번호", "지역", "대표자", "전화", "팩스",
           "주소", "면허일자", "시내", "농어촌", "시외"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(hdr)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(client, headers, data, entity="transport"):
    return client.post(
        f"/api/v1/imports/{entity}/commit",
        headers=headers,
        files={"file": ("t.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


def test_pending_no_folder_then_promote(client, staff_headers, monkeypatch):
    # Dropbox 설정됨 + ensure_folder 캡처
    monkeypatch.setenv("DROPBOX_APP_KEY", "k")
    monkeypatch.setenv("DROPBOX_APP_SECRET", "s")
    monkeypatch.setenv("DROPBOX_REFRESH_TOKEN", "r")
    created = []
    monkeypatch.setattr(dropbox_storage, "ensure_folder", lambda p: created.append(p) or True)

    db = models.SessionLocal()
    try:
        db.query(models.Client).filter(
            models.Client.company_name.in_(["대기운수", "정식운수"])
        ).delete(synchronize_session=False)
        db.commit()

        # 1) 사업자번호 없는 '대기운수' + 있는 '정식운수' 동시 업로드
        d1 = _std_xlsx([
            ["대기운수", None, None, "서울", "김", None, None, None, None, None, None, None],
            ["정식운수", "771-77-77777", None, "서울", "이", None, None, None, None, None, None, None],
        ])
        r1 = _upload(client, staff_headers, d1)
        assert r1.status_code == 200, r1.text

        db.expire_all()
        pend = db.query(models.Client).filter_by(company_name="대기운수").first()
        formal = db.query(models.Client).filter_by(company_name="정식운수").first()
        assert pend is not None and formal is not None

        # provision 직접 호출로 게이트 확인 — 대기는 skip, 정식은 생성
        rp = client_folders.provision(db, pend)
        assert rp.get("skipped") is True and rp.get("reason") == "pending_no_biz_reg_no"
        assert pend.dropbox_folder is None
        rf = client_folders.provision(db, formal)
        assert rf.get("skipped") is False and formal.dropbox_folder is not None

        # 2) 승격 — '대기운수'에 사업자번호가 채워지는 재업로드 → 정식 전환(폴더 생성 대상)
        d2 = _std_xlsx([
            ["대기운수", "772-77-77772", None, "서울", "김", None, None, None, None, None, None, None],
        ])
        r2 = _upload(client, staff_headers, d2)
        assert r2.status_code == 200, r2.text
        assert r2.json()["created"] == 0 and r2.json()["updated"] == 1  # 중복 생성 없음

        db.expire_all()
        pend2 = db.query(models.Client).filter_by(company_name="대기운수").first()
        assert pend2.biz_reg_no == "772-77-77772"  # 사업자번호 채워짐(승격)
        rp2 = client_folders.provision(db, pend2)
        assert rp2.get("skipped") is False  # 이제 정식 → 폴더 생성됨
    finally:
        db.query(models.Client).filter(
            models.Client.company_name.in_(["대기운수", "정식운수"])
        ).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_merge_fills_empty_only(client, staff_headers):
    db = models.SessionLocal()
    try:
        db.query(models.Client).filter_by(company_name="병합운수").delete(synchronize_session=False)
        db.commit()
        db.add(models.Client(client_type="TRANSPORT", company_name="병합운수",
                             biz_reg_no="773-77-77773", ceo_name="기존대표", region="서울"))
        db.commit()

        # 대표자·지역은 기존 값 유지, 비어있던 법인번호·팩스만 채워짐
        d = _std_xlsx([
            ["병합운수", "773-77-77773", "111111-0000000", "부산", "새대표", None, "051-1-1",
             None, None, None, None, None],
        ])
        r = _upload(client, staff_headers, d)
        assert r.status_code == 200 and r.json()["updated"] == 1 and r.json()["created"] == 0
        db.expire_all()
        c = db.query(models.Client).filter_by(company_name="병합운수").first()
        assert c.ceo_name == "기존대표"  # 유지
        assert c.region == "서울"        # 유지
        assert c.corp_reg_no == "111111-0000000"  # 빈 칸 보강
        assert c.fax == "051-1-1"        # 빈 칸 보강
    finally:
        db.query(models.Client).filter_by(company_name="병합운수").delete(synchronize_session=False)
        db.commit()
        db.close()
