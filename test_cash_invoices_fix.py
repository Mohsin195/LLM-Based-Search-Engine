#!/usr/bin/env python3
"""
Test script to demonstrate the cash invoices query fix.

This script tests the improved SQL generation for payment-related queries,
particularly focusing on preventing cross-table column mistakes.
"""

import sys
sys.path.append('.')

def test_cash_invoices_query():
    """Simulate the user's "cash invoices" query and verify fixes."""
    from new_main_3 import _validate_column_table_pairs
    
    # This is the kind of SQL the LLM might generate without fixes:
    # Using Sales.Received which doesn't exist
    problematic_sql = """
    SELECT 
        s.RegistrationNo,
        s.DocumentName,
        sp.PaymentType,
        s.Received,  -- WRONG: Received is only in SalePayments
        SUM(sp.Received) as PaymentAmount
    FROM dbo.Sales s
    JOIN dbo.SalePayments sp ON s.Id = sp.SaleId
    WHERE sp.PaymentType = 6
    GROUP BY s.RegistrationNo, s.DocumentName, sp.PaymentType, s.Received
    """
    
    print("=" * 80)
    print("CASH INVOICES QUERY TEST")
    print("=" * 80)
    
    print("\n1. Testing PROBLEMATIC SQL (uses Sales.Received):")
    print("-" * 80)
    try:
        _validate_column_table_pairs(problematic_sql)
        print("ERROR: Validation should have failed but passed!")
        return False
    except ValueError as e:
        print(f"✓ Validation correctly caught the error:")
        error_msg = str(e).split('\n')[0]
        print(f"  {error_msg}")
    
    # This is the correct SQL after applying the fixes:
    correct_sql = """
    SELECT 
        s.RegistrationNo,
        s.DocumentName,
        sp.PaymentType,
        sp.Received,  -- CORRECT: Received from SalePayments
        SUM(sp.Received) as PaymentAmount
    FROM dbo.Sales s
    JOIN dbo.SalePayments sp ON s.Id = sp.SaleId
    WHERE sp.PaymentType = 6
    GROUP BY s.RegistrationNo, s.DocumentName, sp.PaymentType, sp.Received
    """
    
    print("\n2. Testing CORRECTED SQL (uses SalePayments.Received):")
    print("-" * 80)
    try:
        _validate_column_table_pairs(correct_sql)
        print("✓ Validation passed - SQL is correct!")
        return True
    except ValueError as e:
        print(f"ERROR: Validation failed unexpectedly:")
        print(f"  {str(e)[:100]}")
        return False

if __name__ == "__main__":
    success = test_cash_invoices_query()
    print("\n" + "=" * 80)
    if success:
        print("SUCCESS: Cash invoices query fix is working correctly!")
        sys.exit(0)
    else:
        print("FAILURE: There are still issues to address")
        sys.exit(1)
