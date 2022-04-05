.. py:module:: kasa

Common API
======================

The basic functionalities of all supported devices are accessible using the common :class:`SmartDevice` base class.

The property accesses use the data obtained before by awaiting :func:`SmartDevice.update()`.
The values are cached until the next update call. In practice this means that property accesses do no I/O and are dependent, while I/O producing methods need to be awaited.

.. note::
    The device instances share the communication socket in background to optimize I/O accesses.
    This means that you need to use the same event loop for subsequent requests.
    The library gives a warning ("Detected protocol reuse between different event loop") to hint if you are accessing the device incorrectly.

Methods changing the state of the device do not invalidate the cache (i.e., there is no implicit :func:`SmartDevice.update()` call made by the library).
You can assume that the operation has succeeded if no exception is raised.
These methods will return the device response, which can be useful for some use cases.

Errors are raised as :class:`SmartDeviceException` instances for the library user to handle.

Simple example script showing some functionality:

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

* :class:`SmartPlug`
* :class:`SmartBulb`
* :class:`SmartStrip`
* :class:`SmartDimmer`
* :class:`SmartLightStrip`


API documentation
~~~~~~~~~~~~~~~~~

.. autoclass:: SmartDevice
    :members:
    :undoc-members:
