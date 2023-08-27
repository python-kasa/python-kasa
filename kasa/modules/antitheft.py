"""Implementation of the antitheft module."""
from .rulemodule import RuleModule, ScheduleRule


class Antitheft(RuleModule):
    """Implementation of the antitheft module.

    This shares the functionality among other rule-based modules.
    """

    Rule = ScheduleRule
