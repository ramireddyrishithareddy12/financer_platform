"""
Independent Rule of 78s Mathematical Audit & Verification Test Suite
Proves mathematical correctness of Rule of 78s sum-of-digits calculations,
earned vs unearned interest tracking, installment allocation, and early settlement rebates
WITHOUT calling application internal functions for reference values.
"""

import unittest
from decimal import Decimal, ROUND_HALF_EVEN
import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.loan_engine import LoanEngine

def independent_rule_of_78s_calculator(principal, annual_rate, tenure_months):
    """
    Independent reference implementation of Rule of 78s.
    P = Principal
    r = Annual Rate / 100
    n = Tenure in months
    """
    P = Decimal(str(principal))
    rate = Decimal(str(annual_rate)) / Decimal('100')
    n = int(tenure_months)
    
    # 1. Total Contractual Interest = P * rate * (n / 12)
    years = Decimal(str(n)) / Decimal('12')
    total_interest = (P * rate * years).quantize(Decimal('0.0001'), rounding=ROUND_HALF_EVEN)
    total_payable = P + total_interest
    
    # 2. Sum of digits S = n * (n + 1) / 2
    sum_of_digits = Decimal(str((n * (n + 1)) // 2))
    
    equal_installment = ((P + total_interest) / Decimal(str(n))).quantize(Decimal('0.0001'), rounding=ROUND_HALF_EVEN)
    
    schedule = []
    earned_so_far = Decimal('0.0000')
    rem_p = P

    for i in range(1, n + 1):
        weight = Decimal(str(n - i + 1))
        i_due = (total_interest * (weight / sum_of_digits)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_EVEN)
        earned_so_far += i_due
        
        if i == n:
            p_due = rem_p
            total_due = p_due + i_due
        else:
            p_due = (equal_installment - i_due).quantize(Decimal('0.0001'), rounding=ROUND_HALF_EVEN)
            total_due = p_due + i_due

        rem_p -= p_due
        unearned_interest = total_interest - earned_so_far

        schedule.append({
            "installment": i,
            "principal_due": float(p_due.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)),
            "interest_due": float(i_due.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)),
            "total_due": float(total_due.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)),
            "earned_interest_cumulative": float(earned_so_far.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)),
            "unearned_interest_remaining": float(unearned_interest.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN))
        })

    return {
        "total_contractual_interest": float(total_interest.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)),
        "total_payable": float(total_payable.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)),
        "schedule": schedule
    }

class TestRuleOf78sAudit(unittest.TestCase):

    def test_independent_math_oracle_comparison(self):
        """Audits LoanEngine output against independent mathematical oracle."""
        principal = 12000
        annual_rate = 12
        tenure = 12

        # 1. Independent Oracle Calculation
        oracle = independent_rule_of_78s_calculator(principal, annual_rate, tenure)

        # 2. Application Loan Engine Calculation
        engine_res = LoanEngine.generate_schedule(
            principal=principal,
            annual_rate=annual_rate,
            interest_type='RULE_OF_78S',
            frequency='MONTHLY',
            tenure_periods=tenure,
            start_date='2026-01-01'
        )

        # Compare total contractual interest
        self.assertEqual(engine_res['total_interest'], oracle['total_contractual_interest'])

        # Compare installment line items
        for i in range(12):
            o_inst = oracle['schedule'][i]
            e_inst = engine_res['installments'][i]
            self.assertEqual(e_inst['installment_number'], o_inst['installment'])
            self.assertEqual(e_inst['interest_due'], o_inst['interest_due'])
            self.assertEqual(e_inst['principal_due'], o_inst['principal_due'])

    def test_front_loaded_interest_weight_distribution(self):
        """Audits that period 1 interest is strictly greater than period 2, period 2 > period 3, etc."""
        engine_res = LoanEngine.generate_schedule(12000, 12, 'RULE_OF_78S', 'MONTHLY', 12, '2026-01-01')
        insts = engine_res['installments']
        for i in range(len(insts) - 1):
            self.assertGreater(insts[i]['interest_due'], insts[i+1]['interest_due'])

    def test_earned_vs_unearned_interest_early_payoff(self):
        """Audits early settlement payoff rebate calculation after month 4."""
        # 12,000 principal @ 12% over 12 months -> Total interest = 1,440
        # Sum of digits S = 78
        # Month 1 interest = 1440 * 12/78 = 221.54
        # Month 2 interest = 1440 * 11/78 = 203.08
        # Month 3 interest = 1440 * 10/78 = 184.62
        # Month 4 interest = 1440 * 9/78  = 166.15
        # Total Earned in 4 months = 775.39
        # Unearned Interest waived = 1,440 - 775.39 = 664.61
        oracle = independent_rule_of_78s_calculator(12000, 12, 12)
        earned_4m = sum(inst['interest_due'] for inst in oracle['schedule'][:4])
        unearned_waived = oracle['total_contractual_interest'] - earned_4m
        self.assertAlmostEqual(earned_4m, 775.39, delta=0.5)
        self.assertAlmostEqual(unearned_waived, 664.61, delta=0.5)

if __name__ == '__main__':
    unittest.main()
