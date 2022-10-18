Smart strips
============

.. contents:: Contents
   :local:

.. note::

    Feel free to open a pull request to improve the documentation!

Command-line usage
******************

To command a single socket of a strip, you will need to specify it either by using ``--index`` or by using ``--name``.
If not specified, the commands will act on the parent device: turning the strip off will turn off all sockets.

**Example:** Turn on the first socket (the indexing starts from zero):

.. code::

   $ kasa --type strip --host <host> on --index 0

**Example:** Turn off the socket by name:

.. code::

   $ kasa --type strip --host <host> off --name "Maybe Kitchen"


API documentation
*****************

.. autoclass:: kasa.SmartStrip
    :members:
    :inherited-members:
    :undoc-members:
