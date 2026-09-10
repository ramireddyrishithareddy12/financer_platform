"""
Automated Financial Unit Tests for Loan Calculation Engine
Verifies reducing balance EMI, flat rate, simple interest, banker's rounding,
tenure math, and waterfall allocation.
"""

import unittest
from decimal import Decimal
import datetime
import sys
import os

# Add parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.loan_engine import LoanEngine, round_money, round_internal

class TestLoanEngine(unittest.TestCase):

    def test_bankers_rounding(self):
        """Verifies half-even banker's rounding."""
        self.assertEqual(round_money(Decimal('10.125')), Decimal('10.12')) # 2 is even
        self.assertEqual(round_money(Decimal('10.135')), Decimal('10.14')) # 4 is even
        self.assertEqual(round_money(Decimal('100.0000')), Decimal('100.00'))

    def test_reducing_balance_amortization(self):
        """Verifies reducing balance EMI schedule generation."""
        sched = LoanEngine.generate_schedule(
            principal=100000,
            annual_rate=12,
            interest_type='REDUCING_BALANCE',
            frequency='MONTHLY',
            tenure_periods=12,
            start_date='2026-01-01'
        )

        self.assertEqual(sched['principal'], 100000.0)
        self.assertEqual(len(sched['installments']), 12)
        
        # Verify first installment principal + interest equals total due
        inst1 = sched['installments'][0]
        self.assertAlmostEqual(inst1['principal_due'] + inst1['interest_due'], inst1['total_due'], places=2)
        self.assertEqual(inst1['interest_due'], 1000.0) # 100,000 * (12%/12) = 1,000

        # Verify final installment remaining principal is zero
        last_inst = sched['installments'][-1]
        self.assertEqual(last_inst['remaining_principal'], 0.0)

    def test_flat_rate_calculation(self):
        """Verifies flat rate interest schedule."""
        sched = LoanEngine.generate_schedule(
            principal=50000,
            annual_rate=10,
            interest_type='FLAT_RATE',
            frequency='MONTHLY',
            tenure_periods=10,
            start_date='2026-01-01'
        )

        # 50,000 @ 10% for 10/12 years = 4,166.67 total interest
        self.assertEqual(len(sched['installments']), 10)
        tot_inst_principal = sum(i['principal_due'] for i in sched['installments'])
        self.assertAlmostEqual(tot_inst_principal, 50000.0, places=2)

    def test_simple_interest_calculation(self):
        """Verifies simple interest schedule."""
        sched = LoanEngine.generate_schedule(
            principal=20000,
            annual_rate=12,
            interest_type='SIMPLE_INTEREST',
            frequency='MONTHLY',
            tenure_periods=4,
            start_date='2026-01-01'
        )
        self.assertEqual(len(sched['installments']), 4)
        for inst in sched['installments']:
            self.assertEqual(inst['interest_due'], 200.0) # 20000 * (12%/12) = 200

    def test_waterfall_payment_allocation(self):
        """Verifies fee -> interest -> principal payment waterfall."""
        alloc = LoanEngine.allocate_payment(
            payment_amount=Decimal('5000'),
            interest_due=Decimal('1000'),
            principal_due=Decimal('3500'),
            fee_due=Decimal('200')
        )

        self.assertEqual(alloc['fee_paid'], Decimal('200.00'))
        self.assertEqual(alloc['interest_paid'], Decimal('1000.00'))
        self.assertEqual(alloc['principal_paid'], Decimal('3500.00'))
        self.assertEqual(alloc['excess_paid'], Decimal('300.00'))

    def test_rule_of_78s_calculation(self):
        """Verifies Rule of 78s sum-of-digits front-loaded interest schedule."""
        sched = LoanEngine.generate_schedule(
            principal=12000,
            annual_rate=12,
            interest_type='RULE_OF_78S',
            frequency='MONTHLY',
            tenure_periods=12,
            start_date='2026-01-01'
        )
        self.assertEqual(len(sched['installments']), 12)
        # First month interest should be higher than last month interest
        self.assertGreater(sched['installments'][0]['interest_due'], sched['installments'][-1]['interest_due'])
        last_inst = sched['installments'][-1]
        self.assertEqual(last_inst['remaining_principal'], 0.0)

    def test_compound_interest_calculation(self):
        """Verifies compound interest periodic compounding schedule."""
        sched = LoanEngine.generate_schedule(
            principal=50000,
            annual_rate=15,
            interest_type='COMPOUND_INTEREST',
            frequency='MONTHLY',
            tenure_periods=6,
            start_date='2026-01-01'
        )
        self.assertEqual(len(sched['installments']), 6)
        last_inst = sched['installments'][-1]
        self.assertEqual(last_inst['remaining_principal'], 0.0)

    def test_invalid_parameters_raise_error(self):
        """Verifies negative or zero principal raises ValueError."""
        with self.assertRaises(ValueError):
            LoanEngine.generate_schedule(-100, 12, 'REDUCING_BALANCE', 'MONTHLY', 12, '2026-01-01')

if __name__ == '__main__':
    unittest.main()
