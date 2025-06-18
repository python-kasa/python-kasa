"""Implementation of meow detection module."""

from __future__ import annotations

import logging

from .detectionmodule import DetectionModule

_LOGGER = logging.getLogger(__name__)


class MeowDetection(DetectionModule):
    """Implementation of meow detection module."""

    REQUIRED_COMPONENT = "meowDetection"

    QUERY_GETTER_NAME = "getMeowDetectionConfig"
    QUERY_MODULE_NAME = "meow_detection"
    QUERY_SECTION_NAMES = "detection"

    DETECTION_FEATURE_ID = "meow_detection"
    DETECTION_FEATURE_NAME = "Meow detection"
    QUERY_SETTER_NAME = "setMeowDetectionConfig"
    QUERY_SET_SECTION_NAME = "detection"
