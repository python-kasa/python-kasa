"""Implementation of vehicle detection module."""

from __future__ import annotations

import logging

from .detectionmodule import DetectionModule

_LOGGER = logging.getLogger(__name__)


class VehicleDetection(DetectionModule):
    """Implementation of vehicle detection module."""

    REQUIRED_COMPONENT = "vehicleDetection"

    QUERY_GETTER_NAME = "getVehicleDetectionConfig"
    QUERY_MODULE_NAME = "vehicle_detection"
    QUERY_SECTION_NAMES = "detection"

    DETECTION_FEATURE_ID = "vehicle_detection"
    DETECTION_FEATURE_NAME = "Vehicle detection"
    QUERY_SETTER_NAME = "setVehicleDetectionConfig"
