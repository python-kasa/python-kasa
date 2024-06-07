"""Module for Implementation for typed mappings.

Custom mappings for getting typed modules and features from mapping collections.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from .module import Module

_ModuleT = TypeVar("_ModuleT", bound="Module")

_FeatureT = TypeVar("_FeatureT")


class ModuleName(str, Generic[_ModuleT]):
    """Generic Module name type.

    At runtime this is a generic subclass of str.
    """

    __slots__ = ()


class FeatureId(str, Generic[_FeatureT]):
    """Generic feature id type.

    At runtime this is a generic subclass of str.
    """

    __slots__ = ()


ModuleMapping = dict
FeatureMapping = dict
