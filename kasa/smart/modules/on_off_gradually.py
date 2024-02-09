from ..smartmodule import SmartModule
from ...descriptors import Descriptor, DescriptorType, DescriptorCategory

class OnOffGradually(SmartModule):
    """Implementation of gradual on/off."""

    REQUIRED_COMPONENT = "on_off_gradually"
    QUERY_GETTER_NAME = "get_on_off_gradually_info"

    def __init__(self, device: "Device", module: str):
        super().__init__(device, module)
        self.add_descriptor(
            Descriptor(
                device=self,
                name="Smooth transitions",
                icon="mdi:transition",
                attribute_getter="enabled",
                attribute_setter="set_enabled",
                category=DescriptorCategory.Config,
                type=DescriptorType.Switch,
            )
        )

    def set_enabled(self, enable: bool):
        """Enable gradual on/off."""
        return self.call("set_on_off_gradually_info", {"enable": enable})

    @property
    def enabled(self) -> bool:
        """Return True if gradual on/off is enabled."""
        return bool(self.data["enable"])

    def __cli_output__(self):
        return f"Gradual on/off enabled: {self.enabled}"
