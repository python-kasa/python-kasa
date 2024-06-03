
# Topics

```{contents} Contents
   :local:
```

These topics aim to provide some details on the design and internals of this library.
You might be interested in this if you want to improve this library,
or if you are just looking to access some information that is not currently exposed.

(topics-initialization)=
## Initialization

Use {func}`~kasa.Discover.discover` to perform udp-based broadcast discovery on the network.
This will return you a list of device instances based on the discovery replies.

If the device's host is already known, you can use to construct a device instance with
{meth}`~kasa.Device.connect()`.

The {meth}`~kasa.Device.connect()` also enables support for connecting to new
KASA SMART protocol and TAPO devices directly using the parameter {class}`~kasa.DeviceConfig`.
Simply serialize the {attr}`~kasa.Device.config` property via {meth}`~kasa.DeviceConfig.to_dict()`
and then deserialize it later with {func}`~kasa.DeviceConfig.from_dict()`
and then pass it into {meth}`~kasa.Device.connect()`.


(topics-discovery)=
## Discovery

Discovery works by sending broadcast UDP packets to two known TP-link discovery ports, 9999 and 20002.
Port 9999 is used for legacy devices that do not use strong encryption and 20002 is for newer devices that use different
levels of encryption.
If a device uses port 20002 for discovery you will obtain some basic information from the device via discovery, but you
will need to await {func}`Device.update() <kasa.Device.update()>` to get full device information.
Credentials will most likely be required for port 20002 devices although if the device has never been connected to the tplink
cloud it may work without credentials.

To query or update the device requires authentication via {class}`Credentials <kasa.Credentials>` and if this is invalid or not provided it
will raise an {class}`AuthenticationException <kasa.AuthenticationException>`.

If discovery encounters an unsupported device when calling via {meth}`Discover.discover_single() <kasa.Discover.discover_single>`
it will raise a {class}`UnsupportedDeviceException  <kasa.UnsupportedDeviceException>`.
If discovery encounters a device when calling {func}`Discover.discover() <kasa.Discover.discover>`,
you can provide a callback to the ``on_unsupported`` parameter
to handle these.

(topics-deviceconfig)=
## DeviceConfig

The {class}`DeviceConfig` class can be used to initialise devices with parameters to allow them to be connected to without using
discovery.
This is required for newer KASA and TAPO devices that use different protocols for communication and will not respond
on port 9999 but instead use different encryption protocols over http port 80.
Currently there are three known types of encryption for TP-Link devices and two different protocols.
Devices with automatic firmware updates enabled may update to newer versions of the encryption without separate notice,
so discovery can be helpful to determine the correct config.

To connect directly pass a {class}`DeviceConfig` object to {meth}`Device.connect()`.

A {class}`DeviceConfig` can be constucted manually if you know the {attr}`DeviceConfig.connection_type` values for the device or
alternatively the config can be retrieved from {attr}`Device.config` post discovery and then re-used.

(topics-update-cycle)=
## Update Cycle

When {meth}`~kasa.Device.update()` is called,
the library constructs a query to send to the device based on :ref:`supported modules <modules>`.
Internally, each module defines {meth}`~kasa.modules.Module.query()` to describe what they want query during the update.

The returned data is cached internally to avoid I/O on property accesses.
All properties defined both in the device class and in the module classes follow this principle.

While the properties are designed to provide a nice API to use for common use cases,
you may sometimes want to access the raw, cached data as returned by the device.
This can be done using the {attr}`~kasa.Device.internal_state` property.


(topics-modules-and-features)=
## Modules and Features

The functionality provided by all {class}`~kasa.Device` instances is (mostly) done inside separate modules.
While the individual device-type specific classes provide an easy access for the most import features,
you can also access individual modules through {attr}`kasa.Device.modules`.
You can get the list of supported modules for a given device instance using {attr}`~kasa.Device.supported_modules`.

```{note}
If you only need some module-specific information,
you can call the wanted method on the module to avoid using {meth}`~kasa.Device.update`.
```

(topics-protocols-and-transports)=
## Protocols and Transports

The library supports two different TP-Link protocols, ``IOT`` and ``SMART``.
``IOT`` is the original Kasa protocol and ``SMART`` is the newer protocol supported by TAPO devices and newer KASA devices.
The original protocol has a ``target``, ``command``, ``args`` interface whereas the new protocol uses a different set of
commands and has a ``method``, ``parameters`` interface.
Confusingly TP-Link originally called the Kasa line "Kasa Smart" and hence this library used "Smart" in a lot of the
module and class names but actually they were built to work with the ``IOT`` protocol.

