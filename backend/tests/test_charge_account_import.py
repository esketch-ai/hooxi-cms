"""충전 관제 계정 → 자산·연동 일괄 등록(외부기관 계정 관리). 합성 데이터만(실비밀값 없음)."""

import io

import openpyxl

import models

IMPORT = "/api/v1/assets/charge-accounts/import"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(rows):
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["구분", "회사명", "시내/마을", "홈페이지 명", "홈페이지 주소", "아이디", "비밀번호", "비고"])
    for r in rows:
        ws.append(r)
    b = io.BytesIO(); wb.save(b); return b.getvalue()


def _clean():
    db = models.SessionLocal()
    try:
        db.query(models.Asset).filter(models.Asset.usage_purpose == "충전량 수집").delete(
            synchronize_session=False)
        db.query(models.Client).filter(models.Client.company_name.in_(
            ["춘천시민버스", "협진여객"])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def _seed_client(company, region):
    db = models.SessionLocal()
    try:
        c = models.Client(client_type="TRANSPORT", company_name=company, region=region)
        db.add(c); db.commit(); return c.client_id
    finally:
        db.close()


def test_import_carryforward_and_status(client, staff_headers):
    _clean()
    _seed_client("춘천시민버스", "강원")
    _seed_client("협진여객", "경기")
    rows = [
        # 정상 계정 + 이어지는 2번째 사이트(구분·회사명 공란 → 이어받기)
        ["강원", "춘천시민버스", "시내", "전기버스 통합관리시스템", "http://podo-tms.com/", "chuncheon", "pw1", ""],
        ["", "", "", "충전인프라시스템", "http://cms.e-bab.com/x/login.do", "monitor", "pw2", ""],
        # 전기차 없음 → INACTIVE(계정 없음)
        ["경기", "동안운수", "마을", "X", "", "", "", "전기차 없음"],
        # 로그인 안됨 → ERROR
        ["경기", "협진여객", "시내", "eBAB 펌프킨", "http://x/login.view", "hjin", "secret", "로그인 안됨"],
    ]
    r = client.post(IMPORT, headers=staff_headers, files={"file": ("acc.xlsx", _xlsx(rows), XLSX)})
    assert r.status_code == 200, r.text
    body = r.json()
    # 춘천 2건(이어받기) + 협진 1건 = 3 등록. 동안운수는 고객사 미매칭 → 스킵
    assert body["created"] == 3
    assert body["unmatched"] == 1 and "동안운수" in body["unmatched_names"]

    db = models.SessionLocal()
    try:
        assets = db.query(models.Asset).filter(models.Asset.usage_purpose == "충전량 수집").all()
        by_agency = {a.agency_name: a for a in assets}
        # 이어받기: 2번째 사이트도 춘천시민버스 고객사에 연결
        chun = [a for a in assets if a.agency_name in ("전기버스 통합관리시스템", "충전인프라시스템")]
        assert len(chun) == 2 and all(a.client_id for a in chun)
        # 상태 판정: 로그인 안됨 → ERROR
        assert by_agency["eBAB 펌프킨"].status == "ERROR"
        # 비밀번호는 응답·평문 저장 안 됨: 키 미설정이면 login_password None
        active = by_agency["전기버스 통합관리시스템"]
        assert active.auth_type == "ID_PW" and active.login_id == "chuncheon"
    finally:
        db.close()
    _clean()


def test_password_never_plaintext(client, staff_headers, monkeypatch):
    """키 미설정 시 비밀번호 저장 안 함(메타만) — 응답에 비밀값 필드 없음."""
    _clean()
    _seed_client("춘천시민버스", "강원")
    rows = [["강원", "춘천시민버스", "시내", "포도", "http://podo-tms.com/", "u1", "topsecret", ""]]
    r = client.post(IMPORT, headers=staff_headers, files={"file": ("a.xlsx", _xlsx(rows), XLSX)})
    body = r.json()
    # 응답 어디에도 평문 비밀번호가 없어야 함
    assert "topsecret" not in r.text
    assert set(body.keys()) == {"created", "updated", "client_matched", "unmatched",
                                "unmatched_names", "encrypted", "password_skipped",
                                "encryption_available", "total"}
    if not body["encryption_available"]:
        assert body["password_skipped"] == 1 and body["encrypted"] == 0
        db = models.SessionLocal()
        try:
            a = db.query(models.Asset).filter(models.Asset.usage_purpose == "충전량 수집").first()
            assert a.login_password is None  # 키 없으면 저장 안 함
        finally:
            db.close()
    _clean()


def test_import_reupload_updates(client, staff_headers):
    _clean()
    _seed_client("춘천시민버스", "강원")
    rows = [["강원", "춘천시민버스", "시내", "포도", "http://podo-tms.com/", "u1", "p", ""]]
    f = {"file": ("a.xlsx", _xlsx(rows), XLSX)}
    assert client.post(IMPORT, headers=staff_headers, files=f).json()["created"] == 1
    r2 = client.post(IMPORT, headers=staff_headers, files={"file": ("a.xlsx", _xlsx(rows), XLSX)})
    assert r2.json()["updated"] == 1 and r2.json()["created"] == 0
    _clean()


def test_requires_auth(client):
    assert client.post(IMPORT).status_code == 401
