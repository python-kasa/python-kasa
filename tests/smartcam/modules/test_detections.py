"""Tests for smartcam detections."""

from __future__ import annotations
from typing import List, Any, Dict, NamedTuple, Optional
from kasa.modulemapping import ModuleName
from kasa import Device
from kasa.smartcam.smartcammodule import SmartCamModule
from kasa.smartcam import DetectionModule

from ...device_fixtures import dev
from ...fixtureinfo import filter_fixtures, ComponentFilter, idgenerator


import pytest

baby_cry_detection = parametrize(
    "has babycry detection",
    component_filter="babyCryDetection",
    protocol_filter={"SMARTCAM"},
)

def parametrize_detection(
    *,
    model_filter=None,
    protocol_filter=None,
    fixture_name="dev",
    other_params_names: List[str] | None = None,
    other_params_values: Dict[
        str, Dict[str, str | ModuleName[DetectionModule] | ComponentFilter]
    ]
    | None = None,
):
    _parameters = []

bark_detection = parametrize(
    "has bark detection",
    component_filter="barkDetection",
    protocol_filter={"SMARTCAM"},
)
    _all_inputs = fixture_name
    if other_params_names:
        _all_inputs = f"{fixture_name},{','.join(other_params_names)}"

    _model_filter = model_filter

    for _detection in other_params_values.values():

glass_detection = parametrize(
    "has glass detection",
    component_filter="glassDetection",
    protocol_filter={"SMARTCAM"},
)
        if 'model_filter' in _detection:
            _model_filter = _detection['model_filter']

line_crossing_detection = parametrize(
    "has line crossing detection",
    component_filter="linecrossingDetection",
    protocol_filter={"SMARTCAM"},
    model_filter="C220(EU)_1.0_1.2.5",
)
        other_val = list(map(lambda x: _detection[x], other_params_names))
        _parameters.extend(
            [
                (i, *other_val)
                for i in filter_fixtures(
                    _detection["desc"],
                    model_filter=_model_filter,
                    protocol_filter=protocol_filter,
                    component_filter=_detection["component_filter"],
                    data_root_filter=None,
                    device_type_filter=None,
                )
            ])

meow_detection = parametrize(
    "has meow detection",
    component_filter="meowDetection",
    protocol_filter={"SMARTCAM"},
)

motion_detection = parametrize(
    "has motion detection", component_filter="detection", protocol_filter={"SMARTCAM"}
)
    return pytest.mark.parametrize(
        _all_inputs,
        _parameters,
        indirect=[fixture_name],
        ids=idgenerator,
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

params_detections = parametrize_detection(
    protocol_filter={"SMARTCAM"},
    other_params_names=["module", "feature_name"],
    other_params_values={
        "baby_cry": {
            "desc": "has baby cry detection",
            "module": SmartCamModule.SmartCamBabyCryDetection,
            "feature_name": "baby_cry_detection",
            "component_filter": "babyCryDetection",
        },
        "bark": {
            "desc": "has bark detection",
            "module": SmartCamModule.SmartCamBarkDetection,
            "feature_name": "bark_detection",
            "component_filter": "barkDetection",
        },
        "glass": {
            "desc": "has glass detection",
            "module": SmartCamModule.SmartCamGlassDetection,
            "feature_name": "glass_detection",
            "component_filter": "glassDetection",
        },
        "line_crossing": {
            "desc": "has line crossing detection",
            "module": SmartCamModule.SmartCamLineCrossingDetection,
            "feature_name": "line_crossing_detection",
            "component_filter": "linecrossingDetection",
            "model_filter": "C220(EU)_1.0_1.2.5",
        },
        "meow": {
            "desc": "has meow detection",
            "module": SmartCamModule.SmartCamMeowDetection,
            "feature_name": "meow_detection",
            "component_filter": "meowDetection",
        },
        "motion": {
            "desc": "has motion detection",
            "module": SmartCamModule.SmartCamMotionDetection,
            "feature_name": "motion_detection",
            "component_filter": "detection",
        },
        "person": {
            "desc": "has person detection",
            "module": SmartCamModule.SmartCamPersonDetection,
            "feature_name": "person_detection",
            "component_filter": "personDetection",
        },
        "pet": {
            "desc": "has pet detection",
            "module": SmartCamModule.SmartCamPetDetection,
            "feature_name": "pet_detection",
            "component_filter": "petDetection",
        },
        "tamper": {
            "desc": "has tamper detection",
            "module": SmartCamModule.SmartCamTamperDetection,
            "feature_name": "tamper_detection",
            "component_filter": "tamperDetection",
        },

        "vehicle": {
            "desc": "has vehicle detection",
            "module": SmartCamModule.SmartCamVehicleDetection,
            "feature_name": "vehicle_detection",
            "component_filter": "vehicleDetection",
        },
    },
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
