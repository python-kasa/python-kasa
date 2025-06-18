"""Implementation of tamper detection module."""

from __future__ import annotations

import logging

from .detectionmodule import DetectionModule

_LOGGER = logging.getLogger(__name__)


class TamperDetection(DetectionModule):
    """Implementation of tamper detection module."""

    REQUIRED_COMPONENT = "tamperDetection"

    QUERY_GETTER_NAME = "getTamperDetectionConfig"
    QUERY_MODULE_NAME = "tamper_detection"
    QUERY_SECTION_NAMES = "tamper_det"

    DETECTION_FEATURE_ID = "tamper_detection"
    DETECTION_FEATURE_NAME = "Tamper detection"
    QUERY_SETTER_NAME = "setTamperDetectionConfig"
