#!/usr/bin/env python
"""
This code allow for the decryption of KlapV2 data from a pcap file.

It will output the decrypted data to a file.
This was designed and tested with a Tapo light strip setup using a cloud account.
"""

from __future__ import annotations

import asyncio
import codecs
import json
import re
from threading import Thread

import asyncclick as click
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
from kasa.protocol import DEFAULT_CREDENTIALS, get_default_credentials


def _is_http_response_for_packet(response, packet):
    """Return True if the *response* contains a response for request in *packet*.

    Different tshark versions use different field for the information.
    """
    if not hasattr(response, "http"):
        return False
    if hasattr(response.http, "response_for_uri") and (
        response.http.response_for_uri == packet.http.request_full_uri
    ):
        return True
    # tshark 4.4.0
    if response.http.request_uri == packet.http.request_uri:
        return True

    return False


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
        self._local_seed: bytes | None = None
        self._remote_seed: bytes | None = None
        self._session: MyEncryptionSession | None = None
        self._creds = creds
        self._klap: KlapTransportV2 = klap
        self._auth_hash = self._klap.generate_auth_hash(self._creds)
        self._local_seed_auth_hash = None
        self._remote_seed_auth_hash = None
        self._seq = 0

    def check_default_credentials(self):
        """Check whether default credentials were used.

        Devices sometimes randomly accept the hardcoded default credentials
        and the library handles that.
        """
        for value in DEFAULT_CREDENTIALS.values():
            default_credentials = get_default_credentials(value)
            default_auth_hash = self._klap.generate_auth_hash(default_credentials)
            default_credentials_seed_auth_hash = self._klap.handshake1_seed_auth_hash(
                self._local_seed,
                self._remote_seed,
                default_auth_hash,  # type: ignore
            )
            if self._remote_seed_auth_hash == default_credentials_seed_auth_hash:
                return default_auth_hash
        return None

    def update_encryption_session(self):
        """Update the encryption session used for decrypting data.

        It is called whenever the local_seed, remote_seed,
        or remote_auth_hash is updated.

        It checks if the seeds are set and, if they are, creates a new session.

        Raises:
            ValueError: If the auth hashes do not match.
        """
        if self._local_seed is None or self._remote_seed is None:
            self._session = None
        else:
            self._local_seed_auth_hash = self._klap.handshake1_seed_auth_hash(
                self._local_seed, self._remote_seed, self._auth_hash
            )
            auth_hash = None
            if self._remote_seed_auth_hash is not None:
                if self._local_seed_auth_hash == self._remote_seed_auth_hash:
                    auth_hash = self._auth_hash
                else:
                    auth_hash = self.check_default_credentials()
                if not auth_hash:
                    raise ValueError(
                        "Local and remote auth hashes do not match. "
                        "This could mean an incorrect username and/or password."
                    )
                self._session = MyEncryptionSession(
                    self._local_seed, self._remote_seed, auth_hash
                )
                self._session._seq = self._seq
                self._session._generate_cipher()

    @property
    def seq(self) -> int:
        """Get the sequence number."""
        return self._seq

    @seq.setter
    def seq(self, value: int):
        if not isinstance(value, int):
            raise ValueError("seq must be an integer")
        self._seq = value
        self.update_encryption_session()

    @property
    def local_seed(self) -> bytes | None:
        """Get the local seed."""
        return self._local_seed

    @local_seed.setter
    def local_seed(self, value: bytes):
        print("setting local_seed")
        if not isinstance(value, bytes):
            raise ValueError("local_seed must be bytes")
        elif len(value) != 16:
            raise ValueError("local_seed must be 16 bytes")
        else:
            self._local_seed = value
            self._remote_seed_auth_hash = None
            self._remote_seed = None
            self.update_encryption_session()

    @property
    def remote_auth_hash(self) -> bytes | None:
        """Get the remote auth hash."""
        return self._remote_seed_auth_hash

    @remote_auth_hash.setter
    def remote_auth_hash(self, value: bytes):
        print("setting remote_auth_hash")
        if not isinstance(value, bytes):
            raise ValueError("remote_auth_hash must be bytes")
        elif len(value) != 32:
            raise ValueError("remote_auth_hash must be 32 bytes")
        else:
            self._remote_seed_auth_hash = value
            self.update_encryption_session()

    @property
    def remote_seed(self) -> bytes | None:
        """Get the remote seed."""
        return self._remote_seed

    @remote_seed.setter
    def remote_seed(self, value: bytes):
        print("setting remote_seed")
        if not isinstance(value, bytes):
            raise ValueError("remote_seed must be bytes")
        elif len(value) != 16:
            raise ValueError("remote_seed must be 16 bytes")
        else:
            self._remote_seed = value
            self.update_encryption_session()

    # This function decrypts the data using the encryption session.
    def decrypt(self, *args, **kwargs):
        """Decrypt the data using the encryption session."""
        if self._session is None:
            raise ValueError("No session available")
        return self._session.decrypt(*args, **kwargs)


