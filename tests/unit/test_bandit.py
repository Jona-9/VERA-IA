"""Bandit epsilon-greedy acotado a la ventana de la política (RF-16, T023)."""

import pytest

from src.domain.entities import RiskBand
from src.policy.bandit import BanditSendDaySelector, EpsilonGreedyBandit
from src.policy.config import load_policy_config

WINDOW = [3, 2, 1]


def test_never_selects_outside_the_authorized_window():
    bandit = EpsilonGreedyBandit(epsilon=0.5, seed=1)
    assert {bandit.select("ALTA", WINDOW) for _ in range(200)} <= set(WINDOW)


def test_exploits_the_best_arm_when_not_exploring():
    bandit = EpsilonGreedyBandit(epsilon=0.0, seed=1)
    for _ in range(5):
        bandit.update("ALTA", 2, 1.0)
        bandit.update("ALTA", 3, 0.0)
        bandit.update("ALTA", 1, 0.0)
    assert all(bandit.select("ALTA", WINDOW) == 2 for _ in range(50))


def test_explores_about_ten_percent_of_the_time():
    bandit = EpsilonGreedyBandit(epsilon=0.10, seed=7)
    for _ in range(5):
        bandit.update("ALTA", 2, 1.0)
    picks = [bandit.select("ALTA", WINDOW) for _ in range(2000)]
    off_best = sum(1 for p in picks if p != 2) / len(picks)
    # Explorar elige al azar entre 3 brazos: ~2/3 de 10 % cae fuera del mejor.
    assert 0.03 < off_best < 0.11


def test_same_seed_gives_the_same_choices():
    first = EpsilonGreedyBandit(0.3, seed=9)
    second = EpsilonGreedyBandit(0.3, seed=9)
    assert [first.select("A", WINDOW) for _ in range(30)] == [second.select("A", WINDOW) for _ in range(30)]


def test_empty_window_is_rejected():
    with pytest.raises(ValueError):
        EpsilonGreedyBandit().select("BAJA", [])


def test_selector_keeps_one_stable_choice_per_account_and_learns_from_outcomes():
    policy = load_policy_config("config/politica.yaml")
    selector = BanditSendDaySelector(policy, seed=3)
    first = selector.choose("ACC-1", RiskBand.ALTA, WINDOW)
    assert all(selector.choose("ACC-1", RiskBand.ALTA, WINDOW) == first for _ in range(10))

    selector.record_outcome("ACC-1", paid_on_time=True)

    assert selector.bandit.mean("ALTA", first) == 1.0
