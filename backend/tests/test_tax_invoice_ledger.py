"""세금계산서 원장(tb_tax_invoice) 모델 — round-trip + 승인번호 unique 멱등키.

공유 SQLite 누수 방지를 위해 TEST 접두 승인번호만 쓰고 끝에 정리한다.
"""

import pytest

import models


def _cleanup(db):
    db.query(models.TaxInvoice).filter(
        models.TaxInvoice.approval_no.like("TESTTI%")
    ).delete(synchronize_session=False)
    db.commit()


def test_tax_invoice_ledger_roundtrip_and_unique_approval_no(client):
    # client 픽스처로 앱 lifespan(create_all) 보장
    db = models.SessionLocal()
    try:
        _cleanup(db)
        inv = models.TaxInvoice(
            approval_no="TESTTI0001",
            direction="매입",
            invoicer_reg_no="1112223333",
            invoicee_reg_no="5298102298",
            invoicer_name="테스트공급자",
            invoicee_name="후시파트너스",
            counterpart_reg_no="1112223333",
            counterpart_name="테스트공급자",
            supply_amount=1000000,
            tax_amount=100000,
            total_amount=1100000,
            type_code="0101",
            purpose_code="02",
            source="HTML_IMPORT",
        )
        db.add(inv)
        db.commit()

        got = (
            db.query(models.TaxInvoice)
            .filter_by(approval_no="TESTTI0001")
            .first()
        )
        assert got is not None
        assert got.direction == "매입"
        assert float(got.supply_amount) == 1000000
        assert got.counterpart_reg_no == "1112223333"

        # 같은 승인번호 재적재 → unique 위반(멱등/중복방지)
        dup = models.TaxInvoice(approval_no="TESTTI0001", direction="매출")
        db.add(dup)
        with pytest.raises(Exception):
            db.commit()
        db.rollback()
    finally:
        _cleanup(db)
        db.close()
