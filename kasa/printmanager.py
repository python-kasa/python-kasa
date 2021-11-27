"""Print manager for the kasa cli tool. Handles the logic for different formats like json or human-readable."""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from enum import Flag, auto
from typing import Any, Dict

import asyncclick as click

_LOGGER = logging.getLogger(__name__)


class StyleFlag(Flag):
    """StyleFlags for beautifying output."""

    RED = auto()
    GREEN = auto()
    BOLD = auto()
    NONE = 0


class DataWrapper(ABC):
    """Holds structured data to be printed later."""

    @property
    @abstractmethod
    def data(self) -> dict[Any, Any]:
        """Get the structured data."""
        pass

    @abstractmethod
    def add_point(self, key, value, name: str = None, style: StyleFlag = None) -> None:
        """Add a single data point."""
        pass

    @abstractmethod
    def add_categorie(
        self,
        key,
        data: dict[Any, Any] = None,
        name: str = None,
        style: StyleFlag = None,
    ) -> DataWrapper:
        """Add a categorie of data points."""
        pass


class HumanDataWrapper(DataWrapper):
    """Contains structured data, that can be retrieved later."""

    def __init__(self, dic: dict[Any, Any], style: StyleFlag = None) -> None:
        self._data: dict[Any, tuple[Any, str | None, StyleFlag | None]] = {}
        for k, v in dic.items():
            if isinstance(v, Dict):
                self._data[k] = (HumanDataWrapper(v, style), None, style)
            else:
                self._data[k] = (v, None, style)

    @property
    def data(self) -> dict[Any, Any]:
        """Get the structured data."""
        return self._data

    def add_point(self, key, value, name: str = None, style: StyleFlag = None) -> None:
        """Add a single data point."""
        self._data[key] = (str(value), name, style)

    def add_categorie(
        self,
        key,
        data: dict[Any, Any] = None,
        name: str = None,
        style: StyleFlag = None,
        cnt_style: StyleFlag = None,
    ) -> DataWrapper:
        """Add a categorie to the data set."""
        data = data or {}
        wrapper = HumanDataWrapper(data, cnt_style)
        self._data[key] = (wrapper, name, style)
        return wrapper


class JsonDataWrapper(DataWrapper):
    """Contains structured data, that can be retrieved later."""

    def __init__(self, dic: dict[Any, Any], style: StyleFlag = None) -> None:
        self._data: dict[Any, Any] = dic

    @property
    def data(self) -> dict[Any, Any]:
        """Get the structured data."""
        return self._data

    def add_point(self, key, value, name: str = None, style: StyleFlag = None) -> None:
        """Add a single data point."""
        self._data[key] = str(value)

    def add_categorie(
        self,
        key,
        data: dict[Any, Any] = None,
        name: str = None,
        style: StyleFlag = None,
    ) -> DataWrapper:
        """Add a categorie to the data set."""
        data = data or dict()
        self._data[key] = data
        return JsonDataWrapper(data)


class Messenger(ABC):
    """
    Abstract class of a messenger.

    Implemented by
    * :class:`HumanMessenger`
    * :class:`JsonMessenger`
    """

    @property
    @abstractmethod
    def data_wrapper(self) -> DataWrapper:
        """Get the data wrapper."""
        pass

    @abstractmethod
    def prog(self, message: str):
        """Print a progress message."""
        pass

    @abstractmethod
    def err(self, err_message: str, fatal: bool):
        """Print an error message."""
        pass

    @abstractmethod
    def print_data(self):
        """Print all data inside the data wrapper."""
        pass


class HumanMessenger(Messenger):
    """Prints data in human readable format."""

    def __init__(self) -> None:
        self._data_wraper = HumanDataWrapper(dict())

    @staticmethod
    def __nameify(key: Any):
        return str(key).capitalize().replace("_", " ")

    @classmethod
    def __print_data(cls, data_wrapper: HumanDataWrapper, padding=0):
        lines = []
        max_len = 0
        for key, (val, name, style) in data_wrapper.data.items():
            line = (name or cls.__nameify(key), val, style or StyleFlag.NONE)
            if max_len < len(line[0]):
                max_len = len(line[0])
            lines.append(line)

        max_len += 3
        for name, value, style in lines:
            color = (
                "green"
                if style & StyleFlag.GREEN
                else "red"
                if style & StyleFlag.RED
                else None
            )
            bold = style & StyleFlag.BOLD
            if isinstance(value, HumanDataWrapper):
                if bold:
                    click.echo(
                        "\n"
                        + "\t" * (padding)
                        + click.style("== " + name + " ==", fg=color, bold=True)
                    )
                    cls.__print_data(value, padding)
                else:
                    click.echo("\t" * padding + click.style(name + ":", fg=color))
                    cls.__print_data(value, padding + 1)
                continue
            name += ":"
            click.echo(
                "\t" * padding
                + click.style(
                    name.ljust(max_len, " ") + str(value), fg=color, bold=bold
                )
            )

    @property
    def data_wrapper(self) -> DataWrapper:
        """Get the data wrapper."""
        return self._data_wraper

    def prog(self, message):
        """Print a progress message."""
        click.echo(message)

    def err(self, err_message: str, fatal: bool):
        """Print an error message. If error is fatal a goodbye message is printed."""
        click.echo(click.style(err_message, fg="red"))
        if fatal:
            click.echo(click.style("Exiting...", fg="red"))

    def print_data(self):
        """Print the data in the data wrapper in a human readable form."""
        HumanMessenger.__print_data(self._data_wraper)
        click.echo()


class JsonMessenger(Messenger):
    """Prints data in JSON format."""

    def __init__(self, whitespace) -> None:
        self._data_wraper = JsonDataWrapper(dict())
        self._whitespace = whitespace

    @property
    def data_wrapper(self) -> DataWrapper:
        """Get the data wrapper."""
        return self._data_wraper

    def prog(self, message):
        """Log a progress message."""
        _LOGGER.debug(message)

    def err(self, err_message: str, fatal: bool):
        """Log an error. If fatal, the error is additionally added to the standard output."""
        _LOGGER.debug(err_message)
        if fatal:
            self.data_wrapper.add_point("error", err_message)
            self.print_data()

    def print_data(self):
        """Print all data inside the data wrapper in JSON format."""
        if self._whitespace:
            click.echo(json.dumps(self._data_wraper.data, indent=4))
        else:
            click.echo(json.dumps(self._data_wraper.data, separators=(",", ":")))
