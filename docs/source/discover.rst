Discovering devices
===================

.. code-block::

    import asyncio
    from kasa import Discover

    devices = asyncio.run(Discover.discover())
    for addr, dev in devices.items():
        asyncio.run(dev.update())
        print(f"{addr} >> {dev}")


.. autoclass:: kasa.Discover
    :members:
    :undoc-members:
