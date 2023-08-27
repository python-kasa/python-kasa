"""Base implementation for all rule-based modules."""
import json
import logging
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from .module import Module, merge


class EnabledOption(Enum):
    """Integer enabled option."""

    TurnOff = 0
    Enabled = 1


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


class BaseRule(BaseModel):
    """Representation of a rule."""

    # not used when adding a rule
    id: Optional[str]
    name: str
    enable: EnabledOption

    class Config:
        """Rule Config."""

        validate_assignment = True
        allow_population_by_field_name = True


class CountdownRule(BaseRule):
    """Representation of a countdown rule."""

    delay: int
    act: EnabledOption = Field(alias="action")


class ScheduleRule(BaseRule):
    """Representation of a schedule rule."""

    wday: List[int] = Field(alias="days")
    repeat: EnabledOption

    # start action
    sact: Optional[Action] = Field(alias="start_action")
    stime_opt: TimeOption = Field(alias="start?")
    smin: int = Field(alias="start_minutes", ge=0, le=1440)

    # end action
    eact: Optional[Action] = Field(alias="end_action")
    # Required to submit, but the device will not return it if set to -1
    etime_opt: TimeOption = Field(default=TimeOption.Disabled, alias="end?")
    emin: Optional[int] = Field(alias="end_minutes", ge=0, le=1440)


class BulbScheduleRule(BaseRule):
    """Representation of a bulb schedule rule."""

    s_light: Optional[Dict] = Field(alias="lights")


_LOGGER = logging.getLogger(__name__)


class RuleModule(Module):
    """Base class for rule-based modules, such as antitheft, countdown and schedule."""

    Rule = BaseRule

    def query(self):
        """Prepare the query for rules."""
        q = self.query_for_command("get_rules")
        return merge(q, self.query_for_command("get_next_action"))

    @property
    def rules(self) -> List[BaseRule]:
        """Return the list of rules for the service."""
        try:
            return [
                self.Rule.parse_obj(rule)
                for rule in self.data["get_rules"]["rule_list"]
            ]
        except Exception as ex:
            _LOGGER.error("Unable to read rule list: %s (data: %s)", ex, self.data)
            return []

    async def set_enabled(self, state: int):
        """Enable or disable the service."""
        return await self.call("set_overall_enable", {"enable": state})

    async def add_rule(self, rule: BaseRule):
        """Add a new rule."""
        return await self.call("add_rule", json.loads(rule.json(exclude_none=True)))

    async def edit_rule(self, rule: BaseRule):
        """Edit the given rule."""
        return await self.call("edit_rule", json.loads(rule.json(exclude_none=True)))

    async def delete_rule(self, rule: BaseRule):
        """Delete the given rule."""
        return await self.call("delete_rule", {"id": rule.id})

    async def delete_all_rules(self):
        """Delete all rules."""
        return await self.call("delete_all_rules")
