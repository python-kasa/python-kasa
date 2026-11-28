"""Implementation for the countdown timer."""

from .rulemodule import CountdownRule, RuleModule


class Countdown(RuleModule[CountdownRule]):
    """Implementation of countdown module.

    The device has no overall switch for countdown rules, so enable or
    disable single rules instead.
    """

    _rule_class = CountdownRule
