Command-line usage
==================

The package is shipped with a console tool named kasa, please refer to ``kasa --help`` for detailed usage.
The device to which the commands are sent is chosen by `KASA_HOST` environment variable or passing ``--host <address>`` as an option.
To see what is being sent to and received from the device, specify option ``--debug``.

To avoid discovering the devices when executing commands its type can be passed by specifying either ``--plug`` or ``--bulb``,
if no type is given its type will be discovered automatically with a small delay.
Some commands (such as reading energy meter values and setting color of bulbs) additional parameters are required,
which you can find by adding ``--help`` after the command, e.g. ``kasa emeter --help`` or ``kasa hsv --help``.

If no command is given, the ``state`` command will be executed to query the device state.

Provisioning
~~~~~~~~~~~~

You can provision your device without any extra apps by using the ``kasa wifi`` command:

1. If the device is unprovisioned, connect to its open network
2. Use ``kasa discover`` (or check the routes) to locate the IP address of the device (likely 192.168.0.1)
3. Scan for available networks using ``kasa wifi scan``
4. Join/change the network using ``kasa wifi join`` command, see ``--help`` for details.

``kasa --help``
~~~~~~~~~~~~~~~

.. program-output:: kasa --help
