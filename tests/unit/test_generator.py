"""
Pruebas unitarias de integridad y reproducibilidad para PortfolioGenerator.
Verifica cumplimiento de T004 y RF-01.
"""

from datetime import date
import pytest

from src.data.generator import PortfolioGenerator


def test_generator_reproducibility():
    """Verifica que la misma semilla genere exactamente los mismos datos."""
    gen1 = PortfolioGenerator(seed=42, cutoff_date=date(2026, 10, 15))
    c1, a1, p1, pay1 = gen1.generate_portfolio(num_customers=20)

    gen2 = PortfolioGenerator(seed=42, cutoff_date=date(2026, 10, 15))
    c2, a2, p2, pay2 = gen2.generate_portfolio(num_customers=20)

    assert len(c1) == len(c2) == 20
    assert len(a1) == len(a2) == 20
    assert len(p1) == len(p2)
    assert len(pay1) == len(pay2)

    for cust1, cust2 in zip(c1, c2):
        assert cust1.customer_id == cust2.customer_id
        assert cust1.full_name == cust2.full_name
        assert cust1.email == cust2.email

    for acc1, acc2 in zip(a1, a2):
        assert acc1.account_id == acc2.account_id
        assert acc1.credit_limit == acc2.credit_limit
        assert acc1.current_balance == acc2.current_balance
        assert acc1.due_date == acc2.due_date


def test_generator_different_seeds_produce_variance():
    """Verifica que semillas distintas generen datos diferentes."""
    gen1 = PortfolioGenerator(seed=42, cutoff_date=date(2026, 10, 15))
    c1, _, _, _ = gen1.generate_portfolio(num_customers=10)

    gen2 = PortfolioGenerator(seed=999, cutoff_date=date(2026, 10, 15))
    c2, _, _, _ = gen2.generate_portfolio(num_customers=10)

    names1 = [c.full_name for c in c1]
    names2 = [c.full_name for c in c2]
    assert names1 != names2


def test_generator_profiles_and_edge_cases():
    """Verifica la presencia de todos los perfiles de cartera requeridos."""
    gen = PortfolioGenerator(seed=42, cutoff_date=date(2026, 10, 15))
    customers, accounts, periods, pending_payments = gen.generate_portfolio(num_customers=60)

    # 1. Validación de identificadores y límites
    for c in customers:
        assert c.customer_id.startswith("CUST-")
        assert "@" in c.email
        assert c.contact_enabled is True

    for a in accounts:
        assert a.account_id.startswith("ACC-")
        assert a.credit_limit > 0
        assert a.current_balance >= 0
        assert a.minimum_payment > 0

    # 2. Clientes nuevos con historial corto (< 3 períodos)
    periods_by_account = {}
    for p in periods:
        periods_by_account.setdefault(p.account_id, []).append(p)

    short_history_accounts = [acc_id for acc_id, plist in periods_by_account.items() if len(plist) < 3]
    assert len(short_history_accounts) > 0, "Debe haber clientes nuevos con menos de 3 períodos de historial"

    # 3. Casos de deterioro incipiente (alta utilización > 90%)
    high_utilization_accounts = [a for a in accounts if (a.current_balance / a.credit_limit) >= 0.90]
    assert len(high_utilization_accounts) > 0, "Debe haber cuentas con utilización superior al 90%"

    # 4. Inconsistencias de pago demorado (pagos en trámite)
    assert len(pending_payments) > 0, "Debe haber pagos pendientes en tránsito para evaluar inconsistencias"
    for pay in pending_payments:
        assert pay.status == "IN_PROCESS"
        assert pay.amount > 0

    # 5. Casos con moras crónicas (días de atraso significativos)
    chronic_delinquency = [p for p in periods if p.days_past_due > 10]
    assert len(chronic_delinquency) > 0, "Debe haber períodos con atraso prolongado para perfil crónico"
