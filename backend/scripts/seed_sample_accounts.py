"""추가 샘플 시드 — 운수사·건물 고객사 확대 + 기관별 수집 계정(멱등).

수집 계정 관리·월초 점검 테스트용. 고정 PK(sample-*)로 재실행 시 중복 없음.
자산 인증정보는 crypto.encrypt로 암호화 저장 — 실행 시 ASSET_ENC_KEY 필수
(프로덕션과 동일 키로 실행해야 프로덕션에서 reveal 가능).

실행:
  DATABASE_URL=postgresql://... ASSET_ENC_KEY=<프로덕션 키> \
    python scripts/seed_sample_accounts.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Asset, Client, SessionLocal, User, init_db  # noqa: E402
from services import crypto  # noqa: E402

# 담당 PM 후보 이메일(기존 시드 사용자) — 없으면 첫 ADMIN에 배정
PM_EMAILS = [
    "demo.manager@hooxipartners.com",
    "demo.staff1@hooxipartners.com",
    "demo.staff2@hooxipartners.com",
]

REGION_COORDS = {
    "서울": (37.5665, 126.9780), "경기": (37.2894, 127.0536), "인천": (37.4563, 126.7052),
    "부산": (35.1796, 129.0756), "대구": (35.8714, 128.6014), "광주": (35.1595, 126.8526),
    "대전": (36.3504, 127.3845), "울산": (35.5384, 129.3114), "강원": (37.8228, 128.1555),
    "충남": (36.6588, 126.6728), "전북": (35.8242, 127.1480), "경남": (35.4606, 128.2132),
}

# (suffix, 이름, 유형, 지역, 대표, 담당자, 연락처, 이메일, 계약상태, 보고서수신,
#  [ (자산suffix, group, type, spec, 기관, site, auth_type, login_id, secret) ... ])
SAMPLES = [
    # ── 운수사 (TRANSPORT) — ETAS·BMS 계정 ──
    ("un01", "대한고속버스", "TRANSPORT", "서울", "김대한", "박운영", "010-3001-0001",
     "op@daehan.co.kr", "ACTIVE", "Y", [
        ("a1", "MOBILITY", "BUS", "고속버스 42대", "ETAS 운행기록분석", "https://etas.kotsa.or.kr", "ID_PW", "daehan-etas", "Etas!2026daehan"),
        ("a2", "MOBILITY", "BUS", "시내버스 60대", "경기 BMS", "https://gbms.gg.go.kr", "ID_PW", "daehan-gbms", "Gbms#daehan01"),
     ]),
    ("un02", "서울택시조합", "TRANSPORT", "서울", "이서울", "최배차", "010-3001-0002",
     "fleet@seoultaxi.kr", "ACTIVE", "Y", [
        ("a1", "MOBILITY", "TAXI", "택시 210대", "ETAS 운행기록분석", "https://etas.kotsa.or.kr", "ID_PW", "seoultaxi-etas", "Taxi@etas2026"),
     ]),
    ("un03", "부산화물운송", "TRANSPORT", "부산", "정부산", "강물류", "010-3001-0003",
     "cargo@busanwm.co.kr", "ACTIVE", "Y", [
        ("a1", "MOBILITY", "TRUCK", "화물차 88대", "ETAS 운행기록분석", "https://etas.kotsa.or.kr", "ID_PW", "busan-cargo", "Cargo!busan88"),
        ("a2", "MOBILITY", "TRUCK", "특수화물 12대", "스마트FMS관제", "https://fms.example.co.kr", "API_KEY", None, "fms-api-busan-7c2a9"),
     ]),
    ("un04", "인천마을버스", "TRANSPORT", "인천", "한인천", "오노선", "010-3001-0004",
     "route@incheonbus.kr", "HOLD", "N", [
        ("a1", "MOBILITY", "BUS", "마을버스 34대", "경기 BMS", "https://gbms.gg.go.kr", "ID_PW", "incheon-bms", "Bms!incheon34"),
     ]),
    ("un05", "대구시티투어", "TRANSPORT", "대구", "문대구", "임관광", "010-3001-0005",
     "tour@daegucity.kr", "ACTIVE", "Y", [
        ("a1", "MOBILITY", "BUS", "관광버스 18대", "ETAS 운행기록분석", "https://etas.kotsa.or.kr", "ID_PW", "daegu-tour", "Tour@daegu18"),
     ]),
    ("un06", "광주콜택시", "TRANSPORT", "광주", "서광주", "노배차", "010-3001-0006",
     "call@gjtaxi.kr", "ACTIVE", "N", [
        ("a1", "MOBILITY", "TAXI", "콜택시 95대", "ETAS 운행기록분석", "https://etas.kotsa.or.kr", "ID_PW", "gj-calltaxi", "Call!gj2026"),
     ]),
    ("un07", "강원고속", "TRANSPORT", "강원", "유강원", "신운수", "010-3001-0007",
     "hi@gangwonexp.kr", "END", "N", [
        ("a1", "MOBILITY", "BUS", "시외버스 27대", "ETAS 운행기록분석", "https://etas.kotsa.or.kr", "ID_PW", "gangwon-etas", "Gw@etas27"),
     ]),
    ("un08", "경남물류", "TRANSPORT", "경남", "배경남", "하물류", "010-3001-0008",
     "log@gnlogis.co.kr", "ACTIVE", "Y", [
        ("a1", "MOBILITY", "TRUCK", "화물차 140대", "ETAS 운행기록분석", "https://etas.kotsa.or.kr", "ID_PW", "gn-logis", "Logis!gn140"),
     ]),

    # ── 건물 (FACILITY) — 태양광 발전사·히트펌프 계정 ──
    ("fa01", "햇살태양광", "FACILITY", "전북", "조햇살", "윤설비", "010-4001-0001",
     "pv@haetsal.kr", "ACTIVE", "Y", [
        ("a1", "FACILITY", "SOLAR", "지붕형 태양광 450kW", "한국에너지공단 RPS", "https://onerec.knrec.or.kr", "ID_PW", "haetsal-rec", "Rec@haetsal26"),
        ("a2", "FACILITY", "SOLAR", "인버터 관제", "한화큐셀 모니터링", "https://qcells.example.com", "ID_PW", "haetsal-qcells", "Qc!haetsal"),
     ]),
    ("fa02", "그린빌딩관리", "FACILITY", "서울", "남그린", "구설비", "010-4001-0002",
     "fm@greenbld.kr", "ACTIVE", "Y", [
        ("a1", "FACILITY", "HEATPUMP", "히트펌프 8RT×6", "설비 원격관제", "https://hvac.example.co.kr", "ID_PW", "greenbld-hp", "Hp!green26"),
        ("a2", "FACILITY", "SOLAR", "BIPV 120kW", "한국에너지공단 RPS", "https://onerec.knrec.or.kr", "API_KEY", None, "rec-api-greenbld-3f81"),
     ]),
    ("fa03", "에너지팜", "FACILITY", "충남", "구에너", "선농장", "010-4001-0003",
     "farm@energyfarm.kr", "ACTIVE", "Y", [
        ("a1", "FACILITY", "SOLAR", "영농형 태양광 300kW", "한국에너지공단 RPS", "https://onerec.knrec.or.kr", "ID_PW", "efarm-rec", "Rec!efarm300"),
     ]),
    ("fa04", "블루히트", "FACILITY", "경기", "천블루", "정설비", "010-4001-0004",
     "svc@blueheat.kr", "ACTIVE", "N", [
        ("a1", "FACILITY", "HEATPUMP", "지열 히트펌프 30RT", "LG 원격관제", "https://lghvac.example.com", "ID_PW", "blueheat-lg", "Lg@blue30"),
     ]),
    ("fa05", "선셋솔라", "FACILITY", "울산", "마선셋", "위발전", "010-4001-0005",
     "sun@sunsetsolar.kr", "HOLD", "N", [
        ("a1", "FACILITY", "SOLAR", "수상 태양광 1.2MW", "한국에너지공단 RPS", "https://onerec.knrec.or.kr", "ID_PW", "sunset-rec", "Rec#sunset12"),
     ]),
    ("fa06", "코어빌딩", "FACILITY", "대전", "고코어", "명설비", "010-4001-0006",
     "core@corebld.kr", "ACTIVE", "Y", [
        ("a1", "FACILITY", "HEATPUMP", "공기열 히트펌프 20RT×4", "설비 원격관제", "https://hvac.example.co.kr", "ID_PW", "corebld-hp", "Hp@core20"),
     ]),
]


def _pm_ids(db):
    ids = []
    for email in PM_EMAILS:
        u = db.query(User).filter(User.email == email).first()
        if u:
            ids.append(u.user_id)
    if not ids:
        admin = db.query(User).filter(User.role == "ADMIN", User.status == "ACTIVE").first()
        if admin:
            ids.append(admin.user_id)
    return ids


def main():
    init_db()
    enc_ok = crypto.encryption_available()
    if not enc_ok:
        print("⚠ ASSET_ENC_KEY 미설정 — 자산 인증정보는 비워두고 진행")

    db = SessionLocal()
    new_clients = new_assets = 0
    try:
        pms = _pm_ids(db)
        if not pms:
            print("✗ 담당 PM으로 지정할 사용자가 없습니다 — 중단")
            return
        for i, (suf, name, ctype, region, ceo, contact, phone, email, cstat, ryn, assets) in enumerate(SAMPLES):
            cid = "sample-cl-{0}".format(suf)
            lat, lng = REGION_COORDS.get(region, (37.5, 127.0))
            client = db.get(Client, cid)
            if client is None:
                db.add(Client(  # noqa: E128 (아래 flush로 FK 확보)
                    client_id=cid, client_type=ctype, company_name=name,
                    biz_reg_no="200-{0:02d}-{1:05d}".format(i + 10, 30000 + i),
                    region=region, address="{0} 샘플로 {1}".format(region, i + 1),
                    ceo_name=ceo, ceo_contact_phone=phone,
                    main_contact_name=contact, main_contact_phone=phone,
                    main_contact_email=email, contract_status=cstat, report_yn=ryn,
                    manager_id=pms[i % len(pms)],
                    lat=lat + (i % 5) * 0.006, lng=lng + (i % 5) * 0.006,
                ))
                db.flush()  # 자산 FK(client_id) 확보 — PostgreSQL FK 즉시 검증 대응
                new_clients += 1

            for aidx, (asuf, grp, atype, spec, agency, site, auth, lid, secret) in enumerate(assets):
                aid = "sample-a-{0}-{1}".format(suf, asuf)
                if db.get(Asset, aid) is not None:
                    continue
                enc = crypto.encrypt(secret) if (enc_ok and secret) else None
                db.add(Asset(
                    asset_id=aid, client_id=cid, asset_group=grp, asset_type=atype,
                    quantity=1, main_spec=spec, telemetry_yn="Y",
                    location_info="{0} 현장".format(region), status="ACTIVE",
                    agency_name=agency, site_url=site, auth_type=auth,
                    login_id=lid if auth == "ID_PW" else None,
                    login_password=enc if auth == "ID_PW" else None,
                    api_token=enc if auth == "API_KEY" else None,
                    usage_purpose="운행/발전 데이터 수집",
                ))
                new_assets += 1
        db.commit()
        print("✓ 샘플 시드 완료 — 신규 고객사 {0} · 신규 자산(계정) {1}".format(new_clients, new_assets))
    finally:
        db.close()


if __name__ == "__main__":
    main()
