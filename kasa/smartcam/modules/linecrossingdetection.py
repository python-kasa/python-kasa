"""Implementation of line crossing detection module."""

from __future__ import annotations

import logging

from kasa.smartcam.detectionmodule import DetectionModule

_LOGGER = logging.getLogger(__name__)


class LineCrossingDetection(DetectionModule):
    """Implementation of line crossing detection module."""

    REQUIRED_COMPONENT = "linecrossingDetection"

    QUERY_GETTER_NAME = "getLinecrossingDetectionConfig"
    QUERY_MODULE_NAME = "linecrossing_detection"
    QUERY_SECTION_NAMES = "detection"

    DETECTION_FEATURE_ID = "line_crossing_detection"
    DETECTION_FEATURE_NAME = "Line crossing detection"
    QUERY_SETTER_NAME = "setLinecrossingDetectionConfig"
    QUERY_SET_SECTION_NAME = "detection"
