from __future__ import absolute_import
from __future__ import unicode_literals

from unittest import TestCase
from pyHS100.protocol import TPLinkSmartHomeProtocol
import json


class TestTPLinkSmartHomeProtocol(TestCase):
    def test_encrypt(self):
        d = json.dumps({'foo': 1, 'bar': 2})
        encrypted = TPLinkSmartHomeProtocol.encrypt(d)
        # encrypt appends nullbytes for the protocol sends
        encrypted = encrypted.lstrip(b'\0')
        self.assertEqual(d, TPLinkSmartHomeProtocol.decrypt(encrypted))
