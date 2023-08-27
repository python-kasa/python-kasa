"""Implementation of the antitheft module."""
from .rulemodule import AntitheftRule, RuleModule


class Antitheft(RuleModule):
    """Implementation of the antitheft module.

    This shares the functionality among other rule-based modules.
    """

    Rule = AntitheftRule
