"""Tests for smartcam detections."""

from __future__ import annotations

from kasa.modulemapping import ModuleName
from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule
from kasa.smartcam import DetectionModule

from ...device_fixtures import parametrize, dev


baby_cry_detection = parametrize(
    "has babycry detection",
    component_filter="babyCryDetection",
    protocol_filter={"SMARTCAM"},
)

bark_detection = parametrize(
    "has bark detection",
    component_filter="barkDetection",
    protocol_filter={"SMARTCAM"},
)

glass_detection = parametrize(
    "has glass detection",
    component_filter="glassDetection",
    protocol_filter={"SMARTCAM"},
)

line_crossing_detection = parametrize(
    "has line crossing detection",
    component_filter="linecrossingDetection",
    protocol_filter={"SMARTCAM"},
    model_filter="C220(EU)_1.0_1.2.5",
)

meow_detection = parametrize(
    "has meow detection",
    component_filter="meowDetection",
    protocol_filter={"SMARTCAM"},
)

motion_detection = parametrize(
    "has motion detection", component_filter="detection", protocol_filter={"SMARTCAM"}
)

person_detection = parametrize(
    "has person detection",
    component_filter="personDetection",
    protocol_filter={"SMARTCAM"},
)

pet_detection = parametrize(
    "has pet detection",
    component_filter="petDetection",
    protocol_filter={"SMARTCAM"},
)

tamper_detection = parametrize(
    "has tamper detection",
    component_filter="tamperDetection",
    protocol_filter={"SMARTCAM"},
)

vehicle_detection = parametrize(
    "has vehicle detection",
    component_filter="vehicleDetection",
    protocol_filter={"SMARTCAM"},
)


@baby_cry_detection
async def test_baby_cry_detection(dev: Device):
    """Test device baby cry detection."""
    await common_test(
        dev, SmartCamModule.SmartCamBabyCryDetection, "baby_cry_detection"
    )


@bark_detection
async def test_bark_detection(dev: Device):
    """Test device bark detection."""
    await common_test(dev, SmartCamModule.SmartCamBarkDetection, "bark_detection")


@glass_detection
async def test_glass_detection(dev: Device):
    """Test device glass detection."""
    await common_test(dev, SmartCamModule.SmartCamGlassDetection, "glass_detection")


@line_crossing_detection
async def test_line_crossing_detection(dev: Device):
    """Test device line crossing detection."""
    await common_test(
        dev, SmartCamModule.SmartCamLineCrossingDetection, "line_crossing_detection"
    )


@meow_detection
async def test_meow_detection(dev: Device):
    """Test device meow detection."""
    await common_test(dev, SmartCamModule.SmartCamMeowDetection, "meow_detection")


@motion_detection
async def test_motion_detection(dev: Device):
    """Test device motion detection."""
    await common_test(dev, SmartCamModule.SmartCamMotionDetection, "motion_detection")


@person_detection
async def test_person_detection(dev: Device):
    """Test device person detection."""
    await common_test(dev, SmartCamModule.SmartCamPersonDetection, "person_detection")


@pet_detection
async def test_pet_detection(dev: Device):
    """Test device pet detection."""
    await common_test(dev, SmartCamModule.SmartCamPetDetection, "pet_detection")


@tamper_detection
async def test_tamper_detection(dev: Device):
    """Test device tamper detection."""
    await common_test(dev, SmartCamModule.SmartCamTamperDetection, "tamper_detection")


@vehicle_detection
async def test_vehicle_detection(dev: Device):
    """Test device vehicle detection."""
    await common_test(dev, SmartCamModule.SmartCamVehicleDetection, "vehicle_detection")


async def common_test(
    device: Device, module: ModuleName[DetectionModule], feature_name: str
):
    detection = device.modules.get(module)
    assert detection

    detection_feat = device.features.get(feature_name)
    assert detection_feat

    original_enabled = detection.enabled

    try:
        await detection.set_enabled(not original_enabled)
        await device.update()
        assert detection.enabled is not original_enabled
        assert detection_feat.value is not original_enabled

        await detection.set_enabled(original_enabled)
        await device.update()
        assert detection.enabled is original_enabled
        assert detection_feat.value is original_enabled

        await detection_feat.set_value(not original_enabled)
        await device.update()
        assert detection.enabled is not original_enabled
        assert detection_feat.value is not original_enabled

    finally:
        await detection.set_enabled(original_enabled)
