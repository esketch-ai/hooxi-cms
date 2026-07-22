#!/usr/bin/env python3
"""P0 우선순위: 핵심 기능 종합 QAQC 테스트"""

import sys
from pathlib import Path

# 이 스크립트(backend/qaqc_p0_core.py)의 디렉토리를 import 경로에 추가 — 하드코딩 절대경로 제거
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient
from main import app
from models import SessionLocal, Base, User, Client, Project, ActivityHistory, ReportDelivery
from sqlalchemy import text

# 테스트용 DB 설정
import os
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/test_qaqc.db")
os.environ["ENABLE_DEV_LOGIN"] = "true"
os.environ["JWT_SECRET"] = "qaqc-test-secret-key-32-chars-minimum-length-for-jwt-signing"

from models import engine, get_db
import auth

# DB 초기화
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

client = TestClient(app)

def test_auth_dev_login():
    """[P0] 인증/인가: 개발자 로그인"""
    print("\n=== [P0] Auth Dev Login ===")
    resp = client.post("/api/v1/auth/dev-login", json={"email": "test@hooxi.com"})
    if resp.status_code == 200:
        token = resp.json()["access_token"]
        print("✅ 개발자 로그인 성공")
        return {"token": token}
    else:
        print(f"❌ 개발자 로그인 실패: {resp.text}")
        return None

def test_auth_email_login():
    """[P0] 인증/인가: 이메일 로그인"""
    print("\n=== [P0] Auth Email Login ===")
    resp = client.post("/api/v1/auth/email-login", json={"email": "admin@hooxipartners.com"})
    if resp.status_code == 200:
        token = resp.json()["access_token"]
        print("✅ 이메일 로그인 성공")
        return {"token": token}
    else:
        print(f"❌ 이메일 로그인 실패: {resp.text}")
        return None

