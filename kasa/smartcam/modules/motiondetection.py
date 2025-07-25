"""Implementation of motion detection module."""

from __future__ import annotations

import logging

from kasa.smartcam.detectionmodule import DetectionModule

_LOGGER = logging.getLogger(__name__)


class MotionDetection(DetectionModule):
    """Implementation of motion detection module."""

    REQUIRED_COMPONENT = "detection"

    QUERY_GETTER_NAME = "getDetectionConfig"
    QUERY_MODULE_NAME = "motion_detection"
    QUERY_SECTION_NAMES = "motion_det"

    DETECTION_FEATURE_ID = "motion_detection"
    DETECTION_FEATURE_NAME = "Motion detection"
    QUERY_SETTER_NAME = "setDetectionConfig"
    QUERY_SET_SECTION_NAME = "motion_det"
