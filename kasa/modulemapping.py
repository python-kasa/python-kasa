"""Module for Implementation for ModuleMapping and ModuleName types.

Custom dict for getting typed modules from the module dict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from .module import Module

_ModuleT = TypeVar("_ModuleT", bound="Module")


class ModuleName(str, Generic[_ModuleT]):
    """Generic Module name type.

    At runtime this is a generic subclass of str.
    """

    __slots__ = ()


ModuleMapping = dict
