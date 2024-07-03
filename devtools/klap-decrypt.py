"""
This code allow for the decryption of KlapV2 data from a pcap file.

It will output the decrypted data to a file.
This was designed and tested with a Tapo light strip setup using a cloud account.
"""

import codecs
import json
import re

import pyshark
from cryptography.hazmat.primitives import padding

from kasa.credentials import Credentials
from kasa.deviceconfig import (
    DeviceConfig,
    DeviceConnectionParameters,
    DeviceEncryptionType,
    DeviceFamily,
)
from kasa.klaptransport import KlapEncryptionSession, KlapTransportV2

# These are the only variables that need to be changed in order to run this code.
# ********** CHANGE THESE **********
username = "hello@world.com"  # cloud account username (likely an email)
password = "hunter2"  # cloud account password  # noqa: S105
# the ip of the smart device as it appears in the pcap file
device_ip = "192.168.1.100"
pcap_file_path = "/path/to/my.pcap"  # the path to the pcap file
output_json_name = (
    "output.json"  # the name of the output file, relative to the current directory
)
# **********************************

capture = pyshark.FileCapture(pcap_file_path, display_filter="http")

# In an effort to keep this code tied into the original code
# (so that this can hopefully leverage any future codebase updates inheriently),
# some weird initialization is done here
myCreds = Credentials(username, password)

fakeConnection = DeviceConnectionParameters(
    DeviceFamily.SmartTapoBulb, DeviceEncryptionType.Klap
)
fakeDevice = DeviceConfig(
    device_ip, connection_type=fakeConnection, credentials=myCreds
)


# In case any modifications need to be made in the future,
# this class is created to allow for easy modification
class MyKlapTransport(KlapTransportV2):
    """A custom KlapTransportV2 class that allows for easy modification."""

    pass


# This is a custom error handler that replaces bad characters with '*',
# in case something goes wrong in decryption.
# Without this, the decryption could yield an error.
def bad_chars_replacement(exception):
    """Replace bad characters with '*'."""
    return ("*", exception.start + 1)


codecs.register_error("bad_chars_replacement", bad_chars_replacement)


class MyEncryptionSession(KlapEncryptionSession):
    """A custom KlapEncryptionSession class that allows for decryption."""

    def decrypt(self, msg):
        """Decrypt the data."""
        decryptor = self._cipher.decryptor()
        dp = decryptor.update(msg[32:]) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plaintextbytes = unpadder.update(dp) + unpadder.finalize()

        return plaintextbytes.decode("utf-8", "bad_chars_replacement")


