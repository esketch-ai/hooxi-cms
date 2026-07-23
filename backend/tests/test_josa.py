"""한글 조사 자연화 헬퍼 — 받침 유무로 을/를·은/는 선택, 비한글은 폴백."""

from routers.common import josa


def test_josa_batchim():
    assert josa("자산", "을", "를") == "을"   # 산: 받침 ㄴ
    assert josa("사업", "을", "를") == "을"   # 업: 받침 ㅂ
    assert josa("자산", "은", "는") == "은"


def test_josa_no_batchim():
    assert josa("고객사", "을", "를") == "를"   # 사: 받침 없음
    assert josa("세그먼트", "을", "를") == "를"
    assert josa("보고서", "은", "는") == "는"


def test_josa_non_hangul_fallback():
    assert josa("ETAS", "을", "를") == "을(를)"
    assert josa("BMS", "은", "는") == "은(는)"
    assert josa("2024", "을", "를") == "을(를)"
