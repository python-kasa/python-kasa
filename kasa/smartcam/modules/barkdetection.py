"""Implementation of bark detection module."""

from __future__ import annotations

import logging

from kasa.smartcam.detectionmodule import DetectionModule

_LOGGER = logging.getLogger(__name__)


class BarkDetection(DetectionModule):
    """Implementation of bark detection module."""

    REQUIRED_COMPONENT = "barkDetection"

    QUERY_GETTER_NAME = "getBarkDetectionConfig"
    QUERY_MODULE_NAME = "bark_detection"
    QUERY_SECTION_NAMES = "detection"

    DETECTION_FEATURE_ID = "bark_detection"
    DETECTION_FEATURE_NAME = "Bark detection"
    QUERY_SETTER_NAME = "setBarkDetectionConfig"
    QUERY_SET_SECTION_NAME = "detection"
