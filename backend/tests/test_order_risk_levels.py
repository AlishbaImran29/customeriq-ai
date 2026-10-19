"""Risk levels: the thresholds, the actions, and that nothing is assessed without a trusted model."""

import math
from pathlib import Path

import pytest

from app.services import order_risk_config as config
from app.services.order_risk_levels import LEVELS, action_for, assess_orders, risk_level
from app.services.order_risk_model import train_order_risk
from tests.test_order_risk_model import make_orders


@pytest.mark.parametrize(
    ("probability", "level"),
    [(0.0, "Low"), (0.1999, "Low"), (0.20, "Medium"), (0.35, "Medium"),
     (0.50, "Medium"), (0.5001, "High"), (1.0, "High")],
)
def test_levels_follow_the_agreed_thresholds(probability, level):
    assert risk_level(probability) == level


@pytest.mark.parametrize("bad", [-0.01, 1.01, math.nan])
def test_impossible_probabilities_are_refused(bad):
    with pytest.raises(ValueError):
        risk_level(bad)


def test_thresholds_come_from_the_config_file(monkeypatch):
    monkeypatch.setattr(config, "RISK_LOW_BELOW", 0.30)
    monkeypatch.setattr(config, "RISK_HIGH_ABOVE", 0.60)
    assert [risk_level(p) for p in (0.25, 0.30, 0.60, 0.61)] == ["Low", "Medium", "Medium", "High"]


def test_every_level_has_an_action():
    assert action_for("Low") == "Ship normally"
    assert action_for("Medium") == "Confirm on WhatsApp"
    assert action_for("High") == "Ask for advance payment or call the customer"
    assert set(config.RISK_ACTIONS) == set(LEVELS)


def test_orders_are_assessed_only_when_the_model_is_trusted():
    good, noise = make_orders(signal=True), make_orders(signal=False)
    assert assess_orders(train_order_risk(noise), noise) == {}
    assessed = assess_orders(train_order_risk(good), good)
    assert set(assessed) == {o.order_id for o in good}
    one = next(iter(assessed.values()))
    assert one.level == risk_level(one.probability) and one.action == action_for(one.level)
    assert {a.level for a in assessed.values()} <= set(LEVELS)


def test_every_action_has_an_urdu_translation():
    """The actions are shown through the frontend's translation table (exact English text)."""
    table = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "i18n.ts"
    if not table.exists():
        pytest.skip("frontend folder not available")
    text = table.read_text(encoding="utf-8")
    assert [a for a in config.RISK_ACTIONS.values() if f'"{a}":' not in text] == []
