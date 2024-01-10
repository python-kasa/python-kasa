.. py:module:: kasa.discover

Discovering devices
===================

.. contents:: Contents
   :local:

Discovery
*********

Discovery works by sending broadcast UDP packets to two known TP-link discovery ports, 9999 and 20002.
Port 9999 is used for legacy devices that do not use strong encryption and 20002 is for newer devices that use different
levels of encryption.
If a device uses port 20002 for discovery you will obtain some basic information from the device via discovery, but you
will need to await :func:`SmartDevice.update() <kasa.SmartDevice.update()>` to get full device information.
Credentials will most likely be required for port 20002 devices although if the device has never been connected to the tplink
cloud it may work without credentials.

To query or update the device requires authentication via :class:`Credentials <kasa.Credentials>` and if this is invalid or not provided it
will raise an :class:`AuthenticationException <kasa.AuthenticationException>`.

If discovery encounters an unsupported device when calling via :meth:`Discover.discover_single() <kasa.Discover.discover_single>`
it will raise a :class:`UnsupportedDeviceException  <kasa.UnsupportedDeviceException>`.
If discovery encounters a device when calling :meth:`Discover.discover() <kasa.Discover.discover>`,
you can provide a callback to the ``on_unsupported`` parameter
to handle these.

Example:

.. code-block:: python

    import asyncio
    from kasa import Discover, Credentials

    async def main():
        device = await Discover.discover_single(
            "127.0.0.1",
            credentials=Credentials("myusername", "mypassword"),
            discovery_timeout=10
        )

        await device.update()  # Request the update
        print(device.alias)  # Print out the alias

        devices = await Discover.discover(
            credentials=Credentials("myusername", "mypassword"),
            discovery_timeout=10
        )
        for ip, device in devices.items():
            await device.update()
            print(device.alias)

    if __name__ == "__main__":
        asyncio.run(main())

API documentation
*****************

.. autoclass:: kasa.Discover
    :members:
    :undoc-members:
