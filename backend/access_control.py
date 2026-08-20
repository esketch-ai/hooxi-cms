"""내부 그룹(부서·경영진) 메뉴 접근제어 — 단일 원천 상수 (ACCESS_CONTROL_PLAN.md G1~G2).

두 축 분리 원칙: role(직급)=행위 권한(auth.PERMISSION_MATRIX, 불변), group(부서)=메뉴 접근.
메뉴 키는 프론트 nav.ts의 경로와 1:1 — 여기 목록이 백엔드 유효성·매핑의 정본이다.
외부역할(PARTNER/INVESTOR)·OBSERVER 격리 상수(auth.py)에는 관여하지 않는다.
"""

from typing import Dict, List

# ── 메뉴 키 정본 — frontend/src/layouts/AppShell/nav.ts 경로와 일치 ──
MENU_KEYS: List[str] = [
    "/dashboard",        # 통합 현황판
    "/observe",          # 경영 관찰(읽기 전용)
    "/issues",           # 이슈 보드
    "/calendar",         # 일정 캘린더
    "/clients",          # 고객사 마스터
    "/buyers",           # 매수자 마스터
    "/assets",           # 자산·연동 마스터
    "/accounts",         # 계정 점검
    "/histories",        # 영업 활동 이력
    "/chat",             # 카카오톡 상담 관제
    "/reports",          # 월간 보고서 발송 관리
    "/documents",        # 문서 아카이브
    "/projects",         # 감축 사업 관리
    "/tax-invoices",     # 세금계산서 원장
    "/asset-vehicles",   # 전기버스 자산
    "/finance-ledger",   # 재무 원장
    "/asset-report",     # 자산관리 보고
    "/settlements",      # 정산 관리
    "/portal-accounts",  # 외부 포털 계정
    "/settings",         # 환경 설정
    "/guide",            # 사용자 가이드
]

# tb_config 스위치 — off(기본): 강제 없음 / monitor: 감사로그만 / enforce: 403 차단 (G2)
ACCESS_CONTROL_MODE_KEY = "access_control_mode"
ACCESS_CONTROL_MODES = ("off", "monitor", "enforce")

# ── 초기 그룹 시드(Q1 확정 7종) — tb_access_group이 비어있을 때 1회만 생성.
#    이후 구성 변경은 관리 UI(G3)에서 — 시드는 절대 덮어쓰지 않는다.
#    '전사'는 기본그룹(is_default): 그룹 미배정 사용자의 암묵 소속(fail-safe·회귀 0).
SEED_GROUPS: List[Dict] = [
    {"name": "전사", "is_default": True, "home_path": "/dashboard", "menus": list(MENU_KEYS),
     "memo": "기본 그룹 — 그룹 미배정 사용자는 자동으로 이 그룹 권한(전 메뉴)"},
    {"name": "경영진", "is_default": False, "home_path": "/dashboard", "menus": [
        "/dashboard", "/observe", "/projects", "/finance-ledger", "/asset-report",
        "/asset-vehicles", "/settlements", "/reports", "/guide",
    ], "memo": "경영진 — 현황·재무·사업 중심(쓰기 권한은 직급으로)"},
    {"name": "경영전략실", "is_default": False, "home_path": "/observe", "menus": [
        "/observe", "/dashboard", "/finance-ledger", "/asset-report", "/asset-vehicles", "/guide",
    ], "memo": "경영전략실 — OBSERVER 화이트리스트와 동일 스코프(전환기 공존)"},
    {"name": "자산관리", "is_default": False, "home_path": "/assets", "menus": [
        "/dashboard", "/assets", "/accounts", "/asset-vehicles", "/asset-report",
        "/clients", "/documents", "/guide",
    ], "memo": "자산관리 부서 — 자산·연동·계정점검·자산보고"},
    {"name": "정산재무", "is_default": False, "home_path": "/settlements", "menus": [
        "/dashboard", "/settlements", "/finance-ledger", "/tax-invoices",
        "/projects", "/buyers", "/documents", "/guide",
    ], "memo": "정산·재무 부서 — 정산·원장·세금계산서·매수자"},
    {"name": "사업운영", "is_default": False, "home_path": "/dashboard", "menus": [
        "/dashboard", "/issues", "/calendar", "/clients", "/histories", "/chat",
        "/reports", "/documents", "/projects", "/guide",
    ], "memo": "사업운영(고객·CRM) 부서 — 고객사·이력·상담·보고서"},
    {"name": "시스템관리", "is_default": False, "home_path": "/settings", "menus": [
        "/dashboard", "/settings", "/portal-accounts", "/accounts", "/guide",
    ], "memo": "시스템 관리 — 설정·외부계정·계정점검"},
]


def valid_menu_keys(keys) -> List[str]:
    """menu_key 목록 검증 — 정본에 없는 키는 걸러낸다(오타·구버전 방어)."""
    allow = set(MENU_KEYS)
    return [k for k in keys if k in allow]


def resolve_user_access(db, user) -> dict:
    """내부 사용자의 그룹·허용 메뉴 합집합·로그인 홈 계산 (G1 — /users/me 용).

    - 명시 배정(tb_user_group)이 없으면 기본(전사) 그룹을 암묵 소속(implicit)으로 취급.
    - allowed_menus = 소속 그룹 허용 메뉴의 합집합. ADMIN은 전체(락아웃 방지 우회).
    - home_path = 명시 그룹이 1개면 그 그룹 홈, 여럿이면 /dashboard(중립), 암묵이면 기본그룹 홈.
    """
    from models import AccessGroup, GroupMenu, UserGroup

    rows = (
        db.query(AccessGroup)
        .join(UserGroup, UserGroup.group_id == AccessGroup.group_id)
        .filter(UserGroup.user_id == user.user_id)
        .order_by(AccessGroup.name)
        .all()
    )
    implicit = False
    if not rows:
        default = db.query(AccessGroup).filter(AccessGroup.is_default.is_(True)).first()
        rows = [default] if default is not None else []
        implicit = True

    group_ids = [g.group_id for g in rows]
    if user.role == "ADMIN":
        allowed = list(MENU_KEYS)
    elif group_ids:
        keys = {
            k[0]
            for k in db.query(GroupMenu.menu_key)
            .filter(GroupMenu.group_id.in_(group_ids))
            .distinct()
            .all()
        }
        allowed = [k for k in MENU_KEYS if k in keys]  # 정본(nav) 순서 유지
    else:
        # 그룹도 기본그룹도 없음(시드 전 DB) — 전체 허용(fail-safe: 잠금보다 개방)
        allowed = list(MENU_KEYS)

    if implicit:
        home = rows[0].home_path if rows and rows[0].home_path else "/dashboard"
    elif len(rows) == 1:
        home = rows[0].home_path or "/dashboard"
    else:
        home = "/dashboard"

    return {
        "groups": [
            {"group_id": g.group_id, "name": g.name, "home_path": g.home_path,
             "implicit": implicit}
            for g in rows
        ],
        "allowed_menus": allowed,
        "home_path": home,
    }
