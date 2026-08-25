"""감축량 산정 엔진(D5) — 실무 엑셀(강원 CNG 차량) 수치 재현 회귀 검증."""

from services import reduction_calc as rc


def test_reproduces_gangwon_cng_vehicle():
    # 강원 산정 3행 실제 입력(로컬 검증 완료). 엑셀 결과: 1년차 base 98.010, 10년차 89.534, 사업 38.423.
    res = rc.compute_vehicle(
        fuel="CNG",
        baseline_distance=73218.33636363636,
        baseline_fuel=48344.80124954544,
        project_distance=69399.53571428571,
        project_kwh=83636.09999999999,
        ev_reg_year=2023,
        private_ratio=0.4,
    )
    assert res["usage_year"] == 2  # 2025 - 2023
    assert abs(res["project_emission"] - 38.423) < 1e-3
    assert abs(res["annual"][0]["baseline"] - 98.010) < 0.01   # 1년차
    assert abs(res["annual"][9]["baseline"] - 89.534) < 0.01   # 10년차
    # 감축 = base - project, 민간반영 = ×0.4
    y1 = res["annual"][0]
    assert abs(y1["reduction"] - (y1["baseline"] - 38.423)) < 1e-3
    assert abs(res["adjusted_total"] - res["total_reduction"] * 0.4) < 1e-3


def test_diesel_constants_differ():
    d = rc.compute_vehicle(fuel="경유", baseline_distance=50000, baseline_fuel=20000,
                           project_distance=48000, project_kwh=60000, ev_reg_year=2024)
    c = rc.compute_vehicle(fuel="CNG", baseline_distance=50000, baseline_fuel=20000,
                           project_distance=48000, project_kwh=60000, ev_reg_year=2024)
    # 경유(35.2·73.2) vs CNG(38.9·56.1) → 서로 다른 베이스라인
    assert d["annual"][0]["baseline"] != c["annual"][0]["baseline"]


def test_reduction_never_negative():
    r = rc.compute_vehicle(fuel="경유", baseline_distance=1000, baseline_fuel=1,
                           project_distance=99999, project_kwh=999999, ev_reg_year=2024)
    assert all(a["reduction"] >= 0 for a in r["annual"])
