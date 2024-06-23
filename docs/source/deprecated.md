# 0.7 API changes

This page contains information about the major API changes in 0.7.

The previous API reference can be found below.

## Restructuring the library

This is the largest refactoring of the library and there are changes in all parts of the library.
Other than the three breaking changes below, all changes are backwards compatible, and you will get a deprecation warning with instructions to help porting your code over.

* The library has now been restructured into `iot` and `smart` packages to contain the respective protocol (command set) implementations. The old `Smart{Plug,Bulb,Lightstrip}` that do not require authentication are now accessible through `kasa.iot` package.
* Exception classes are renamed
* Using .connect() or discover() is the preferred way to construct device instances rather than initiating constructors on a device.

### Breaking changes

* `features()` now returns a dict of `(identifier, feature)` instead of barely used set of strings.
* The `supported_modules` attribute is removed from the device class.
* `state_information` returns information based on features. If you leveraged this property, you may need to adjust your keys.

## Module support for SMART devices

This release introduces modules to SMART devices (i.e., devices that require authentication, previously supported using the "tapo" package which has now been renamed to "smart") and uses the device-reported capabilities to initialize the modules supported by the device.
This allows us to support previously unknown devices for known and implemented features,
and makes it easy to add support for new features and device types in the future.

This inital release adds 26 modules to support a variety of features, including:
* Basic controls for various device (like color temperature, brightness, etc.)
* Light effects & presets
* Control LEDs
* Fan controls
* Thermostat controls
* Handling of firmware updates
* Some hub controls (like playing alarms, )

## Introspectable device features

The library now offers a generic way to access device features ("features"), making it possible to create interfaces without knowledge of the module/feature specific APIs.
We use this information to construct our cli tool status output, and you can use `kasa feature` to read and control them.

The upcoming homeassistant integration rewrite will also use these interfaces to provide access to features that were not easily available to homeassistant users, and simplifies extending the support for more devices and features in the future.

## Deprecated API Reference

```{currentmodule} kasa
```
The page contains the documentation for the deprecated library API that only works with the older kasa devices.

If you want to continue to use the old API for older devices,
you can use the classes in the `iot` module to avoid deprecation warnings.

```py
from kasa.iot import IotDevice, IotBulb, IotPlug, IotDimmer, IotStrip, IotLightStrip
```


```{toctree}
:maxdepth: 2

smartdevice
smartbulb
smartplug
smartdimmer
smartstrip
smartlightstrip
```