# This is a custom error handler that replaces bad characters with '*',
# in case something goes wrong in decryption.
# Without this, the decryption could yield an error.
def bad_chars_replacement(exception):
    """Replace bad characters with '*'."""
    return ("*", exception.start + 1)


codecs.register_error("bad_chars_replacement", bad_chars_replacement)


def main(
    loop: asyncio.AbstractEventLoop,
    username,
    password,
    device_ip,
    source_host,
    pcap_file_path,
    output_json_name=None,
):
    """Run the main function."""
    asyncio.set_event_loop(loop)
    capture = pyshark.FileCapture(pcap_file_path, display_filter="http", eventloop=loop)

    # In an effort to keep this code tied into the original code
    # (so that this can hopefully leverage any future codebase updates inheriently),
    # some weird initialization is done here
    creds = Credentials(username, password)

    fake_connection = DeviceConnectionParameters(
        DeviceFamily.SmartTapoBulb, DeviceEncryptionType.Klap
    )
    fake_device = DeviceConfig(
        device_ip, connection_type=fake_connection, credentials=creds
    )

    operator = Operator(KlapTransportV2(config=fake_device), creds)
    packets = []

    # pyshark is a little weird in how it handles iteration,
    # so this is a workaround to allow for (advanced) iteration over the packets.
    while True:
        try:
            packet = capture.next()
            packet_number = capture._current_packet
            if packet.ip.src != source_host:
                continue
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
                data = (
                    # Windows and linux file_data attribute returns different
                    # pretty format so get the raw field value.
                    packet.http.get_field_value("file_data", raw=True)
                    if hasattr(packet.http, "file_data")
                    else None
                )
                match uri:
                    case "/app/request":
                        if packet.ip.dst != device_ip:
                            continue
                        assert isinstance(data, str)  # noqa: S101
                        message = bytes.fromhex(data)
                        try:
                            plaintext = operator.decrypt(message)
                            payload = json.loads(plaintext)
                            print(json.dumps(payload, indent=2))
                            packets.append(payload)
                        except ValueError:
                            print("Insufficient data to decrypt thus far")

                    case "/app/handshake1":
                        if packet.ip.dst != device_ip:
                            continue
                        assert isinstance(data, str)  # noqa: S101
                        message = bytes.fromhex(data)
                        operator.local_seed = message
                        response = None
                        print(
                            f"got handshake1 in {packet_number}, "
                            f"looking for the response"
                        )
                        while (
                            True
                        ):  # we are going to now look for the response to this request
                            response = capture.next()
                            if _is_http_response_for_packet(response, packet):
                                print(f"found response in {packet_number}")
                                break
                        data = response.http.get_field_value("file_data", raw=True)
                        message = bytes.fromhex(data)
                        operator.remote_seed = message[0:16]
                        operator.remote_auth_hash = message[16:]

                    case "/app/handshake2":
                        continue  # we don't care about this
                    case _:
                        continue
        except StopIteration:
            break

    # save the final array to a file
    if output_json_name is not None:
        with open(output_json_name, "w") as f:
            f.write(json.dumps(packets, indent=2))
            f.write("\n" * 1)
            f.close()

    # Call close method which cleans up event loop
    capture.close()


@click.command()
@click.option(
    "--host",
    required=True,
    help="the IP of the smart device as it appears in the pcap file.",
)
@click.option(
    "--source-host",
    required=True,
    help="the IP of the device communicating with the smart device.",
)
@click.option(
    "--username",
    required=True,
    envvar="KASA_USERNAME",
    help="Username/email address to authenticate to device.",
)
@click.option(
    "--password",
    required=True,
    envvar="KASA_PASSWORD",
    help="Password to use to authenticate to device.",
)
@click.option(
    "--pcap-file-path",
    required=True,
    help="The path to the pcap file to parse.",
)
@click.option(
    "-o",
    "--output",
    required=False,
    help="The name of the output file, relative to the current directory.",
)
async def cli(username, password, host, source_host, pcap_file_path, output):
    """Export KLAP data in JSON format from a PCAP file."""
    # pyshark does not work within a running event loop and we don't want to
    # install click as well as asyncclick so run in a new thread.
    loop = asyncio.new_event_loop()
    thread = Thread(
        target=main,
        args=[loop, username, password, host, source_host, pcap_file_path, output],
        daemon=True,
    )
    thread.start()
    thread.join()


if __name__ == "__main__":
    cli()
