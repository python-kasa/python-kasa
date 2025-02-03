"""Module for lazily instantiating sub modules.

Taken from the click help files.
"""

from __future__ import annotations

import importlib

import asyncclick as click


class LazyGroup(click.Group):
    """Lazy group class."""

    def __init__(self, *args, lazy_subcommands=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # lazy_subcommands is a map of the form:
        #
        #   {command-name} -> {module-name}.{command-object-name}
        #
        self.lazy_subcommands = lazy_subcommands or {}

    def list_commands(self, ctx):
        """List click commands."""
        base = super().list_commands(ctx)
        lazy = list(self.lazy_subcommands.keys())
        return lazy + base

    def get_command(self, ctx, cmd_name):
        """Get click command."""
        if cmd_name in self.lazy_subcommands:
            return self._lazy_load(cmd_name)
        return super().get_command(ctx, cmd_name)

    def format_commands(self, ctx, formatter) -> None:
        """Format the top level help output."""
        sections: dict[str, list] = {}
        for cmd, parent in self.lazy_subcommands.items():
            sections.setdefault(parent, [])
            cmd_obj = self.get_command(ctx, cmd)
            help = cmd_obj.get_short_help_str()
            sections[parent].append((cmd, help))
        for section in sections:
            if section:
                header = (
                    f"Common {section} commands (also available "
                    f"under the `{section}` subcommand)"
                )
            else:
                header = "Subcommands"
            with formatter.section(header):
                formatter.write_dl(sections[section])

    def _lazy_load(self, cmd_name):
        # lazily loading a command, first get the module name and attribute name
        if not (import_path := self.lazy_subcommands[cmd_name]):
            import_path = f".{cmd_name}.{cmd_name}"
        else:
            import_path = f".{import_path}.{cmd_name}"
        modname, cmd_object_name = import_path.rsplit(".", 1)
        # do the import
        mod = importlib.import_module(modname, package=__package__)
        # get the Command object from that module
        cmd_object = getattr(mod, cmd_object_name)
        # check the result to make debugging easier
        if not isinstance(cmd_object, click.BaseCommand):
            raise ValueError(
                f"Lazy loading of {cmd_name} failed by returning a non-command object"
            )
        return cmd_object
