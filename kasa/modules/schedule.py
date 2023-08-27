"""Schedule module implementation."""
from .rulemodule import BulbScheduleRule, RuleModule, ScheduleRule


class Schedule(RuleModule):
    """Implements the scheduling interface."""

    Rule = ScheduleRule


class BulbSchedule(RuleModule):
    """Implements the scheduling interface."""

    Rule = BulbScheduleRule