class Operator:
    """A class that handles the data decryption, and the encryption session updating."""

    def __init__(self, klap, creds):
        self.__local_seed: bytes = None
        self.__remote_seed: bytes = None
        self.__session: MyEncryptionSession = None
        self.__creds = creds
        self.__klap: MyKlapTransport = klap
        self.__auth_hash = self.__klap.generate_auth_hash(self.__creds)
        self.__local_auth_hash = None
        self.__remote_auth_hash = None
        self.__seq = 0
        pass

    def update_encryption_session(self):
        """Update the encryption session used for decrypting data.

        It is called whenever the local_seed, remote_seed,
        or remote_auth_hash is updated.

        It checks if the seeds are set and, if they are, creates a new session.

        Raises:
            ValueError: If the auth hashes do not match.
        """
        if self.__local_seed is None or self.__remote_seed is None:
            self.__session = None
        else:
            self.__local_auth_hash = self.__klap.handshake1_seed_auth_hash(
                self.__local_seed, self.__remote_seed, self.__auth_hash
            )
            if (self.__remote_auth_hash is not None) and (
                self.__local_auth_hash != self.__remote_auth_hash
            ):
                raise ValueError(
                    "Local and remote auth hashes do not match.\
This could mean an incorrect username and/or password."
                )
            self.__session = MyEncryptionSession(
                self.__local_seed, self.__remote_seed, self.__auth_hash
            )
            self.__session._seq = self.__seq
            self.__session._generate_cipher()

    @property
    def seq(self) -> int:
        """Get the sequence number."""
        return self.__seq

    @seq.setter
    def seq(self, value: int):
        if not isinstance(value, int):
            raise ValueError("seq must be an integer")
        self.__seq = value
        self.update_encryption_session()

    @property
    def local_seed(self) -> bytes:
        """Get the local seed."""
        return self.__local_seed

    @local_seed.setter
    def local_seed(self, value: bytes):
        if not isinstance(value, bytes):
            raise ValueError("local_seed must be bytes")
        elif len(value) != 16:
            raise ValueError("local_seed must be 16 bytes")
        else:
            self.__local_seed = value
            self.update_encryption_session()

    @property
    def remote_auth_hash(self) -> bytes:
        """Get the remote auth hash."""
        return self.__remote_auth_hash

    @remote_auth_hash.setter
    def remote_auth_hash(self, value: bytes):
        print("setting remote_auth_hash")
        if not isinstance(value, bytes):
            raise ValueError("remote_auth_hash must be bytes")
        elif len(value) != 32:
            raise ValueError("remote_auth_hash must be 32 bytes")
        else:
            self.__remote_auth_hash = value
            self.update_encryption_session()

    @property
    def remote_seed(self) -> bytes:
        """Get the remote seed."""
        return self.__remote_seed

    @remote_seed.setter
    def remote_seed(self, value: bytes):
        print("setting remote_seed")
        if not isinstance(value, bytes):
            raise ValueError("remote_seed must be bytes")
        elif len(value) != 16:
            raise ValueError("remote_seed must be 16 bytes")
        else:
            self.__remote_seed = value
            self.update_encryption_session()

    # This function decrypts the data using the encryption session.
    def decrypt(self, *args, **kwargs):
        """Decrypt the data using the encryption session."""
        if self.__session is None:
            raise ValueError("No session available")
        return self.__session.decrypt(*args, **kwargs)


operator = Operator(MyKlapTransport(config=fakeDevice), myCreds)

finalArray = []

# pyshark is a little weird in how it handles iteration,
# so this is a workaround to allow for (advanced) iteration over the packets.
while True:
    try:
        packet = capture.next()
        packet_number = capture._current_packet
        # we only care about http packets
        if hasattr(
            packet, "http"
        ):  # this is redundant, as pyshark is set to only load http packets
            if hasattr(packet.http, "request_uri_path"):
                uri = packet.http.get("request_uri_path")
            elif hasattr(packet.http, "request_uri"):
                uri = packet.http.get("request_uri")
            else:
                uri = None
            if hasattr(packet.http, "request_uri_query"):
                query = packet.http.get("request_uri_query")
                # use regex to get: seq=(\d+)
                seq = re.search(r"seq=(\d+)", query)
                if seq is not None:
                    operator.seq = int(
                        seq.group(1)
                    )  # grab the sequence number from the query
            data = packet.http.file_data if hasattr(packet.http, "file_data") else None
            match uri:
                case "/app/request":
                    if packet.ip.dst != device_ip:
                        continue
                    message = bytes.fromhex(data.replace(":", ""))
                    try:
                        plaintext = operator.decrypt(message)
                        myDict = json.loads(plaintext)
                        print(json.dumps(myDict, indent=2))
                        finalArray.append(myDict)
                    except ValueError:
                        print("Insufficient data to decrypt thus far")

                case "/app/handshake1":
                    if packet.ip.dst != device_ip:
                        continue
                    message = bytes.fromhex(data.replace(":", ""))
                    operator.local_seed = message
                    response = None
                    while (
                        True
                    ):  # we are going to now look for the response to this request
                        response = capture.next()
                        if (
                            hasattr(response, "http")
                            and hasattr(response.http, "response_for_uri")
                            and (
                                response.http.response_for_uri
                                == packet.http.request_full_uri
                            )
                        ):
                            break
                    data = response.http.file_data
                    message = bytes.fromhex(data.replace(":", ""))
                    operator.remote_seed = message[0:16]
                    operator.remote_auth_hash = message[16:]

                case "/app/handshake2":
                    continue  # we don't care about this
                case _:
                    continue
    except StopIteration:
        break

# save the final array to a file
with open(output_json_name, "w") as f:
    f.write(json.dumps(finalArray, indent=2))
    f.write("\n" * 1)
    f.close()
