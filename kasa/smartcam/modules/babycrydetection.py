"""Implementation of baby cry detection module."""

from __future__ import annotations

import logging

from kasa.smartcam.detectionmodule import DetectionModule

_LOGGER = logging.getLogger(__name__)


class BabyCryDetection(DetectionModule):
    """Implementation of baby cry detection module."""

    REQUIRED_COMPONENT = "babyCryDetection"

    QUERY_GETTER_NAME = "getBCDConfig"
    QUERY_MODULE_NAME = "sound_detection"
    QUERY_SECTION_NAMES = "bcd"

    DETECTION_FEATURE_ID = "baby_cry_detection"
    DETECTION_FEATURE_NAME = "Baby cry detection"
    QUERY_SETTER_NAME = "setBCDConfig"
    QUERY_SET_SECTION_NAME = "bcd"
