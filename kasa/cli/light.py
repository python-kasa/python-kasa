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
def light(dev) -> None:
    """Commands to control light settings."""


@light.command()
@click.argument("brightness", type=click.IntRange(0, 100), default=None, required=False)
@click.option("--transition", type=int, required=False)
@pass_dev_or_child
async def brightness(dev: Device, brightness: int, transition: int):
    """Get or set brightness."""
    if not (light := dev.modules.get(Module.Light)) or not light.has_feature(
        "brightness"
    ):
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
    if not (light := dev.modules.get(Module.Light)) or not (
        color_temp_feat := light.get_feature("color_temp")
    ):
        error("Device does not support color temperature")
        return

    if temperature is None:
        echo(f"Color temperature: {light.color_temp}")
        valid_temperature_range = color_temp_feat.range
        if valid_temperature_range != (0, 0):
            echo("(min: {}, max: {})".format(*valid_temperature_range))
        else:
            echo(
                "Temperature range unknown, please open a github issue"
                f" or a pull request for model '{dev.model}'"
            )
        return color_temp_feat.range
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
    if not (light := dev.modules.get(Module.Light)) or not light.has_feature("hsv"):
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
        error("Device does not support light presets")
        return

    for idx, preset in enumerate(light_preset.preset_states_list):
        echo(
            f"[{idx}] Hue: {preset.hue or '':3}  "
            f"Saturation: {preset.saturation or '':3}  "
            f"Brightness/Value: {preset.brightness or '':3}  "
            f"Temp: {preset.color_temp or '':4}"
        )

    return light_preset.preset_states_list


@presets.command(name="modify")
@click.argument("index", type=int)
@click.option("--brightness", type=int, required=False, default=None)
@click.option("--hue", type=int, required=False, default=None)
@click.option("--saturation", type=int, required=False, default=None)
@click.option("--temperature", type=int, required=False, default=None)
@pass_dev_or_child
async def presets_modify(dev: Device, index, brightness, hue, saturation, temperature):
    """Modify a preset."""
    if not (light_preset := dev.modules.get(Module.LightPreset)):
        error("Device does not support light presets")
        return

    max_index = len(light_preset.preset_states_list) - 1
    if index > len(light_preset.preset_states_list) - 1:
        error(f"Invalid index, must be between 0 and {max_index}")
        return

    if all([val is None for val in {brightness, hue, saturation, temperature}]):
        error("Need to supply at least one option to modify.")
        return

    # Preset names have `Not set`` as the first value
    preset_name = light_preset.preset_list[index + 1]
    preset = light_preset.preset_states_list[index]

    echo(f"Preset {preset_name} currently: {preset}")

    if brightness is not None and preset.brightness is not None:
        preset.brightness = brightness
    if hue is not None and preset.hue is not None:
        preset.hue = hue
    if saturation is not None and preset.saturation is not None:
        preset.saturation = saturation
    if temperature is not None and preset.temperature is not None:
        preset.color_temp = temperature

    echo(f"Updating preset {preset_name} to: {preset}")

    return await light_preset.save_preset(preset_name, preset)


@light.command()
@pass_dev_or_child
@click.option("--type", type=click.Choice(["soft", "hard"], case_sensitive=False))
@click.option("--last", is_flag=True)
@click.option("--preset", type=int)
async def turn_on_behavior(dev: Device, type, last, preset):
    """Modify bulb turn-on behavior."""
    if dev.device_type is not Device.Type.Bulb or not isinstance(dev, IotBulb):
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
