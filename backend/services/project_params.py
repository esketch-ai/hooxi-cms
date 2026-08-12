"""감축 사업 파생값 기준값 리졸버 — tb_config project_base_params(JSON) 승격.

예상지급액·잔여차령·차령만료일 계산의 기준값(기준감축량·기준차령·만료개월·차량당
기본 최대지급액)을 공통 설정으로 관리한다. 설정 미저장 시 코드 기본값이 현행과 완전히
동일해 회귀가 없다(부록 L 정본 240/8/108). batch.py의 Config 조회·JSON 파싱·기본폴백
패턴을 재사용한다.
"""

import json

from sqlalchemy.orm import Session

from models import Config

CONFIG_KEY = "project_base_params"

# 코드 기본값 — 설정 미저장 시 현행과 비트 동일(회귀 0). 부록 L 정본.
DEFAULT_PROJECT_BASE_PARAMS = {
    "base_reduction": 240.0,          # 기준감축량 기본값
    "base_vehicle_age": 8.0,          # 기준차령 기본값
    "expire_months": 108,             # 차령만료 개월(EDATE 12*9)
    "default_max_payment": 2000000,   # 차량당 기본 최대지급액(UI 프리필용)
}


def base_params(db: Session) -> dict:
    """기준값 리졸버 — tb_config project_base_params(JSON) 우선, 없으면 코드 기본값 병합.

    부분 저장(일부 키만) 시 나머지는 기본값으로 폴백한다(dict merge). expire_months는
    int, 나머지는 float로 정규화한다(만료 계산이 정수 개월을 전제).
    """
    params = dict(DEFAULT_PROJECT_BASE_PARAMS)
    row = db.get(Config, CONFIG_KEY)
    if row and row.config_value:
        try:
            parsed = json.loads(row.config_value)
            if isinstance(parsed, dict):
                for k in DEFAULT_PROJECT_BASE_PARAMS:
                    v = parsed.get(k)
                    if v is None:
                        continue
                    params[k] = int(v) if k == "expire_months" else float(v)
        except (ValueError, TypeError):
            pass  # 파싱 실패 시 코드 기본값 유지(현행 동일)
    return params
