import re

from nm4_sql import SQLService


class _DummySchemaService:
    schema_index = {"sales": set(), "salepayments": set(), "saleitems": set(), "products": set()}


class _DummyResponse:
    def __init__(self, content: str):
        self.choices = [type("Choice", (), {"message": type("Msg", (), {"content": content})()})()]


def _dummy_call_openai_with_retry(**kwargs):
    return _DummyResponse("SELECT 1")


def _schema_profile_getter():
    return {
        "dbo.Sales": {
            "columns": {
                "DueAmount": {"data_type": "decimal"},
                "RegistrationNo": {"data_type": "nvarchar"},
                "Id": {"data_type": "uniqueidentifier"},
            }
        },
        "dbo.SalePayments": {
            "columns": {
                "Received": {"data_type": "decimal"},
                "DueAmount": {"data_type": "decimal"},
                "PaymentType": {"data_type": "int"},
                "SaleId": {"data_type": "uniqueidentifier"},
                "Amount": {"data_type": "decimal"},
            }
        },
        "dbo.SaleItems": {
            "columns": {
                "SaleId": {"data_type": "uniqueidentifier"},
                "ProductId": {"data_type": "uniqueidentifier"},
                "Quantity": {"data_type": "decimal"},
                "UnitPrice": {"data_type": "decimal"},
                "TotalAmount": {"data_type": "decimal"},
            }
        },
        "dbo.Products": {
            "columns": {
                "Id": {"data_type": "uniqueidentifier"},
                "code": {"data_type": "nvarchar"},
                "EnglishName": {"data_type": "nvarchar"},
                "ArabicName": {"data_type": "nvarchar"},
            }
        },
    }


def _build_service():
    return SQLService(
        call_openai_with_retry=_dummy_call_openai_with_retry,
        schema_service=_DummySchemaService(),
        schema_profile_getter=_schema_profile_getter,
    )


def test_alias_amount_rewrite_is_scoped():
    service = _build_service()
    sql = (
        "SELECT sp.Amount, si.TotalAmount FROM dbo.Sales s "
        "JOIN dbo.SalePayments sp ON s.Id=sp.SaleId "
        "JOIN dbo.SaleItems si ON si.SaleId=s.Id"
    )
    fixed = service._apply_post_generation_fixes(sql, "show total revenue")

    assert "sp.Received" in fixed
    assert "si.TotalAmount" in fixed
    assert "si.Received" not in fixed


def test_sales_dueamount_not_forced_to_salepayments():
    service = _build_service()
    sql = "SELECT s.DueAmount FROM dbo.Sales s"
    fixed = service._apply_post_generation_fixes(sql, "show due amount")
    assert "s.DueAmount" in fixed


def test_sum_wrapped_with_coalesce_for_revenue_questions():
    service = _build_service()
    sql = "SELECT SUM(si.TotalAmount) AS Revenue FROM dbo.SaleItems si"
    fixed = service._apply_post_generation_fixes(sql, "top selling product revenue")
    assert re.search(r"COALESCE\(SUM\(si\.TotalAmount\),\s*0\)", fixed, re.IGNORECASE)


def test_saleitems_products_join_rewrites_code_to_id():
    service = _build_service()
    sql = (
        "SELECT TOP 10 p.code, SUM(si.Quantity) AS Qty "
        "FROM dbo.SaleItems si "
        "JOIN dbo.Products p ON si.ProductId = p.code "
        "GROUP BY p.code"
    )

    fixed = service._apply_post_generation_fixes(sql, "top products")
    assert "si.ProductId = p.Id" in fixed


def test_incompatible_join_key_types_raise_validation_error():
    service = _build_service()
    sql = (
        "SELECT TOP 10 p.code, SUM(si.Quantity) AS Qty "
        "FROM dbo.SaleItems si "
        "JOIN dbo.Products p ON si.ProductId = p.code "
        "GROUP BY p.code"
    )

    try:
        service._validate_join_key_compatibility(sql)
        assert False, "Expected incompatibile join key type validation to fail"
    except ValueError as exc:
        assert "Incompatible JOIN key types detected" in str(exc)


def test_bracketed_saleitems_products_join_is_repaired():
    service = _build_service()
    sql = (
        "SELECT TOP 10 p.code, SUM(si.Quantity) AS Qty "
        "FROM [dbo].[SaleItems] si "
        "JOIN [dbo].[Products] p ON si.ProductId = p.code "
        "GROUP BY p.code"
    )

    fixed = service._fix_known_incompatible_joins(sql)
    assert "si.ProductId = p.Id" in fixed


if __name__ == "__main__":
    test_alias_amount_rewrite_is_scoped()
    test_sales_dueamount_not_forced_to_salepayments()
    test_sum_wrapped_with_coalesce_for_revenue_questions()
    test_saleitems_products_join_rewrites_code_to_id()
    test_incompatible_join_key_types_raise_validation_error()
    test_bracketed_saleitems_products_join_is_repaired()
    print("All SQL guardrail tests passed.")
