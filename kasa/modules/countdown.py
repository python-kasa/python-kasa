"""Implementation for the countdown timer."""
from .rulemodule import CountdownRule, RuleModule


class Countdown(RuleModule):
    """Implementation of countdown module."""

    Rule = CountdownRule
