"""
Modular Loan Calculation Engine
Provides precise financial decimal math for loan amortization schedules, 
flat rate interest, simple interest, and repayment allocation.
"""

from decimal import Decimal, ROUND_HALF_EVEN
import datetime
from typing import List, Dict, Any

# Standard precision setup: internal math to 4 decimal places, display rounded to 2 places
PRECISION = Decimal('0.0001')
CURRENCY_ROUND = Decimal('0.01')

def round_money(val: Decimal) -> Decimal:
    """Round to 2 decimal places using Banker's rounding (ROUND_HALF_EVEN)."""
    if not isinstance(val, Decimal):
        val = Decimal(str(val))
    return val.quantize(CURRENCY_ROUND, rounding=ROUND_HALF_EVEN)

def round_internal(val: Decimal) -> Decimal:
    """Round internally to 4 decimal places."""
    if not isinstance(val, Decimal):
        val = Decimal(str(val))
    return val.quantize(PRECISION, rounding=ROUND_HALF_EVEN)

def get_frequency_periods_per_year(frequency: str) -> int:
    freq_map = {
        'MONTHLY': 12,
        'WEEKLY': 52,
        'DAILY': 365
    }
    return freq_map.get(frequency.upper(), 12)

def add_frequency_period(start_date: datetime.date, period_index: int, frequency: str) -> datetime.date:
    """Calculates the due date for period_index (1-indexed)."""
    freq = frequency.upper()
    if freq == 'MONTHLY':
        # Add period_index months
        month = start_date.month - 1 + period_index
        year = start_date.year + month // 12
        month = month % 12 + 1
        day = min(start_date.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        return datetime.date(year, month, day)
    elif freq == 'WEEKLY':
        return start_date + datetime.timedelta(weeks=period_index)
    elif freq == 'DAILY':
        return start_date + datetime.timedelta(days=period_index)
    else:
        return start_date + datetime.timedelta(days=30 * period_index)

class LoanEngine:
    @staticmethod
    def generate_schedule(
        principal: float | Decimal,
        annual_rate: float | Decimal,
        interest_type: str,
        frequency: str,
        tenure_periods: int,
        start_date: str | datetime.date
    ) -> Dict[str, Any]:
        """
        Generates deterministic repayment schedule.
        Returns a dict with overall loan summary and list of installment details.
        """
        P = Decimal(str(principal))
        rate_annual = Decimal(str(annual_rate)) / Decimal('100')
        periods_per_year = Decimal(str(get_frequency_periods_per_year(frequency)))
        n = int(tenure_periods)
        
        if isinstance(start_date, str):
            start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        else:
            start_dt = start_date

        if P <= Decimal('0') or n <= 0 or rate_annual < Decimal('0'):
            raise ValueError("Invalid loan parameters: Principal and tenure must be positive.")

        interest_type = interest_type.upper()
        installments: List[Dict[str, Any]] = []
        total_interest = Decimal('0.0000')

        if interest_type == 'REDUCING_BALANCE':
            # Equated Monthly / Periodic Installment formula
            # r = annual_rate / periods_per_year
            r = rate_annual / periods_per_year
            
            if r == Decimal('0'):
                emi = P / Decimal(str(n))
            else:
                # EMI = P * [r * (1+r)^n] / [(1+r)^n - 1]
                one_plus_r = Decimal('1') + r
                factor = one_plus_r ** n
                emi = P * (r * factor) / (factor - Decimal('1'))
            
            emi = round_internal(emi)
            remaining_balance = P

            for i in range(1, n + 1):
                due_date = add_frequency_period(start_dt, i, frequency)
                interest_for_period = round_internal(remaining_balance * r)
                
                if i == n:
                    # Final period adjustment to ensure principal exact zero
                    principal_for_period = remaining_balance
                    total_due_for_period = principal_for_period + interest_for_period
                else:
                    principal_for_period = emi - interest_for_period
                    total_due_for_period = emi

                remaining_balance = round_internal(remaining_balance - principal_for_period)
                total_interest += interest_for_period

                installments.append({
                    "installment_number": i,
                    "due_date": due_date.isoformat(),
                    "principal_due": float(round_money(principal_for_period)),
                    "interest_due": float(round_money(interest_for_period)),
                    "total_due": float(round_money(total_due_for_period)),
                    "remaining_principal": float(round_money(max(Decimal('0'), remaining_balance)))
                })

        elif interest_type == 'FLAT_RATE':
            # Flat interest = Principal * (annual_rate) * (n / periods_per_year)
            years = Decimal(str(n)) / periods_per_year
            total_interest = round_internal(P * rate_annual * years)
            total_payable = P + total_interest
            
            principal_per_period = round_internal(P / Decimal(str(n)))
            interest_per_period = round_internal(total_interest / Decimal(str(n)))
            
            remaining_balance = P

            for i in range(1, n + 1):
                due_date = add_frequency_period(start_dt, i, frequency)
                
                if i == n:
                    p_due = remaining_balance
                    i_due = total_interest - sum(Decimal(str(item['interest_due'])) for item in installments)
                else:
                    p_due = principal_per_period
                    i_due = interest_per_period

                remaining_balance = round_internal(remaining_balance - p_due)
                total_due = p_due + i_due

                installments.append({
                    "installment_number": i,
                    "due_date": due_date.isoformat(),
                    "principal_due": float(round_money(p_due)),
                    "interest_due": float(round_money(i_due)),
                    "total_due": float(round_money(total_due)),
                    "remaining_principal": float(round_money(max(Decimal('0'), remaining_balance)))
                })

        elif interest_type == 'SIMPLE_INTEREST':
            # Simple interest per period on original principal
            r_period = rate_annual / periods_per_year
            interest_per_period = round_internal(P * r_period)
            principal_per_period = round_internal(P / Decimal(str(n)))
            remaining_balance = P

            for i in range(1, n + 1):
                due_date = add_frequency_period(start_dt, i, frequency)
                
                if i == n:
                    p_due = remaining_balance
                else:
                    p_due = principal_per_period

                remaining_balance = round_internal(remaining_balance - p_due)
                total_interest += interest_per_period
                total_due = p_due + interest_per_period

                installments.append({
                    "installment_number": i,
                    "due_date": due_date.isoformat(),
                    "principal_due": float(round_money(p_due)),
                    "interest_due": float(round_money(interest_per_period)),
                    "total_due": float(round_money(total_due)),
                    "remaining_principal": float(round_money(max(Decimal('0'), remaining_balance)))
                })

        elif interest_type == 'RULE_OF_78S':
            # Rule of 78s (Sum of digits method for front-loaded interest)
            years = Decimal(str(n)) / periods_per_year
            total_interest = round_internal(P * rate_annual * years)
            sum_of_digits = Decimal(str((n * (n + 1)) // 2))
            
            equal_installment = round_internal((P + total_interest) / Decimal(str(n)))
            remaining_balance = P

            for i in range(1, n + 1):
                due_date = add_frequency_period(start_dt, i, frequency)
                weight = Decimal(str(n - i + 1))
                i_due = round_internal(total_interest * (weight / sum_of_digits))
                
                if i == n:
                    p_due = remaining_balance
                    total_due = p_due + i_due
                else:
                    p_due = round_internal(equal_installment - i_due)
                    total_due = p_due + i_due

                remaining_balance = round_internal(remaining_balance - p_due)

                installments.append({
                    "installment_number": i,
                    "due_date": due_date.isoformat(),
                    "principal_due": float(round_money(p_due)),
                    "interest_due": float(round_money(i_due)),
                    "total_due": float(round_money(total_due)),
                    "remaining_principal": float(round_money(max(Decimal('0'), remaining_balance)))
                })

        elif interest_type == 'COMPOUND_INTEREST':
            # Compound interest periodic compounding
            r = rate_annual / periods_per_year
            if r == Decimal('0'):
                emi = P / Decimal(str(n))
            else:
                one_plus_r = Decimal('1') + r
                factor = one_plus_r ** n
                emi = P * (r * factor) / (factor - Decimal('1'))

            emi = round_internal(emi)
            remaining_balance = P

            for i in range(1, n + 1):
                due_date = add_frequency_period(start_dt, i, frequency)
                interest_for_period = round_internal(remaining_balance * r)

                if i == n:
                    principal_for_period = remaining_balance
                    total_due_for_period = principal_for_period + interest_for_period
                else:
                    principal_for_period = emi - interest_for_period
                    total_due_for_period = emi

                remaining_balance = round_internal(remaining_balance - principal_for_period)
                total_interest += interest_for_period

                installments.append({
                    "installment_number": i,
                    "due_date": due_date.isoformat(),
                    "principal_due": float(round_money(principal_for_period)),
                    "interest_due": float(round_money(interest_for_period)),
                    "total_due": float(round_money(total_due_for_period)),
                    "remaining_principal": float(round_money(max(Decimal('0'), remaining_balance)))
                })

        else:
            raise ValueError(f"Unsupported interest methodology: {interest_type}")

        total_payable = P + total_interest

        return {
            "principal": float(round_money(P)),
            "annual_rate": float(rate_annual * Decimal('100')),
            "interest_type": interest_type,
            "frequency": frequency,
            "tenure_periods": n,
            "start_date": start_dt.isoformat(),
            "total_interest": float(round_money(total_interest)),
            "total_payable": float(round_money(total_payable)),
            "installments": installments
        }

    @staticmethod
    def allocate_payment(payment_amount: Decimal, interest_due: Decimal, principal_due: Decimal, fee_due: Decimal = Decimal('0')) -> Dict[str, Decimal]:
        """
        Waterfall payment allocation strategy:
        1. Fees first
        2. Interest second
        3. Principal third
        """
        payment = Decimal(str(payment_amount))
        i_due = Decimal(str(interest_due))
        p_due = Decimal(str(principal_due))
        f_due = Decimal(str(fee_due))

        fee_paid = min(payment, f_due)
        payment -= fee_paid

        interest_paid = min(payment, i_due)
        payment -= interest_paid

        principal_paid = min(payment, p_due)
        payment -= principal_paid

        overpayment = payment

        return {
            "fee_paid": round_money(fee_paid),
            "interest_paid": round_money(interest_paid),
            "principal_paid": round_money(principal_paid),
            "excess_paid": round_money(overpayment)
        }
