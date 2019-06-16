from unittest import TestCase
from ..protocol import TPLinkSmartHomeProtocol
import json


class TestTPLinkSmartHomeProtocol(TestCase):
    def test_encrypt(self):
        d = json.dumps({"foo": 1, "bar": 2})
        encrypted = TPLinkSmartHomeProtocol.encrypt(d)
        # encrypt adds a 4 byte header
        encrypted = encrypted[4:]
        self.assertEqual(d, TPLinkSmartHomeProtocol.decrypt(encrypted))

    def test_encrypt_unicode(self):
        d = "{'snowman': '\u2603'}"

        e = bytes(
            [
                208,
                247,
                132,
                234,
                133,
                242,
                159,
                254,
                144,
                183,
                141,
                173,
                138,
                104,
                240,
                115,
                84,
                41,
            ]
        )

        encrypted = TPLinkSmartHomeProtocol.encrypt(d)
        # encrypt adds a 4 byte header
        encrypted = encrypted[4:]

        self.assertEqual(e, encrypted)

    def test_decrypt_unicode(self):
        e = bytes(
            [
                208,
                247,
                132,
                234,
                133,
                242,
                159,
                254,
                144,
                183,
                141,
                173,
                138,
                104,
                240,
                115,
                84,
                41,
            ]
        )

        d = "{'snowman': '\u2603'}"

        self.assertEqual(d, TPLinkSmartHomeProtocol.decrypt(e))
