"""Implementation of the antitheft module."""

from .rulemodule import Rule, RuleModule


class Antitheft(RuleModule[Rule]):
    """Implementation of the antitheft module.

    This shares the functionality among other rule-based modules.
    """

    _rule_class = Rule
