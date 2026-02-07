"""
Stop-and-Go strategy implementations.

Import triggers registration so strategies are available when the
package is imported.
"""

from .predictive import PredictiveStrategy
from .verified import VerifiedStrategy

__all__ = ["PredictiveStrategy", "VerifiedStrategy"]
