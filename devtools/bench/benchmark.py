"""Benchmark the new parser against the old parser."""

import json
import timeit

import orjson
from kasa_crypt import decrypt, encrypt
from utils.data import REQUEST, WIRE_RESPONSE
from utils.original import OriginalTPLinkSmartHomeProtocol


def original_request_response() -> None:
    """Benchmark the original parser."""
    OriginalTPLinkSmartHomeProtocol.encrypt(json.dumps(REQUEST))
    json.loads(OriginalTPLinkSmartHomeProtocol.decrypt(WIRE_RESPONSE[4:]))


def new_request_response() -> None:
    """Benchmark the new parser."""
    encrypt(orjson.dumps(REQUEST).decode())
    orjson.loads(decrypt(WIRE_RESPONSE[4:]))


count = 100000

time = timeit.Timer(new_request_response).timeit(count)
print(f"New parser, parsing {count} messages took {time} seconds")

time = timeit.Timer(original_request_response).timeit(count)
print(f"Old parser, parsing {count} messages took {time} seconds")
