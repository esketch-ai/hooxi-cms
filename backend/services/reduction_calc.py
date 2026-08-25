"""감축량 산정 계산 엔진(D5) — 실무 엑셀 방법론을 CMS로 정립·검증.

강원/제주 산정 엑셀의 per-vehicle 공식을 그대로 재현(로컬 수치검증 완료):
  베이스라인 배출량(연차 n=0..9, tCO2/yr)
     = MIN(주행_base, 주행_사업) × (연료/km × 순발열량 × 배출계수 × 기술향상계수^(이용연수+n)) × 1e-6
       · 연료/km = 연평균연료 / 연평균주행(base)
  사업(전기) 배출량(연 고정, tCO2/yr) = ROUNDDOWN(
       MIN × 전력/km × 전력CO2 / 1e3
     + MIN × 전력/km × 전력CH4 × GWP_CH4 / 1e6
     + MIN × 전력/km × 전력N2O × GWP_N2O / 1e6, 3)
       · 전력/km = 연평균충전 / 연평균주행(사업)
  감축(연차) = MAX(0, 베이스라인 − 사업),  민간반영 = 감축 × 민간비율
방법론 상수는 tb_methodology_constant에서 주입(없으면 검증된 기본값). 엑셀 ROUNDDOWN=trunc.
"""

import math
from datetime import date
from typing import Dict, List, Optional

# 검증된 기본 상수(강원 산정 재현) — 마스터 미설정 시 폴백. 관리자는 마스터로 갱신 가능.
DEFAULT_CONSTANTS = {
    "CALORIFIC_CNG": 38.9,   # 순발열량(CNG)
    "CALORIFIC_OTHER": 35.2,  # 순발열량(경유 등)
    "EF_CNG": 56.1,           # 배출계수(CNG)
    "EF_OTHER": 73.2,         # 배출계수(경유 등)
    "TECH_IMPROVE": 0.99,     # 기술향상계수
    "ELEC_CO2": 0.4567,       # 전력 CO2 배출계수
    "ELEC_CH4": 0.0036,       # 전력 CH4 배출계수
    "ELEC_N2O": 0.0085,       # 전력 N2O 배출계수
    "GWP_CH4": 21.0,
    "GWP_N2O": 310.0,
    "BASE_YEAR": 2025.0,      # 이용연수 기준연도
    "CREDIT_YEARS": 10.0,     # 인증기간(년)
}


def load_constants(db=None) -> Dict[str, float]:
    """방법론 상수 — 마스터(key별 유효일자 ≤ 오늘 최신) 우선, 없으면 검증된 기본값."""
    consts = dict(DEFAULT_CONSTANTS)
    if db is None:
        return consts
    try:
        from models import MethodologyConstant
        rows = (
            db.query(MethodologyConstant)
            .filter(MethodologyConstant.effective_date <= date.today())
            .order_by(MethodologyConstant.key,
                      MethodologyConstant.effective_date.desc(),
                      MethodologyConstant.created_at.desc())
            .all()
        )
        seen = set()
        for r in rows:
            if r.key in seen:
                continue
            seen.add(r.key)
            consts[r.key] = float(r.value)
    except Exception:
        pass
    return consts


def _trunc3(v: float) -> float:
    return math.floor(v * 1000) / 1000  # 엑셀 ROUNDDOWN(,3)


def compute_vehicle(
    *,
    fuel: str,
    baseline_distance: float,   # 연평균 주행거리(베이스라인) I
    baseline_fuel: float,       # 연평균 연료사용량(베이스라인) J
    project_distance: float,    # 연평균 주행거리(사업/전기) AK
    project_kwh: float,         # 연평균 충전량(사업) AL
    ev_reg_year: int,           # 전기차 등록연도 → 이용연수
    private_ratio: Optional[float] = None,
    consts: Optional[Dict[str, float]] = None,
) -> dict:
    """차량 1대 산정 — 연차별 감축량·총감축·민간반영 반환(엑셀 재현)."""
    c = consts or DEFAULT_CONSTANTS
    is_cng = (fuel or "").upper() == "CNG"
    calorific = c["CALORIFIC_CNG"] if is_cng else c["CALORIFIC_OTHER"]
    ef = c["EF_CNG"] if is_cng else c["EF_OTHER"]
    tech = c["TECH_IMPROVE"]
    years = int(c["CREDIT_YEARS"])
    usage_year = int(c["BASE_YEAR"]) - int(ev_reg_year)

    fuel_per_km = baseline_fuel / baseline_distance if baseline_distance else 0.0
    min_dist = min(baseline_distance, project_distance)
    kwh_per_km = project_kwh / project_distance if project_distance else 0.0

    # 사업(전기) 배출량 — 연 고정
    project_emission = _trunc3(
        min_dist * kwh_per_km * c["ELEC_CO2"] / 1e3
        + min_dist * kwh_per_km * c["ELEC_CH4"] * c["GWP_CH4"] / 1e6
        + min_dist * kwh_per_km * c["ELEC_N2O"] * c["GWP_N2O"] / 1e6
    )

    annual = []
    for n in range(years):
        coeff = fuel_per_km * calorific * ef * (tech ** (usage_year + n))
        baseline_n = min_dist * coeff * 1e-6
        reduction_n = max(0.0, baseline_n - project_emission)
        annual.append({
            "year": n + 1,
            "baseline": round(baseline_n, 3),
            "project": project_emission,
            "reduction": round(reduction_n, 3),
        })
    total_reduction = round(sum(a["reduction"] for a in annual), 3)
    result = {
        "annual": annual,
        "project_emission": project_emission,
        "total_reduction": total_reduction,
        "usage_year": usage_year,
    }
    if private_ratio is not None:
        result["adjusted_total"] = round(total_reduction * private_ratio, 3)
        result["adjusted_annual"] = [round(a["reduction"] * private_ratio, 3) for a in annual]
    return result
