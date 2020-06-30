Common API
======================

The basic functionalities of all supported devices are accessible using the common :class:`SmartDevice` base class.

The property accesses use the data obtained before by awaiting :func:`update()`.
The values are cached until the next update call. In practice this means that property accesses do no I/O and are dependent, while I/O producing methods need to be awaited.

Methods changing the state of the device do not invalidate the cache (i.e., there is no implicit `update()`).
You can assume that the operation has succeeded if no exception is raised.
These methods will return the device response, which can be useful for some use cases.

Errors are raised as :class:`SmartDeviceException` instances for the library user to handle.


.. autoclass:: kasa.SmartDevice
    :members:
    :undoc-members:
