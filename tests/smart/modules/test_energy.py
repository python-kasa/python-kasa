import pytest

from kasa import Module, SmartDevice
from kasa.interfaces.energy import Energy
from kasa.smart.modules import Energy as SmartEnergyModule
from tests.conftest import has_emeter_smart


@has_emeter_smart
async def test_supported(dev: SmartDevice):
    energy_module = dev.modules.get(Module.Energy)
    if not energy_module:
        pytest.skip(f"Energy module not supported for {dev}.")

    assert isinstance(energy_module, SmartEnergyModule)
    assert energy_module.supports(Energy.ModuleFeature.CONSUMPTION_TOTAL) is False
    assert energy_module.supports(Energy.ModuleFeature.PERIODIC_STATS) is False
    if energy_module.supported_version < 2:
        assert energy_module.supports(Energy.ModuleFeature.VOLTAGE_CURRENT) is False
    else:
        assert energy_module.supports(Energy.ModuleFeature.VOLTAGE_CURRENT) is True
