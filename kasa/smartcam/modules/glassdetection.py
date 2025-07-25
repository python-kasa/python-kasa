"""Implementation of glass detection module."""

from __future__ import annotations

import logging

from kasa.smartcam.detectionmodule import DetectionModule

_LOGGER = logging.getLogger(__name__)


class GlassDetection(DetectionModule):
    """Implementation of glass detection module."""

    REQUIRED_COMPONENT = "glassDetection"

    QUERY_GETTER_NAME = "getGlassDetectionConfig"
    QUERY_MODULE_NAME = "glass_detection"
    QUERY_SECTION_NAMES = "detection"

    DETECTION_FEATURE_ID = "glass_detection"
    DETECTION_FEATURE_NAME = "Glass detection"
    QUERY_SETTER_NAME = "setGlassDetectionConfig"
    QUERY_SET_SECTION_NAME = "detection"
