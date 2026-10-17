"""
Multi-Armed Bandit epsilon-greedy para elegir el día del aviso preventivo (RF-16).

Cada brazo es "enviar a N días del vencimiento". El bandit solo elige entre los días que la
política ya autoriza para la banda (`window_days_before_due`): explora con probabilidad
`epsilon` (10 % por defecto, `multi_armed_bandit.exploration_rate`) y en el resto explota el
brazo con mayor tasa de pago oportuno. No puede ampliar ventanas, cuotas ni tonos; esos límites
los sigue imponiendo `ScheduleNoticeTool`.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

from src.domain.entities import RiskBand
from src.policy.config import PolicyConfig


class EpsilonGreedyBandit:
    def __init__(self, epsilon: float = 0.10, seed: int = 42):
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("epsilon debe estar en [0, 1]")
        self.epsilon = epsilon
        self._rng = random.Random(seed)
        self._pulls: Dict[Tuple[str, int], int] = defaultdict(int)
        self._reward: Dict[Tuple[str, int], float] = defaultdict(float)

    def mean(self, context: str, arm: int) -> float:
        pulls = self._pulls[(context, arm)]
        return self._reward[(context, arm)] / pulls if pulls else 0.0

    def select(self, context: str, arms: Sequence[int]) -> int:
        if not arms:
            raise ValueError("No hay brazos disponibles: la política no autoriza ventana")
        if self._rng.random() < self.epsilon:
            return self._rng.choice(list(arms))
        best = max(self.mean(context, a) for a in arms)
        return self._rng.choice([a for a in arms if self.mean(context, a) == best])

    def update(self, context: str, arm: int, reward: float) -> None:
        self._pulls[(context, arm)] += 1
        self._reward[(context, arm)] += reward

    def stats(self) -> List[Dict[str, float]]:
        return [
            {"contexto": ctx, "dias_antes": arm, "envios": n, "tasa_pago_oportuno": self.mean(ctx, arm)}
            for (ctx, arm), n in sorted(self._pulls.items())
        ]


class BanditSendDaySelector:
    """Adaptador al orquestador: una decisión estable por cuenta y ventana, y aprendizaje al pagar."""

    def __init__(self, policy: PolicyConfig, seed: int = 42):
        self.bandit = EpsilonGreedyBandit(policy.multi_armed_bandit.exploration_rate, seed)
        self._choice: Dict[Tuple[str, Tuple[int, ...]], int] = {}
        self._by_account: Dict[str, Tuple[str, int]] = {}

    def choose(self, account_id: str, band: RiskBand, window_days: List[int]) -> int:
        key = (account_id, tuple(sorted(window_days)))
        if key not in self._choice:
            arm = self.bandit.select(band.value, window_days)
            self._choice[key] = arm
            self._by_account[account_id] = (band.value, arm)
        return self._choice[key]

    def record_outcome(self, account_id: str, paid_on_time: bool) -> None:
        """Recompensa 1 si el cliente pagó a más tardar el día de vencimiento."""
        used = self._by_account.pop(account_id, None)
        if used is not None:
            self.bandit.update(used[0], used[1], 1.0 if paid_on_time else 0.0)
