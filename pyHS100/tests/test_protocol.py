from unittest import TestCase
from ..protocol import TPLinkSmartHomeProtocol
import json


class TestTPLinkSmartHomeProtocol(TestCase):
    def test_encrypt(self):
        d = json.dumps({'foo': 1, 'bar': 2})
        encrypted = TPLinkSmartHomeProtocol.encrypt(d)
        # encrypt adds a 4 byte header
        encrypted = encrypted[4:]
        self.assertEqual(d, TPLinkSmartHomeProtocol.decrypt(encrypted))
