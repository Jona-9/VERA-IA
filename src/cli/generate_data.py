"""
CLI para generar la base de datos de prueba SQLite con datos sintéticos reproducibles.
Uso:
    python -m src.cli.generate_data --seed 42 --db-path data/portfolio_demo.db --customers 60
"""

import argparse
from datetime import date
import os
import sys

from src.data.generator import PortfolioGenerator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generador de cartera reproducible para VERAIA (Hackathon Vertical Slice)"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semilla determinista para números pseudoaleatorios (default: 42)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/portfolio_demo.db",
        help="Ruta de destino de la base de datos SQLite (default: data/portfolio_demo.db)",
    )
    parser.add_argument(
        "--customers",
        type=int,
        default=60,
        help="Número total de clientes a generar (default: 60)",
    )
    parser.add_argument(
        "--cutoff-date",
        type=str,
        default="2026-10-15",
        help="Fecha de corte en formato YYYY-MM-DD (default: 2026-10-15)",
    )

    args = parser.parse_args()

    # Asegurar que el directorio de datos existe
    db_dir = os.path.dirname(args.db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    cutoff = date.fromisoformat(args.cutoff_date)
    print(f"============================================================")
    print(f" Generando Cartera Sintética VERAIA")
    print(f"============================================================")
    print(f" Semilla:           {args.seed}")
    print(f" Clientes:          {args.customers}")
    print(f" Fecha de corte:    {cutoff}")
    print(f" Archivo SQLite:    {args.db_path}")
    print(f"------------------------------------------------------------")

    generator = PortfolioGenerator(seed=args.seed, cutoff_date=cutoff)
    repo = generator.populate_database(db_path=args.db_path, num_customers=args.customers)

    accounts = repo.get_portfolio_accounts(cutoff_date=cutoff)
    print(f"✔ Cuentas generadas y guardadas: {len(accounts)}")

    # Resumen rápido de comprobación
    sample_acc = accounts[0]
    history = repo.get_period_history(sample_acc.account_id, cutoff_date=cutoff)
    print(f"✔ Muestra cuenta {sample_acc.account_id}: límite={sample_acc.credit_limit}, saldo={sample_acc.current_balance}")
    print(f"✔ Períodos históricos cargados para muestra: {len(history)}")
    print(f"============================================================")
    print(f" ¡Base de datos lista en: {args.db_path}!")


if __name__ == "__main__":
    main()
