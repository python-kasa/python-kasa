"""Implementation of pet detection module."""

from __future__ import annotations

import logging

from .detectionmodule import DetectionModule

_LOGGER = logging.getLogger(__name__)


class PetDetection(DetectionModule):
    """Implementation of pet detection module."""

    REQUIRED_COMPONENT = "petDetection"

    QUERY_GETTER_NAME = "getPetDetectionConfig"
    QUERY_MODULE_NAME = "pet_detection"
    QUERY_SECTION_NAMES = "detection"

    DETECTION_FEATURE_ID = "pet_detection"
    DETECTION_FEATURE_NAME = "Pet detection"
    QUERY_SETTER_NAME = "setPetDetectionConfig"
