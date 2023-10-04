"""Implementation of the antitheft module."""
from .rulemodule import RuleModule


class Antitheft(RuleModule):
    """Implementation of the antitheft module.

    This shares the functionality among other rule-based modules.
    """

    @property
    def is_supported(self) -> bool:
        """Return whether the module is supported by the device."""
        if (
            (is_supported := super().is_supported)
            and (module_data := self._device._last_update.get(self._module))
            and (get_next_action := module_data.get("get_next_action"))
            and "err_code" in get_next_action
        ):
            return False
        return is_supported
