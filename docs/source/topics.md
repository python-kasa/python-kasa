
# Topics

```{contents} Contents
   :local:
```

These topics aim to provide some details on the design and internals of this library.
You might be interested in this if you want to improve this library,
or if you are just looking to access some information that is not currently exposed.

(topics-initialization)=
## Initialization

Use {func}`~kasa.Discover.discover` to perform broadcast discovery on the network.
This returns a dictionary of device instances keyed by IP address.

If the device's host is known, use {meth}`~kasa.Device.connect` to connect
directly. Supplying a {class}`~kasa.DeviceConfig` avoids probing for the
connection settings. A config obtained from {attr}`~kasa.Device.config` can be
serialized with {meth}`~kasa.DeviceConfig.to_dict` and restored with
{meth}`~kasa.DeviceConfig.from_dict`.


(topics-discovery)=
## Discovery

Discovery queries the known UDP and TDP discovery endpoints. UDP uses port 9999,
while TDP uses ports 20002 and 20004 for different device populations. If the
same host responds through UDP and TDP, the TDP response is used.

Each response is normalized into connection and discovery information before it
is passed to the device factory. The factory selects the protocol, transport,
and concrete device class. When a discovery response identifies only a broad
device family, the factory can query the device for the information needed to
select the concrete class.

The discovery API initializes each device with the information available in its
response, but it does not perform a full {meth}`~kasa.Device.update`. Call
``update()`` before using properties that are not available from discovery.
Credentials are generally required for TDP devices.

Responses that cannot be represented by a {class}`~kasa.Device` can be reported
through the ``on_unsupported`` and ``on_authentication_error`` callbacks.
Without the corresponding callback, {meth}`~kasa.Discover.discover_single`
raises the error for the requested device.

(topics-deviceconfig)=
## DeviceConfig

The {class}`~kasa.DeviceConfig` class contains the settings needed to connect to
a device without discovery. Pass it to {meth}`~kasa.Device.connect` to create
and initialize the device.

The safest way to obtain a config is from {attr}`~kasa.Device.config` after
discovery. It can be serialized with {meth}`~kasa.DeviceConfig.to_dict` and
reused with {meth}`~kasa.DeviceConfig.from_dict`. A config can also be created
manually when the exact connection parameters are known.

The ``login_version`` and ``klap_version`` connection parameters are
independent. ``klap_version`` selects the advertised IOT KLAP handshake version;
the encryption type remains {attr}`~kasa.DeviceEncryptionType.Klap`.

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
While the device class provides easy access for most device related attributes,
for components like `light` and `camera` you can access the module through {attr}`kasa.Device.modules`.
The module names are handily available as constants on {class}`~kasa.Module` and will return type aware values from the collection.

Features represent individual pieces of functionality within a module like brightness, hsv and temperature within a light module.
They allow for instrospection and can be accessed through {attr}`kasa.Device.features`.
Attributes can be accessed via a `Feature` or a module attribute depending on the use case.
Modules tend to provide richer functionality but using the features does not require an understanding of the module api.

:::{include} featureattributes.md
:::

(topics-protocols-and-transports)=
## Protocols and Transports

The library distinguishes three TP-Link protocol families: ``IOT``, ``SMART``, and ``SMARTCAM``.
``IOT`` is used by the original Kasa devices, ``SMART`` by Tapo and newer Kasa devices, and ``SMARTCAM`` by cameras and some hubs and doorbells.
The IOT protocol has a ``target``, ``command``, ``args`` interface, whereas SMART and SMARTCAM use method-based requests.
Confusingly TP-Link originally called the Kasa line "Kasa Smart" and hence this library used "Smart" in a lot of the
module and class names but actually they were built to work with the ``IOT`` protocol.

In 2021 TP-Link started updating the underlying communication transport used by Kasa devices to make them more secure.
It switched from a TCP connection with static XOR type of encryption to a transport called ``KLAP`` which communicates
over HTTP and uses handshakes to negotiate a dynamic encryption cipher.
IOT devices can use either KLAP handshake version without changing
their device family or concrete device class.

In 2023 TP-Link started updating the underlying communication transport used by Tapo devices to make them more secure.
It switched from AES encryption via public key exchange to use ``KLAP`` encryption and negotiation due to concerns
around impersonation with AES.
The encryption cipher is the same as for Kasa KLAP but the handshake seeds are slightly different.
Also in 2023 TP-Link started releasing newer Kasa branded devices using the ``SMART`` protocol.
This appears to be driven by hardware version rather than firmware.


In order to support these different configurations the library migrated from a single protocol class ``TPLinkSmartHomeProtocol``
to support pluggable transports and protocols.
The classes providing this functionality are:

- {class}`BaseProtocol <kasa.protocols.BaseProtocol>`
- {class}`IotProtocol <kasa.protocols.IotProtocol>`
- {class}`SmartProtocol <kasa.protocols.SmartProtocol>`
- {class}`SmartCamProtocol <kasa.protocols.SmartCamProtocol>`

- {class}`BaseTransport <kasa.transports.BaseTransport>`
- {class}`XorTransport <kasa.transports.XorTransport>`
- {class}`AesTransport <kasa.transports.AesTransport>`
- {class}`KlapTransport <kasa.transports.KlapTransport>`
- {class}`KlapTransportV2 <kasa.transports.KlapTransportV2>`
- {class}`SslTransport <kasa.transports.SslTransport>`
- {class}`SslAesTransport <kasa.transports.SslAesTransport>`
- {class}`LinkieTransportV2 <kasa.transports.LinkieTransportV2>`

(topics-errors-and-exceptions)=
## Errors and Exceptions

The base exception for all library errors is {class}`KasaException <kasa.exceptions.KasaException>`.

- If the device returns an error the library raises a {class}`DeviceError <kasa.exceptions.DeviceError>` which will usually contain an ``error_code`` with the detail.
- If the device fails to authenticate the library raises an {class}`AuthenticationError <kasa.exceptions.AuthenticationError>` which is derived
  from {class}`DeviceError <kasa.exceptions.DeviceError>` and could contain an ``error_code`` depending on the type of failure.
- If authentication fails for a device discovered with an unsupported onboarding source, the library raises {class}`UnsupportedAuthenticationError <kasa.exceptions.UnsupportedAuthenticationError>`, which derives from both {class}`AuthenticationError <kasa.exceptions.AuthenticationError>` and {class}`UnsupportedDeviceError <kasa.exceptions.UnsupportedDeviceError>`.
- If the library encounters an unsupported device it raises an {class}`UnsupportedDeviceError <kasa.exceptions.UnsupportedDeviceError>`.
- If the device fails to respond within a timeout the library raises a {class}`TimeoutError <kasa.exceptions.TimeoutError>`.
- All other failures will raise the base {class}`KasaException <kasa.exceptions.KasaException>` class.
