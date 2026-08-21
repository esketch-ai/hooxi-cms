"""고객사 옵션 API — 경량 전건 목록(200건 상한 문제의 근본 해결) + 경로 매칭·enforce 전역 허용."""

import models
from access_control import is_path_allowed


def test_client_options_returns_all_min_fields(client, admin_headers):
    db = models.SessionLocal()
    try:
        db.query(models.Client).filter(
            models.Client.company_name.like("TESTOPT%")).delete(synchronize_session=False)
        db.add_all([
            models.Client(client_type="TRANSPORT", company_name="TESTOPT운수", region="서울",
                          biz_reg_no="893-11-11111"),
            models.Client(client_type="BUILDING", company_name="TESTOPT빌딩", region="부산"),
        ])
        db.commit()
        r = client.get("/api/v1/clients/options", headers=admin_headers)
        assert r.status_code == 200, r.text  # /{client_id}에 안 삼켜짐(선언 순서)
        names = {x["company_name"] for x in r.json()}
        assert {"TESTOPT운수", "TESTOPT빌딩"} <= names
        row = [x for x in r.json() if x["company_name"] == "TESTOPT운수"][0]
        assert set(row.keys()) == {"client_id", "client_type", "company_name",
                                   "region", "biz_reg_no", "contract_status",
                                   "main_contact_name", "main_contact_email",
                                   "main_contact_phone"}
        # 구분 필터
        r2 = client.get("/api/v1/clients/options?client_type=TRANSPORT", headers=admin_headers)
        n2 = {x["company_name"] for x in r2.json()}
        assert "TESTOPT운수" in n2 and "TESTOPT빌딩" not in n2
    finally:
        db.query(models.Client).filter(
            models.Client.company_name.like("TESTOPT%")).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_client_options_globally_allowed_in_enforce():
    """enforce 모드에서 /clients 메뉴가 없는 그룹도 옵션 조회는 가능(전 화면 드롭다운)."""
    assert is_path_allowed("GET", "/api/v1/clients/options", [])
    assert not is_path_allowed("POST", "/api/v1/clients/options", [])  # 변경류는 여전히 메뉴 필요
    assert not is_path_allowed("GET", "/api/v1/clients", [])  # 목록 본편은 /clients 메뉴 필요
