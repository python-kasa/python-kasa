"""Base implementation for all rule-based modules."""
import logging, json
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel

from .module import Module, merge


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


class Rule(BaseModel, validate_assignment=True):
    """Representation of a rule."""

    # not used when adding a rule
    id: Optional[str]
    name: str
    enable: int
    wday: List[int]
    repeat: int

    # start action
    sact: Optional[Action]
    stime_opt: TimeOption
    smin: int

    # end action
    eact: Optional[Action]
    # Required to submit, but the device will not return it if set to -1
    etime_opt: TimeOption = TimeOption.Disabled
    emin: Optional[int]

    # Only on bulbs
    s_light: Optional[Dict]


_LOGGER = logging.getLogger(__name__)


class RuleModule(Module):
    """Base class for rule-based modules, such as antitheft, countdown and schedule."""

    def query(self):
        """Prepare the query for rules."""
        q = self.query_for_command("get_rules")
        return merge(q, self.query_for_command("get_next_action"))

    @property
    def rules(self) -> List[Rule]:
        """Return the list of rules for the service."""
        try:
            return [
                Rule.parse_obj(rule) for rule in self.data["get_rules"]["rule_list"]
            ]
        except Exception as ex:
            _LOGGER.error("Unable to read rule list: %s (data: %s)", ex, self.data)
            return []

    async def set_enabled(self, state: int):
        """Enable or disable the service."""
        return await self.call("set_overall_enable", {"enable": state})

    async def add_rule(self, rule: Rule):
        """Add a new rule."""
        return await self.call("add_rule", json.loads(rule.json(exclude_none=True)))

    async def edit_rule(self, rule: Rule):
        """Edit the given rule."""
        return await self.call("edit_rule", json.loads(rule.json(exclude_none=True)))

    async def delete_rule(self, rule: Rule):
        """Delete the given rule."""
        return await self.call("delete_rule", {"id": rule.id})

    async def delete_all_rules(self):
        """Delete all rules."""
        return await self.call("delete_all_rules")
