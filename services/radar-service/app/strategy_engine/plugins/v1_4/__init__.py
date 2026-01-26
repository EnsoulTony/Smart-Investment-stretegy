"""v1.4 Strategy Plugin: EDS (Economic Direction Signal) Minimum Viable.

Based on XLU/XLK sector rotation indicators.
Implements scoring-based mode detection with falsifiable triggers.
"""

from .plugin import V1_4Plugin
from .rules import (
    FACTOR_GROUPS,
    GROUP_LIMITS,
    compute_mode_scores,
    determine_mode,
    compute_exposure,
    determine_decision,
)

__all__ = [
    "V1_4Plugin",
    "FACTOR_GROUPS",
    "GROUP_LIMITS",
    "compute_mode_scores",
    "determine_mode",
    "compute_exposure",
    "determine_decision",
]
