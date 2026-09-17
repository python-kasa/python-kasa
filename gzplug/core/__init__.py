"""Device control and run execution, independent of any user interface.

Nothing in this package imports from :mod:`gzplug.api` or knows that a browser
exists, which is what lets it be tested against the repository's offline
device fixtures.
"""

from __future__ import annotations
