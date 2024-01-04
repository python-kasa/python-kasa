Command-line usage
==================

The package is shipped with a console tool named ``kasa``, refer to ``kasa --help`` for detailed usage.
The device to which the commands are sent is chosen by ``KASA_HOST`` environment variable or passing ``--host <address>`` as an option.
To see what is being sent to and received from the device, specify option ``--debug``.

To avoid discovering the devices when executing commands its type can be passed as an option (e.g., ``--type plug`` for plugs, ``--type bulb`` for bulbs, ..).
If no type is manually given, its type will be discovered automatically which causes a short delay.

If no command is given, the ``state`` command will be executed to query the device state.

.. note::

    Some commands (such as reading energy meter values, changing bulb settings, or accessing individual sockets on smart strips) additional parameters are required,
    which you can find by adding ``--help`` after the command, e.g. ``kasa --type emeter --help`` or ``kasa --type hsv --help``.
    Refer to the device type specific documentation for more details.

Discovery
*********

The tool can automatically discover supported devices using a broadcast-based discovery protocol.
This works by sending an UDP datagram on ports 9999 and 20002 to the broadcast address (defaulting to ``255.255.255.255``).

Newer devices that respond on port 20002 will most likely require TP-Link cloud credentials to be passed or they will report as having failed authentication.
Use ``--username`` and ``--password`` options to specify credentials.

On multihomed systems, you can use ``--target`` option to specify the broadcast target.
For example, if your devices reside in network ``10.0.0.0/24`` you can use ``kasa --target 10.0.0.255 discover`` to discover them.

.. note::

    When no command is specified when invoking ``kasa``, a discovery is performed and the ``state`` command is executed on each discovered device.

Provisioning
************

You can provision your device without any extra apps by using the ``kasa wifi`` command:

1. If the device is unprovisioned, connect to its open network
2. Use ``kasa discover`` (or check the routes) to locate the IP address of the device (likely 192.168.0.1, if unprovisioned)
3. Scan for available networks using ``kasa --host 192.168.0.1 wifi scan`` see which networks are visible to the device
4. Join/change the network using ``kasa --host 192.168.0.1 wifi join <network to join>``

As with all other commands, you can also pass ``--help`` to both ``join`` and ``scan`` commands to see the available options.

``kasa --help``
***************

.. program-output:: kasa --help