def test_users_me(token):
    """[P0] 사용자 관리: 현재 사용자 조회"""
    print("\n=== [P0] Users Me ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/users/me", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 현재 사용자 조회 성공: {data['name']} ({data['email']})")
        return data["user_id"]
    else:
        print(f"❌ 현재 사용자 조회 실패: {resp.text}")
        return None

def test_clients_list(token, user_id):
    """[P0] 고객사 관리: 목록 조회"""
    print("\n=== [P0] Clients List ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/clients", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 고객사 목록 조회 성공 (총 {data['total']}개)")
        return user_id
    else:
        print(f"❌ 고객사 목록 조회 실패: {resp.text}")
        return None

def test_assets_list(token, user_id):
    """[P0] 자산 관리: 목록 조회"""
    print("\n=== [P0] Assets List ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/assets", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 자산 목록 조회 성공 (총 {data['total']}개)")
        return user_id
    else:
        print(f"❌ 자산 목록 조회 실패: {resp.text}")
        return None

def test_reports_list(token, user_id):
    """[P0] 보고서 관리: 목록 조회"""
    print("\n=== [P0] Reports List ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/reports", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 보고서 목록 조회 성공 (총 {data['total']}개)")
        return user_id
    else:
        print(f"❌ 보고서 목록 조회 실패: {resp.text}")
        return None

def test_histories_list(token, user_id):
    """[P0] 활동 이력 관리: 목록 조회"""
    print("\n=== [P0] Histories List ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/histories", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 활동 이력 목록 조회 성공 (총 {data['total']}개)")
        return user_id
    else:
        print(f"❌ 활동 이력 목록 조회 실패: {resp.text}")
        return None

def test_projects_list(token, user_id):
    """[P0] 프로젝트 관리: 목록 조회"""
    print("\n=== [P0] Projects List ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/projects", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 프로젝트 목록 조회 성공 (총 {data['total']}개)")
        return user_id
    else:
        print(f"❌ 프로젝트 목록 조회 실패: {resp.text}")
        return None

def test_schedules_list(token, user_id):
    """[P0] 일정 관리: 목록 조회"""
    print("\n=== [P0] Schedules List ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/schedules", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 일정 목록 조회 성공 (총 {data['total']}개)")
        return user_id
    else:
        print(f"❌ 일정 목록 조회 실패: {resp.text}")
        return None

def test_dashboard_stats(token, user_id):
    """[P0] 대시보드: 통계 정보"""
    print("\n=== [P0] Dashboard Stats ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/dashboard/stats", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 대시보드 통계 조회 성공")
        return user_id
    else:
        print(f"❌ 대시보드 통계 조회 실패: {resp.text}")
        return None

def test_audit_logs(token, user_id):
    """[P0] 감사 로그: 목록 조회"""
    print("\n=== [P0] Audit Logs ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/audit-logs", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 감사 로그 조회 성공 (총 {data['total']}개)")
        return user_id
    else:
        print(f"❌ 감사 로그 조회 실패: {resp.text}")
        return None

def test_settlements_list(token, user_id):
    """[P0] 정산 관리: 목록 조회"""
    print("\n=== [P0] Settlements List ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/settlements", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 정산 목록 조회 성공 (총 {data['total']}개)")
        return user_id
    else:
        print(f"❌ 정산 목록 조회 실패: {resp.text}")
        return None

def test_documents_list(token, user_id):
    """[P0] 문서 관리: 목록 조회"""
    print("\n=== [P0] Documents List ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/documents", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 문서 목록 조회 성공 (총 {data['total']}개)")
        return user_id
    else:
        print(f"❌ 문서 목록 조회 실패: {resp.text}")
        return None

def test_config_list(token, user_id):
    """[P0] 설정 관리: 목록 조회"""
    print("\n=== [P0] Config List ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/config", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 설정 목록 조회 성공 (총 {data['total']}개)")
        return user_id
    else:
        print(f"❌ 설정 목록 조회 실패: {resp.text}")
        return None

def test_backups_list(token, user_id):
    """[P0] 백업 관리: 목록 조회"""
    print("\n=== [P0] Backups List ===")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.get("/api/v1/backups", headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ 백업 목록 조회 성공 (총 {data['total']}개)")
        return user_id
    else:
        print(f"❌ 백업 목록 조회 실패: {resp.text}")
        return None

def main():
    """종합 QAQC 테스트 실행"""
    print("=" * 60)
    print("Hooxi-CMS P0 우선순위 종합 QAQC 테스트")
    print("=" * 60)
    
    # 인증/인가 테스트
    auth_token = test_auth_dev_login()
    if not auth_token:
        print("\n❌ 인증 실패로 나머지 테스트 중단")
        return False
    
    user_id = "u-admin"
    
    # 모든 P0 기능 테스트
    tests = [
        ("Users Me", lambda: test_users_me(auth_token, user_id)),
        ("Clients List", lambda: test_clients_list(auth_token, user_id)),
        ("Assets List", lambda: test_assets_list(auth_token, user_id)),
        ("Reports List", lambda: test_reports_list(auth_token, user_id)),
        ("Histories List", lambda: test_histories_list(auth_token, user_id)),
        ("Projects List", lambda: test_projects_list(auth_token, user_id)),
        ("Schedules List", lambda: test_schedules_list(auth_token, user_id)),
        ("Dashboard Stats", lambda: test_dashboard_stats(auth_token, user_id)),
        ("Audit Logs", lambda: test_audit_logs(auth_token, user_id)),
        ("Settlements List", lambda: test_settlements_list(auth_token, user_id)),
        ("Documents List", lambda: test_documents_list(auth_token, user_id)),
        ("Config List", lambda: test_config_list(auth_token, user_id)),
        ("Backups List", lambda: test_backups_list(auth_token, user_id)),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {name} 테스트 중 예외 발생: {e}")
            failed += 1
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("P0 종합 QAQC 테스트 결과")
    print("=" * 60)
    print(f"✅ 통과: {passed}개")
    print(f"❌ 실패: {failed}개")
    print(f"📊 전체 통과율: {(passed/(passed+failed))*100:.1f}%")
    
    if failed == 0:
        print("\n🎉 P0 우선순위 모든 테스트 통과!")
    else:
        print(f"\n⚠️ {failed}개 테스트가 실패했습니다.")
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
