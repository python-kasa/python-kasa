.. py:module:: kasa.modules


.. _library_design:

Library Design & Modules
========================

This page aims to provide some details on the design and internals of this library.
You might be interested in this if you want to improve this library,
or if you are just looking to access some information that is not currently exposed.

.. contents:: Contents
   :local:

.. _initialization:

Initialization
**************

Use :func:`~kasa.Discover.discover` to perform udp-based broadcast discovery on the network.
This will return you a list of device instances based on the discovery replies.

If the device's host is already known, you can use to construct a device instance with
:meth:`~kasa.SmartDevice.connect()`.

The :meth:`~kasa.SmartDevice.connect()` also enables support for connecting to new
KASA SMART protocol and TAPO devices directly using the parameter :class:`~kasa.DeviceConfig`.
Simply serialize the :attr:`~kasa.SmartDevice.config` property via :meth:`~kasa.DeviceConfig.to_dict()`
and then deserialize it later with :func:`~kasa.DeviceConfig.from_dict()`
and then pass it into :meth:`~kasa.SmartDevice.connect()`.


.. _update_cycle:

Update Cycle
************

When :meth:`~kasa.SmartDevice.update()` is called,
the library constructs a query to send to the device based on :ref:`supported modules <modules>`.
Internally, each module defines :meth:`~kasa.modules.Module.query()` to describe what they want query during the update.

The returned data is cached internally to avoid I/O on property accesses.
All properties defined both in the device class and in the module classes follow this principle.

While the properties are designed to provide a nice API to use for common use cases,
you may sometimes want to access the raw, cached data as returned by the device.
This can be done using the :attr:`~kasa.SmartDevice.internal_state` property.


.. _modules:

Modules
*******

The functionality provided by all :class:`~kasa.SmartDevice` instances is (mostly) done inside separate modules.
While the individual device-type specific classes provide an easy access for the most import features,
you can also access individual modules through :attr:`kasa.SmartDevice.modules`.
You can get the list of supported modules for a given device instance using :attr:`~kasa.SmartDevice.supported_modules`.

.. note::

    If you only need some module-specific information,
    you can call the wanted method on the module to avoid using :meth:`~kasa.SmartDevice.update`.

Protocols and Transports
************************

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

- :class:`BaseProtocol <kasa.protocol.BaseProtocol>`
- :class:`IotProtocol <kasa.iotprotocol.IotProtocol>`
- :class:`SmartProtocol <kasa.smartprotocol.SmartProtocol>`

- :class:`BaseTransport <kasa.protocol.BaseTransport>`
- :class:`XorTransport <kasa.xortransport.XorTransport>`
- :class:`AesTransport <kasa.aestransport.AesTransport>`
- :class:`KlapTransport <kasa.klaptransport.KlapTransport>`
- :class:`KlapTransportV2 <kasa.klaptransport.KlapTransportV2>`


API documentation for modules
*****************************

.. automodule:: kasa.modules
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
