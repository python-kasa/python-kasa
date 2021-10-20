"""Schedule module implementation."""
from .rulemodule import RuleModule
from .usage import Usage


class Schedule(Usage, RuleModule):
    """Implements the scheduling interface & usage statistics.

    Some devices do not support emeter, but may still keep track about their on/off state.
    This module implements the interface to access that usage data.
    """
