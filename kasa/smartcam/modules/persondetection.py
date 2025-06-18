"""Implementation of person detection module."""

from __future__ import annotations

import logging

from .detectionmodule import DetectionModule

_LOGGER = logging.getLogger(__name__)


class PersonDetection(DetectionModule):
    """Implementation of person detection module."""

    REQUIRED_COMPONENT = "personDetection"

    QUERY_GETTER_NAME = "getPersonDetectionConfig"
    QUERY_MODULE_NAME = "people_detection"
    QUERY_SECTION_NAMES = "detection"

    DETECTION_FEATURE_ID = "person_detection"
    DETECTION_FEATURE_NAME = "Person detection"
    QUERY_SETTER_NAME = "setPersonDetectionConfig"
