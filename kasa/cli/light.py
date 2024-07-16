"""Module for cli light control commands."""

import asyncclick as click

from kasa import (
    Device,
    Module,
)
from kasa.iot import (
    IotBulb,
)

from .common import echo, error, pass_dev_or_child


@click.group()
@pass_dev_or_child
def light(dev):
    """Commands to control light settings."""


@light.command()
@click.argument("brightness", type=click.IntRange(0, 100), default=None, required=False)
@click.option("--transition", type=int, required=False)
@pass_dev_or_child
async def brightness(dev: Device, brightness: int, transition: int):
    """Get or set brightness."""
    if not (light := dev.modules.get(Module.Light)) or not light.is_dimmable:
        error("This device does not support brightness.")
        return

    if brightness is None:
        echo(f"Brightness: {light.brightness}")
        return light.brightness
    else:
        echo(f"Setting brightness to {brightness}")
        return await light.set_brightness(brightness, transition=transition)


@light.command()
@click.argument(
    "temperature", type=click.IntRange(2500, 9000), default=None, required=False
)
@click.option("--transition", type=int, required=False)
@pass_dev_or_child
async def temperature(dev: Device, temperature: int, transition: int):
    """Get or set color temperature."""
    if not (light := dev.modules.get(Module.Light)) or not light.is_variable_color_temp:
        error("Device does not support color temperature")
        return

    if temperature is None:
        echo(f"Color temperature: {light.color_temp}")
        valid_temperature_range = light.valid_temperature_range
        if valid_temperature_range != (0, 0):
            echo("(min: {}, max: {})".format(*valid_temperature_range))
        else:
            echo(
                "Temperature range unknown, please open a github issue"
                f" or a pull request for model '{dev.model}'"
            )
        return light.valid_temperature_range
    else:
        echo(f"Setting color temperature to {temperature}")
        return await light.set_color_temp(temperature, transition=transition)


@light.command()
@click.argument("effect", type=click.STRING, default=None, required=False)
@click.pass_context
@pass_dev_or_child
async def effect(dev: Device, ctx, effect):
    """Set an effect."""
    if not (light_effect := dev.modules.get(Module.LightEffect)):
        error("Device does not support effects")
        return
    if effect is None:
        echo(
            f"Light effect: {light_effect.effect}\n"
            + f"Available Effects: {light_effect.effect_list}"
        )
        return light_effect.effect

    if effect not in light_effect.effect_list:
        raise click.BadArgumentUsage(
            f"Effect must be one of: {light_effect.effect_list}", ctx
        )

    echo(f"Setting Effect: {effect}")
    return await light_effect.set_effect(effect)


@light.command()
@click.argument("h", type=click.IntRange(0, 360), default=None, required=False)
@click.argument("s", type=click.IntRange(0, 100), default=None, required=False)
@click.argument("v", type=click.IntRange(0, 100), default=None, required=False)
@click.option("--transition", type=int, required=False)
@click.pass_context
@pass_dev_or_child
async def hsv(dev: Device, ctx, h, s, v, transition):
    """Get or set color in HSV."""
    if not (light := dev.modules.get(Module.Light)) or not light.is_color:
        error("Device does not support colors")
        return

    if h is None and s is None and v is None:
        echo(f"Current HSV: {light.hsv}")
        return light.hsv
    elif s is None or v is None:
        raise click.BadArgumentUsage("Setting a color requires 3 values.", ctx)
    else:
        echo(f"Setting HSV: {h} {s} {v}")
        return await light.set_hsv(h, s, v, transition=transition)


@light.group(invoke_without_command=True)
@pass_dev_or_child
@click.pass_context
async def presets(ctx, dev):
    """List and modify bulb setting presets."""
    if ctx.invoked_subcommand is None:
        return await ctx.invoke(presets_list)


@presets.command(name="list")
@pass_dev_or_child
def presets_list(dev: Device):
    """List presets."""
    if not (light_preset := dev.modules.get(Module.LightPreset)):
        error("Presets not supported on device")
        return

    for preset in light_preset.preset_states_list:
        echo(preset)

    return light_preset.preset_states_list


@presets.command(name="modify")
@click.argument("index", type=int)
@click.option("--brightness", type=int)
@click.option("--hue", type=int)
@click.option("--saturation", type=int)
@click.option("--temperature", type=int)
@pass_dev_or_child
async def presets_modify(dev: Device, index, brightness, hue, saturation, temperature):
    """Modify a preset."""
    for preset in dev.presets:
        if preset.index == index:
            break
    else:
        error(f"No preset found for index {index}")
        return

    if brightness is not None:
        preset.brightness = brightness
    if hue is not None:
        preset.hue = hue
    if saturation is not None:
        preset.saturation = saturation
    if temperature is not None:
        preset.color_temp = temperature

    echo(f"Going to save preset: {preset}")

    return await dev.save_preset(preset)


@light.command()
@pass_dev_or_child
@click.option("--type", type=click.Choice(["soft", "hard"], case_sensitive=False))
@click.option("--last", is_flag=True)
@click.option("--preset", type=int)
async def turn_on_behavior(dev: Device, type, last, preset):
    """Modify bulb turn-on behavior."""
    if not dev.is_bulb or not isinstance(dev, IotBulb):
        error("Presets only supported on iot bulbs")
        return
    settings = await dev.get_turn_on_behavior()
    echo(f"Current turn on behavior: {settings}")

    # Return if we are not setting the value
    if not type and not last and not preset:
        return settings

    # If we are setting the value, the type has to be specified
    if (last or preset) and type is None:
        echo("To set the behavior, you need to define --type")
        return

    behavior = getattr(settings, type)

    if last:
        echo(f"Going to set {type} to last")
        behavior.preset = None
    elif preset is not None:
        echo(f"Going to set {type} to preset {preset}")
        behavior.preset = preset

    return await dev.set_turn_on_behavior(settings)
