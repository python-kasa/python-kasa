Bulbs
===========

.. contents:: Contents
   :local:

Supported features
******************

* Turning on and off
* Setting brightness, color temperature, and color (in HSV)
* Querying emeter information
* Transitions
* Presets

Currently unsupported
*********************

* Setting the default transitions
* Timers

.. note::

    Feel free to open a pull request to add support for more features!

Transitions
***********

All commands changing the bulb state can be accompanied with a transition, e.g., to slowly fade the light off.
The transition time is in milliseconds, 0 means immediate change.
If no transition value is given, the default setting as configured for the bulb will be used.

.. note::

    Accepted values are command (and potentially bulb) specific, feel free to improve the documentation on accepted values.

    **Example:** While KL130 allows at least up to 15 second transitions for smooth turning off transitions, turning it on will not be so smooth.

Command-line usage
******************

All command-line commands can be used with transition period for smooth changes.


**Example:** Turn the bulb off over a 15 second time period.

.. code::

    $ kasa --type bulb --host <host> off --transition 15000

**Example:** Change the bulb to red with 20% brightness over 15 seconds:

.. code::

    $ kasa --type bulb --host <host> hsv 0 100 20 --transition 15000


API documentation
*****************

.. autoclass:: kasa.SmartBulb
    :members:
    :inherited-members:
    :undoc-members:

.. autoclass:: kasa.SmartBulbPreset
    :members:
    :undoc-members:

.. autoclass:: kasa.smartbulb.BehaviorMode
    :members:

.. autoclass:: kasa.TurnOnBehaviors
    :members:


.. autoclass:: kasa.TurnOnBehavior
    :undoc-members:
    :members:
