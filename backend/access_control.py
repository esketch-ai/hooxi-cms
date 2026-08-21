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
    {"name": "경영진", "dept_code": "EXEC", "is_default": False, "home_path": "/dashboard", "menus": [
        "/dashboard", "/observe", "/projects", "/finance-ledger", "/asset-report",
        "/asset-vehicles", "/settlements", "/reports", "/guide",
    ], "memo": "경영진 — 현황·재무·사업 중심(쓰기 권한은 직급으로)"},
    {"name": "경영전략실", "dept_code": "STRATEGY", "is_default": False, "home_path": "/observe", "menus": [
        "/observe", "/dashboard", "/finance-ledger", "/asset-report", "/asset-vehicles", "/guide",
    ], "memo": "경영전략실 — OBSERVER 화이트리스트와 동일 스코프(전환기 공존)"},
    {"name": "자산관리", "dept_code": "ASSET", "is_default": False, "home_path": "/assets", "menus": [
        "/dashboard", "/assets", "/accounts", "/asset-vehicles", "/asset-report",
        "/clients", "/documents", "/guide",
    ], "memo": "자산관리 부서 — 자산·연동·계정점검·자산보고"},
    {"name": "정산재무", "dept_code": "FINANCE", "is_default": False, "home_path": "/settlements", "menus": [
        "/dashboard", "/settlements", "/finance-ledger", "/tax-invoices",
        "/projects", "/buyers", "/documents", "/guide",
    ], "memo": "정산·재무 부서 — 정산·원장·세금계산서·매수자"},
    {"name": "사업운영", "dept_code": "BIZOPS", "is_default": False, "home_path": "/dashboard", "menus": [
        "/dashboard", "/issues", "/calendar", "/clients", "/histories", "/chat",
        "/reports", "/documents", "/projects", "/guide",
    ], "memo": "사업운영(고객·CRM) 부서 — 고객사·이력·상담·보고서"},
    {"name": "시스템관리", "dept_code": "SYSTEM", "is_default": False, "home_path": "/settings", "menus": [
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
    from models import AccessGroup, Code, GroupMenu, UserGroup

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

    # 부서명 라이브 해석 — dept_code가 있으면 공통코드(DEPT) 라벨을 표시명으로(부서명 변경은
    # 공통코드 관리 한 곳에서 끝나게). 코드가 없거나 미지정이면 저장된 name 사용.
    dept_codes = [g.dept_code for g in rows if getattr(g, "dept_code", None)]
    labels = {}
    if dept_codes:
        labels = {
            c.code: c.label
            for c in db.query(Code).filter(
                Code.category == "DEPT", Code.code.in_(dept_codes)
            ).all()
        }

    return {
        "groups": [
            {"group_id": g.group_id,
             "name": labels.get(getattr(g, "dept_code", None), g.name),
             "home_path": g.home_path, "implicit": implicit}
            for g in rows
        ],
        "allowed_menus": allowed,
        "home_path": home,
    }


# ── G2. 메뉴 → API 매핑(강제용) — (method|None, prefix). method=None이면 전 메서드.
#    한 화면이 읽는 보조 API까지 포함(모니터 모드 로그로 계속 보정). 정본은 이 표 1곳.
MENU_API_REGISTRY: Dict[str, List] = {
    "/dashboard": [(None, "/api/v1/dashboard"), (None, "/api/v1/projects/stage-delays"),
                   ("GET", "/api/v1/reports"), ("GET", "/api/v1/schedules")],
    "/observe": [(None, "/api/v1/dashboard"), (None, "/api/v1/projects/stage-delays"),
                 ("GET", "/api/v1/finance-ledger"), ("GET", "/api/v1/asset-vehicles"),
                 ("GET", "/api/v1/asset-report")],
    "/issues": [(None, "/api/v1/histories"), (None, "/api/v1/schedules")],
    "/calendar": [(None, "/api/v1/schedules")],
    "/clients": [(None, "/api/v1/clients"), (None, "/api/v1/imports"),
                 (None, "/api/v1/fleet"), (None, "/api/v1/fleet-status")],
    "/buyers": [(None, "/api/v1/buyers")],
    "/assets": [(None, "/api/v1/assets"), (None, "/api/v1/integrations")],
    "/accounts": [("GET", "/api/v1/assets"), (None, "/api/v1/batch/account-check")],
    "/histories": [(None, "/api/v1/histories"), ("GET", "/api/v1/clients")],
    "/chat": [(None, "/api/v1/chat")],
    "/reports": [(None, "/api/v1/reports"), (None, "/api/v1/segments")],
    "/documents": [(None, "/api/v1/documents"), ("GET", "/api/v1/clients")],
    "/projects": [(None, "/api/v1/projects"), ("GET", "/api/v1/market-rates")],
    "/tax-invoices": [(None, "/api/v1/tax-invoices")],
    "/asset-vehicles": [(None, "/api/v1/asset-vehicles"), ("GET", "/api/v1/market-rates")],
    "/finance-ledger": [(None, "/api/v1/finance-ledger"), ("GET", "/api/v1/market-rates")],
    "/asset-report": [(None, "/api/v1/asset-report")],
    "/settlements": [(None, "/api/v1/settlements")],
    "/portal-accounts": [(None, "/api/v1/external-accounts"),
                         ("GET", "/api/v1/buyers"), ("GET", "/api/v1/clients")],
    "/settings": [(None, "/api/v1/users"), (None, "/api/v1/config"),
                  (None, "/api/v1/backups"), (None, "/api/v1/audit-logs"),
                  (None, "/api/v1/access-groups")],  # 접근그룹 관리(실사용은 ADMIN 우회, 정합용)
    "/guide": [],  # 프론트 전용(API 없음)
}

# 어느 메뉴에도 속하지 않는 공통 API — 항상 허용(인증·내 정보·코드·담당자 옵션·헬스)
GLOBAL_ALLOW: List = [
    (None, "/api/v1/auth"),
    (None, "/api/v1/users/me"),
    ("GET", "/api/v1/users"),   # 담당자 필터 옵션(전 화면) — 변경류는 /settings 메뉴 + ADMIN role
    ("GET", "/api/v1/clients/options"),  # 고객사 옵션(전 화면 드롭다운·이름 맵) — 경량 전건
    (None, "/api/v1/codes"),
    (None, "/api/v1/health"),
]


def _rule_hit(method: str, path: str, rules) -> bool:
    for m, prefix in rules:
        if m is not None and m != method:
            continue
        if path == prefix or path.startswith(prefix + "/") or (
            path.startswith(prefix) and prefix.endswith("/")
        ):
            return True
        # 쿼리스트링 없는 startswith 보조(예: /api/v1/users?status=…는 path에 쿼리 미포함)
        if path.startswith(prefix) and (len(path) == len(prefix) or path[len(prefix)] in "/?"):
            return True
    return False


def is_path_allowed(method: str, path: str, allowed_menus) -> bool:
    """요청(method, path)이 허용 메뉴들의 API 집합(+공통 허용)에 속하는가."""
    if _rule_hit(method, path, GLOBAL_ALLOW):
        return True
    for menu in allowed_menus:
        if _rule_hit(method, path, MENU_API_REGISTRY.get(menu, [])):
            return True
    return False


def get_access_mode(db) -> str:
    """tb_config access_control_mode — off(기본)/monitor/enforce."""
    from models import Config

    row = db.get(Config, ACCESS_CONTROL_MODE_KEY)
    if row is None:
        return "off"
    val = (row.config_value or "").strip().strip('"').lower()
    return val if val in ACCESS_CONTROL_MODES else "off"


# monitor 모드 감사로그 스로틀 — (user_id, path) 프로세스당 1회만 기록(로그 폭주 방지)
_monitor_seen: set = set()
_MONITOR_SEEN_MAX = 5000


def check_request_access(db, user, method: str, path: str) -> None:
    """G2 그룹 접근 강제 — get_current_user에서 호출.

    off: 아무것도 안 함 / monitor: 위반이어도 통과+감사로그 / enforce: 403.
    ADMIN·OBSERVER 제외(ADMIN=전역 우회, OBSERVER=기존 화이트리스트 별도 유지).
    외부역할은 이 함수에 오기 전에 차단된다(격리 불변).
    """
    if user.role in ("ADMIN", "OBSERVER"):
        return
    mode = get_access_mode(db)
    if mode == "off":
        return
    allowed = resolve_user_access(db, user)["allowed_menus"]
    if is_path_allowed(method, path, allowed):
        return
    if mode == "enforce":
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="접근 권한이 없는 메뉴의 기능입니다")
    # monitor — 차단 없이 감사로그(경로만, R2-E6)
    key = (user.user_id, method, path)
    if key in _monitor_seen or len(_monitor_seen) >= _MONITOR_SEEN_MAX:
        return
    _monitor_seen.add(key)
    try:
        from services.audit_logger import AuditLogger

        AuditLogger.log_action(
            db, user.user_id, "ACCESS_DENY_WOULD", target_type="ACCESS_CONTROL",
            new_value="{0} {1}".format(method, path),
        )
        db.commit()
    except Exception:
        db.rollback()  # 로그 실패가 요청을 막으면 안 됨
