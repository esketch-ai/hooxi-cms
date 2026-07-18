"""엑셀 일괄 등록 규격(import_spec) 정합성 — 스키마 1:1 대조·코드 카테고리 실존·라벨 중복.

규격은 services/import_spec.py 단일 파일이 원천 — 여기서 대상 스키마·시드 코드와
어긋나면 양식/파싱/검증이 조용히 깨지므로 정적으로 대조한다.
"""

from pydantic_core import PydanticUndefined

import models
from services import import_spec

# 인증 비밀값 — 엑셀 컬럼으로 절대 유통 금지 (평문 차단, import_spec docstring)
_FORBIDDEN_FIELDS = {"auth_value", "login_password", "api_token", "pin_hash"}


def test_spec_fields_match_target_schema():
    """스펙 field는 대상 Pydantic 스키마의 실제 필드와 1:1 (오타·유령 필드 차단)."""
    for entity, spec in import_spec.IMPORT_SPECS.items():
        schema_fields = set(spec.schema_cls.model_fields.keys())
        spec_fields = [c.field for c in spec.columns]
        # 중복 필드 없음
        assert len(spec_fields) == len(set(spec_fields)), entity
        # 전 컬럼이 스키마 실필드
        unknown = set(spec_fields) - schema_fields
        assert not unknown, "{0}: 스키마에 없는 필드 {1}".format(entity, unknown)


def test_spec_required_covers_schema_required():
    """스키마에서 기본값 없는 필수 필드는 스펙에서도 필수 컬럼으로 노출."""
    for entity, spec in import_spec.IMPORT_SPECS.items():
        required_in_spec = {c.field for c in spec.columns if c.required}
        for name, info in spec.schema_cls.model_fields.items():
            if name in _FORBIDDEN_FIELDS or name == "subscription":
                continue
            schema_required = (
                info.default is PydanticUndefined and info.default_factory is None
            )
            if schema_required:
                assert name in required_in_spec, "{0}: 필수 필드 {1} 누락/비필수".format(
                    entity, name
                )


def test_no_credential_columns():
    """인증 비밀값 컬럼 금지 — 평문 비밀값의 엑셀 유통 원천 차단(R2-E6 취지)."""
    for entity, spec in import_spec.IMPORT_SPECS.items():
        fields = {c.field for c in spec.columns}
        assert not (fields & _FORBIDDEN_FIELDS), entity


def test_labels_unique_and_nonempty():
    """엑셀 헤더 라벨 중복/공백 금지 — 헤더 매칭 모호성 차단."""
    for entity, spec in import_spec.IMPORT_SPECS.items():
        labels = [c.label.strip() for c in spec.columns]
        assert all(labels), entity
        assert len(labels) == len(set(labels)), "{0}: 라벨 중복 {1}".format(entity, labels)


def test_code_categories_exist_in_seed(client):
    """code_category는 시드된 tb_code 카테고리에 실존 — 라벨↔코드 매핑 공급원 보장.

    client 픽스처(lifespan)가 seed_codes()를 실행한 뒤 DB를 직접 확인한다.
    """
    db = models.SessionLocal()
    try:
        seeded = {c for (c,) in db.query(models.Code.category).distinct().all()}
    finally:
        db.close()
    for entity, spec in import_spec.IMPORT_SPECS.items():
        for col in spec.columns:
            if col.code_category:
                assert col.code_category in seeded, "{0}: {1} 카테고리 미시드".format(
                    entity, col.code_category
                )


def test_fixed_values_map_to_schema_allowed():
    """고정값 매핑(인증 방식)은 대상 스키마 패턴이 허용하는 저장값만 가리킨다."""
    spec = import_spec.IMPORT_SPECS["assets"]
    auth_col = next(c for c in spec.columns if c.field == "auth_type")
    assert auth_col.fixed_values, "인증 방식은 고정값 매핑이어야 한다 (AUTH_TYPE 코드 미운영)"
    assert set(auth_col.fixed_values.values()) <= {"ID_PW", "API_KEY", "NONE"}
