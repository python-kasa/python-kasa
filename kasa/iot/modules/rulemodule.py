"""Base implementation for all rule-based modules."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, List, Optional

from pydantic.v1 import BaseModel

from ..iotmodule import IotModule, merge


class Action(Enum):
    """Action to perform."""

    Disabled = -1
    TurnOff = 0
    TurnOn = 1
    Unknown = 2


class TimeOption(Enum):
    """Time when the action is executed."""

    Disabled = -1
    Enabled = 0
    AtSunrise = 1
    AtSunset = 2


class Rule(BaseModel):
    """Representation of a rule."""

    id: str
    name: str
    enable: bool
    wday: List[int]  # noqa: UP006
    repeat: bool

    # start action
    sact: Optional[Action]  # noqa: UP007
    stime_opt: TimeOption
    smin: int

    eact: Optional[Action]  # noqa: UP007
    etime_opt: TimeOption
    emin: int

    # Only on bulbs
    s_light: Optional[Dict]  # noqa: UP006,UP007


_LOGGER = logging.getLogger(__name__)


class RuleModule(IotModule):
    """Base class for rule-based modules, such as countdown and antitheft."""

    def query(self):
        """Prepare the query for rules."""
        q = self.query_for_command("get_rules")
        return merge(q, self.query_for_command("get_next_action"))

    @property
    def rules(self) -> list[Rule]:
        """Return the list of rules for the service."""
        try:
            return [
                Rule.parse_obj(rule) for rule in self.data["get_rules"]["rule_list"]
            ]
        except Exception as ex:
            _LOGGER.error("Unable to read rule list: %s (data: %s)", ex, self.data)
            return []

    async def set_enabled(self, state: bool):
        """Enable or disable the service."""
        return await self.call("set_overall_enable", state)

    async def delete_rule(self, rule: Rule):
        """Delete the given rule."""
        return await self.call("delete_rule", {"id": rule.id})

    async def delete_all_rules(self):
        """Delete all rules."""
        return await self.call("delete_all_rules")
