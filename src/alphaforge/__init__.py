"""AlphaForge: Qlib-native quantitative research platform.

Layers
------
data      : A-share market / PIT fundamentals / sentiment ingestion + Qlib bin export
expr      : vectorized factor expression engine (parser + operator library)
evaluate  : IC / quantile / turnover / gate / report
mining    : genetic-programming factor mining + factor registry
portfolio : multi-factor combination, risk model, constrained optimizer
backtest  : A-share constrained event-driven backtester (calendar & event cross-section)
event     : T0 volume-surge event detection, labels, leakage audit
"""

__version__ = "0.1.0"

from alphaforge.config import Config, load_config  # noqa: F401