In 2021 TP-Link started updating the underlying communication transport used by Kasa devices to make them more secure.
It switched from a TCP connection with static XOR type of encryption to a transport called ``KLAP`` which communicates
over http and uses handshakes to negotiate a dynamic encryption cipher.
This automatic update was put on hold and only seemed to affect UK HS100 models.

In 2023 TP-Link started updating the underlying communication transport used by Tapo devices to make them more secure.
It switched from AES encryption via public key exchange to use ``KLAP`` encryption and negotiation due to concerns
around impersonation with AES.
The encryption cipher is the same as for Kasa KLAP but the handshake seeds are slightly different.
Also in 2023 TP-Link started releasing newer Kasa branded devices using the ``SMART`` protocol.
This appears to be driven by hardware version rather than firmware.


In order to support these different configurations the library migrated from a single protocol class ``TPLinkSmartHomeProtocol``
to support pluggable transports and protocols.
The classes providing this functionality are:

- {class}`BaseProtocol <kasa.protocol.BaseProtocol>`
- {class}`IotProtocol <kasa.iotprotocol.IotProtocol>`
- {class}`SmartProtocol <kasa.smartprotocol.SmartProtocol>`

- {class}`BaseTransport <kasa.protocol.BaseTransport>`
- {class}`XorTransport <kasa.xortransport.XorTransport>`
- {class}`AesTransport <kasa.aestransport.AesTransport>`
- {class}`KlapTransport <kasa.klaptransport.KlapTransport>`
- {class}`KlapTransportV2 <kasa.klaptransport.KlapTransportV2>`

(topics-errors-and-exceptions)=
## Errors and Exceptions

The base exception for all library errors is {class}`KasaException <kasa.exceptions.KasaException>`.

- If the device returns an error the library raises a {class}`DeviceError <kasa.exceptions.DeviceError>` which will usually contain an ``error_code`` with the detail.
- If the device fails to authenticate the library raises an {class}`AuthenticationError <kasa.exceptions.AuthenticationError>` which is derived
  from {class}`DeviceError <kasa.exceptions.DeviceError>` and could contain an ``error_code`` depending on the type of failure.
- If the library encounters and unsupported deviceit raises an {class}`UnsupportedDeviceError <kasa.exceptions.UnsupportedDeviceError>`.
- If the device fails to respond within a timeout the library raises a {class}`TimeoutError <kasa.exceptions.TimeoutError>`.
- All other failures will raise the base {class}`KasaException <kasa.exceptions.KasaException>` class.

<!-- Commenting out this section keeps git seeing the change as a rename.

API documentation for modules and features
******************************************

.. autoclass:: kasa.Module
    :noindex:
    :members:
    :inherited-members:
    :undoc-members:

.. automodule:: kasa.interfaces
    :noindex:
    :members:
    :inherited-members:
    :undoc-members:

.. autoclass:: kasa.Feature
    :noindex:
    :members:
    :inherited-members:
    :undoc-members:



API documentation for protocols and transports
**********************************************

.. autoclass:: kasa.protocol.BaseProtocol
    :members:
    :inherited-members:
    :undoc-members:

.. autoclass:: kasa.iotprotocol.IotProtocol
    :members:
    :inherited-members:
    :undoc-members:

.. autoclass:: kasa.smartprotocol.SmartProtocol
    :members:
    :inherited-members:
    :undoc-members:

.. autoclass:: kasa.protocol.BaseTransport
    :members:
    :inherited-members:
    :undoc-members:

.. autoclass:: kasa.xortransport.XorTransport
    :members:
    :inherited-members:
    :undoc-members:

.. autoclass:: kasa.klaptransport.KlapTransport
    :members:
    :inherited-members:
    :undoc-members:

.. autoclass:: kasa.klaptransport.KlapTransportV2
    :members:
    :inherited-members:
    :undoc-members:

.. autoclass:: kasa.aestransport.AesTransport
    :members:
    :inherited-members:
    :undoc-members:

API documentation for errors and exceptions
*******************************************

.. autoclass:: kasa.exceptions.KasaException
    :members:
    :undoc-members:

.. autoclass:: kasa.exceptions.DeviceError
    :members:
    :undoc-members:

.. autoclass:: kasa.exceptions.AuthenticationError
    :members:
    :undoc-members:

.. autoclass:: kasa.exceptions.UnsupportedDeviceError
    :members:
    :undoc-members:

.. autoclass:: kasa.exceptions.TimeoutError
    :members:
    :undoc-members:

-->
