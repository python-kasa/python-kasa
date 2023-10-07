"""Implementation of the antitheft module."""
from .rulemodule import RuleModule


class Antitheft(RuleModule):
    """Implementation of the antitheft module.

    This shares the functionality among other rule-based modules.
    """

    @property
    def is_supported(self) -> bool:
        """Return whether the module is supported by the device."""
        if not super().is_supported:
            return False
        return (
            not (module_data := self._device._last_update.get(self._module))
            or not (get_next_action := module_data.get("get_next_action"))
            or "err_code" not in get_next_action
        )
