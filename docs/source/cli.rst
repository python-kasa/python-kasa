Command-line usage
==================

The package is shipped with a console tool named ``kasa``, refer to ``kasa --help`` for detailed usage.
The device to which the commands are sent is chosen by ``KASA_HOST`` environment variable or passing ``--host <address>`` as an option.
To see what is being sent to and received from the device, specify option ``--debug``.

To avoid discovery when the connection details are known, pass ``--type`` for
one of the common connection types. For other connections, pass both
``-df``/``--device-family`` and ``-e``/``--encrypt-type``. Some devices also
require values for ``-lv``/``--login-version``, ``-kv``/``--klap-version``, or
``--https``.
These advanced options require ``--host`` and cannot be used with the
``discover`` command.

``-lv``/``--login-version`` and ``-kv``/``--klap-version`` are independent
connection settings and should only be supplied when they are known. Use
``kasa --host <address> discover config`` to show the connection configuration
advertised by the device. If no discovery response is received, the command
falls back to direct connection probing and identifies that fallback in its
output. A response that was received remains authoritative and is not replaced
by probing. Devices that require authentication can use ``--username`` and
``--password``, or ``--credentials-hash`` when an existing credential hash is
available.

If no command is given, the ``state`` command will be executed to query the device state.

.. note::

    Some commands (such as reading energy meter values, changing bulb settings, or accessing individual sockets on smart strips) additional parameters are required,
    which you can find by adding ``--help`` after the command, e.g. ``kasa --type emeter --help`` or ``kasa --type hsv --help``.
    Refer to the device type specific documentation for more details.

Discovery
*********

The tool can automatically discover supported devices using a broadcast-based discovery protocol.
This sends discovery queries to UDP port 9999 and TDP ports 20002 and 20004 at
the broadcast address, which defaults to ``255.255.255.255``. If a device
responds through both UDP and TDP, the TDP response is used. The global
``--port`` option changes the UDP discovery and device connection port; the
TDP discovery ports remain fixed.

Devices that respond using TDP will generally require TP-Link cloud credentials to be passed (unless they have never been connected
to the TP-Link cloud) or they will report as having failed authentication when trying to query the device.
Use ``--username`` and ``--password`` options to specify credentials.
These values can also be set as environment variables via ``KASA_USERNAME`` and ``KASA_PASSWORD``.

The default output and ``discover list`` update supported devices before
displaying them. The default summary also reports devices that could not be
queried because of an authentication failure and devices that are not
supported by the library.

Broadcast routing and multiple interfaces
-----------------------------------------

The default ``255.255.255.255`` address is a limited broadcast. On systems with
multiple active network interfaces, the operating system may send it through
an interface that cannot reach the devices.

Use ``--target`` to send discovery to the subnet-directed broadcast address of the network containing the devices.
For example, if the devices reside on ``10.0.0.0/24``, use::

    kasa --target 10.0.0.255 discover

If directed discovery works but the default does not, review the host's network
interface and routing configuration.

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

.. note::

    For devices requiring authentication, the device-stored credentials can be changed using
    the ``update-credentials`` commands, for example, to match with other cloud-connected devices.
    However, note that communications with devices provisioned using this method will stop working
    when connected to the cloud.

.. note::

    Some commands do not work if the device time is out-of-sync.
    You can use ``kasa time sync`` command to set the device time from the system where the command is run.

.. warning::

    At least some devices (e.g., Tapo lights L530 and L900) are known to have a watchdog that reboots them every 10 minutes if they are unable to connect to the cloud.
    Although the communications are done locally, this will make these devices unavailable for a minute every time the device restarts.
    This does not affect other devices to our current knowledge, but you have been warned.



``kasa --help``
***************

.. program-output:: kasa --help
