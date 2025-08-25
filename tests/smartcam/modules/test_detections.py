"""Tests for smartcam detections."""

from __future__ import annotations

from typing import NamedTuple

import pytest

from kasa import Device
from kasa.modulemapping import ModuleName
from kasa.smartcam import DetectionModule
from kasa.smartcam.smartcammodule import SmartCamModule

from ...fixtureinfo import filter_fixtures, idgenerator


class Detection(NamedTuple):
    desc: str
    module: ModuleName[DetectionModule]
    feature_name: str
    component_filter: str
    model_filter: str | None = None


def parametrize_detection(
    *,
    model_filter=None,
    protocol_filter=None,
    fixture_name="dev",
    extra_params_names: list[str],
    extra_params_values: list[Detection],
):
    _pytest_parameters = []

    _arg_names = fixture_name
    if extra_params_names:
        _arg_names = f"{fixture_name},{','.join(extra_params_names)}"

    _model_filter = model_filter

    for _detection in extra_params_values:
        if _detection.model_filter:
            _model_filter = _detection.model_filter

        extra_values = list(map(lambda x: _detection._asdict()[x], extra_params_names))
        _pytest_parameters.extend(
            [
                (i, *extra_values)
                for i in filter_fixtures(
                    _detection.desc,
                    model_filter=_model_filter,
                    protocol_filter=protocol_filter,
                    component_filter=_detection.component_filter,
                    data_root_filter=None,
                    device_type_filter=None,
                )
            ]
        )

    return pytest.mark.parametrize(
        _arg_names,
        _pytest_parameters,
        indirect=[fixture_name],
        ids=idgenerator,
    )


detections = [
    Detection(
        desc="has baby cry detection",
        module=SmartCamModule.SmartCamBabyCryDetection,
        feature_name="baby_cry_detection",
        component_filter="babyCryDetection",
    ),
    Detection(
        desc="has bark detection",
        module=SmartCamModule.SmartCamBarkDetection,
        feature_name="bark_detection",
        component_filter="barkDetection",
    ),
    Detection(
        desc="has glass detection",
        module=SmartCamModule.SmartCamGlassDetection,
        feature_name="glass_detection",
        component_filter="glassDetection",
    ),
    Detection(
        desc="has line crossing detection",
        module=SmartCamModule.SmartCamLineCrossingDetection,
        feature_name="line_crossing_detection",
        component_filter="linecrossingDetection",
        model_filter="C220(EU)_1.0_1.2.5",
    ),
    Detection(
        desc="has meow detection",
        module=SmartCamModule.SmartCamMeowDetection,
        feature_name="meow_detection",
        component_filter="meowDetection",
    ),
    Detection(
        desc="has motion detection",
        module=SmartCamModule.SmartCamMotionDetection,
        feature_name="motion_detection",
        component_filter="detection",
    ),
    Detection(
        desc="has person detection",
        module=SmartCamModule.SmartCamPersonDetection,
        feature_name="person_detection",
        component_filter="personDetection",
    ),
    Detection(
        desc="has pet detection",
        module=SmartCamModule.SmartCamPetDetection,
        feature_name="pet_detection",
        component_filter="petDetection",
    ),
    Detection(
        desc="has tamper detection",
        module=SmartCamModule.SmartCamTamperDetection,
        feature_name="tamper_detection",
        component_filter="tamperDetection",
    ),
    Detection(
        desc="has vehicle detection",
        module=SmartCamModule.SmartCamVehicleDetection,
        feature_name="vehicle_detection",
        component_filter="vehicleDetection",
    ),
]

params_detections = parametrize_detection(
    protocol_filter={"SMARTCAM"},
    extra_params_names=["module", "feature_name"],
    extra_params_values=detections,
)


@params_detections
async def test_detections(
    dev: Device, module: ModuleName[DetectionModule], feature_name: str
):
    detection = dev.modules.get(module)
    assert detection

    detection_feat = dev.features.get(feature_name)
    assert detection_feat

    original_enabled = detection.enabled

    try:
        await detection.set_enabled(not original_enabled)
        await dev.update()
        assert detection.enabled is not original_enabled
        assert detection_feat.value is not original_enabled

        await detection.set_enabled(original_enabled)
        await dev.update()
        assert detection.enabled is original_enabled
        assert detection_feat.value is original_enabled

        await detection_feat.set_value(not original_enabled)
        await dev.update()
        assert detection.enabled is not original_enabled
        assert detection_feat.value is not original_enabled

    finally:
        await detection.set_enabled(original_enabled)
