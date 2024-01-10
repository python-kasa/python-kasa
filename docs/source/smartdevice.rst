.. py:module:: kasa

Common API
==========

.. contents:: Contents
   :local:

SmartDevice class
*****************

The basic functionalities of all supported devices are accessible using the common :class:`SmartDevice` base class.

The property accesses use the data obtained before by awaiting :func:`SmartDevice.update()`.
The values are cached until the next update call. In practice this means that property accesses do no I/O and are dependent, while I/O producing methods need to be awaited.
See :ref:`library_design` for more detailed information.

.. note::
    The device instances share the communication socket in background to optimize I/O accesses.
    This means that you need to use the same event loop for subsequent requests.
    The library gives a warning ("Detected protocol reuse between different event loop") to hint if you are accessing the device incorrectly.

Methods changing the state of the device do not invalidate the cache (i.e., there is no implicit :func:`SmartDevice.update()` call made by the library).
You can assume that the operation has succeeded if no exception is raised.
These methods will return the device response, which can be useful for some use cases.

Errors are raised as :class:`SmartDeviceException` instances for the library user to handle.

Simple example script showing some functionality for legacy devices:

.. code-block:: python

    import asyncio
    from kasa import SmartPlug

    async def main():
        p = SmartPlug("127.0.0.1")

        await p.update()  # Request the update
        print(p.alias)  # Print out the alias
        print(p.emeter_realtime)  # Print out current emeter status

        await p.turn_off()  # Turn the device off

    if __name__ == "__main__":
        asyncio.run(main())

If you are connecting to a newer KASA or TAPO device you can get the device via discovery or
connect directly with :class:`DeviceConfig`:

.. code-block:: python

    import asyncio
    from kasa import Discover, Credentials

    async def main():
        device = await Discover.discover_single(
            "127.0.0.1",
            credentials=Credentials("myusername", "mypassword"),
            discovery_timeout=10
        )

        config = device.config # DeviceConfig.to_dict() can be used to store for later

        # To connect directly later without discovery

        later_device = await SmartDevice.connect(config=config)

        await later_device.update()

        print(later_device.alias)  # Print out the alias

If you want to perform updates in a loop, you need to make sure that the device accesses are done in the same event loop:

.. code-block:: python

    import asyncio
    from kasa import SmartPlug

    async def main():
        dev = SmartPlug("127.0.0.1")  # We create the instance inside the main loop
        while True:
            await dev.update()  # Request an update
            print(dev.emeter_realtime)
            await asyncio.sleep(0.5)  # Sleep some time between updates

    if __name__ == "__main__":
        asyncio.run(main())


Refer to device type specific classes for more examples:
:class:`SmartPlug`, :class:`SmartBulb`, :class:`SmartStrip`,
:class:`SmartDimmer`, :class:`SmartLightStrip`.

DeviceConfig class
******************

The :class:`DeviceConfig` class can be used to initialise devices with parameters to allow them to be connected to without using
discovery.
This is required for newer KASA and TAPO devices that use different protocols for communication and will not respond
on port 9999 but instead use different encryption protocols over http port 80.
Currently there are three known types of encryption for TP-Link devices and two different protocols.
Devices with automatic firmware updates enabled may update to newer versions of the encryption without separate notice,
so discovery can be helpful to determine the correct config.

To connect directly pass a :class:`DeviceConfig` object to :meth:`SmartDevice.connect()`.

A :class:`DeviceConfig` can be constucted manually if you know the :attr:`DeviceConfig.connection_type` values for the device or
alternatively the config can be retrieved from :attr:`SmartDevice.config` post discovery and then re-used.

Energy Consumption and Usage Statistics
***************************************

.. note::
    In order to use the helper methods to calculate the statistics correctly, your devices need to have correct time set.
    The devices use NTP and public servers from `NTP Pool Project <https://www.ntppool.org/>`_ to synchronize their time.

Energy Consumption
~~~~~~~~~~~~~~~~~~

The availability of energy consumption sensors depend on the device.
While most of the bulbs support it, only specific switches (e.g., HS110) or strips (e.g., HS300) support it.
You can use :attr:`~SmartDevice.has_emeter` to check for the availability.


Usage statistics
~~~~~~~~~~~~~~~~

You can use :attr:`~SmartDevice.on_since` to query for the time the device has been turned on.
Some devices also support reporting the usage statistics on daily or monthly basis.
You can access this information using through the usage module (:class:`kasa.modules.Usage`):

.. code-block:: python

    dev = SmartPlug("127.0.0.1")
    usage = dev.modules["usage"]
    print(f"Minutes on this month: {usage.usage_this_month}")
    print(f"Minutes on today: {usage.usage_today}")


API documentation
*****************

.. autoclass:: SmartDevice
    :members:
    :undoc-members:

.. autoclass:: DeviceConfig
    :members:
    :inherited-members:
    :undoc-members:
    :member-order: bysource

.. autoclass:: Credentials
    :members:
    :undoc-members:

.. autoclass:: SmartDeviceException
    :members:
    :undoc-members:

.. autoclass:: AuthenticationException
    :members:
    :undoc-members:

.. autoclass:: UnsupportedDeviceException
    :members:
    :undoc-members:
