"""
CLI del ciclo diario (RF-12): evalúa la cartera a las 09:00 y despacha a las 10:00.

Uso:
    python -m src.cli.run_cycle --date 2026-10-16
    python -m src.cli.run_cycle --date 2026-10-16 --days 3 --auto-review

Sin `--auto-review`, los casos derivados quedan pendientes y sus avisos se retienen: eso es lo
que ocurre cuando nadie revisa antes del cierre.
"""

import argparse
from datetime import date

from src.agent.orchestrator import DailyCycleOrchestrator, NullDispatcher, SmtpNoticeDispatcher
from src.analytics.model import RiskModel
from src.data.sqlite_repo import SQLitePortfolioRepository
from src.domain.entities import ActionType
from src.mail.server import SQLiteCaptureStore, start_embedded_server
from src.policy.config import load_policy_config
from src.simulation.engine import CustomerBehavior, SimulationEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecuta el ciclo diario de cobranza temprana de VERAIA.")
    parser.add_argument("--db", default="data/portfolio_demo.db")
    parser.add_argument("--model", default="reports/risk_model.joblib")
    parser.add_argument("--policy", default="config/politica.yaml")
    parser.add_argument("--date", default="2026-10-15", help="Fecha del primer ciclo (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=1, help="Cantidad de días a simular")
    parser.add_argument("--auto-review", action="store_true", help="Simula al analista resolviendo la cola")
    parser.add_argument("--no-smtp", action="store_true", help="No levantar el servidor SMTP local")
    args = parser.parse_args()

    start = date.fromisoformat(args.date)
    repo = SQLitePortfolioRepository(args.db)
    policy = load_policy_config(args.policy)
    orchestrator = DailyCycleOrchestrator(repo, RiskModel.load(args.model), policy)
    if args.no_smtp:
        dispatcher = NullDispatcher()
    else:
        start_embedded_server(store=SQLiteCaptureStore(args.db))
        dispatcher = SmtpNoticeDispatcher(repo)

    engine = SimulationEngine(repo, orchestrator, CustomerBehavior(), dispatcher, start, args.auto_review)
    result = engine.begin_day(engine.current_date if engine.phase else start)
    for step in range(args.days):
        dispatch = engine.close_day()
        cycle = result.cycle
        print(
            f"{result.cycle_date}: {len(result.payments)} pagos | {cycle.count(ActionType.SCHEDULE_NOTICE)} avisos aprobados | "
            f"{len(repo.get_review_queue())} casos en revisión | {len(dispatch.sent)} enviados | "
            f"{len(dispatch.held)} retenidos | evaluación {cycle.elapsed_seconds:.2f}s"
        )
        if step + 1 < args.days:
            result = engine.advance_day()


if __name__ == "__main__":
    main()
