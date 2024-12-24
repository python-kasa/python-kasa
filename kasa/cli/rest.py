"""Module for cli rest api."""

import asyncio
import datetime
import inspect
import logging
import socket
import ssl
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

import asyncclick as click
from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from kasa import (
    Device,
)
from kasa.json import dumps as json_dumps
from kasa.json import loads as json_loads
from kasa.module import _is_bound_feature

from .common import echo
from .discover import _discover

_LOGGER = logging.getLogger(__name__)
logging.getLogger("aiohttp").setLevel(logging.WARNING)

CERT_FILENAME = "certificate.pem"
KEY_FILENAME = "key.pem"
DEFAULT_PASSPHRASE = "passthrough"  # noqa: S105


async def wait_on_keyboard_interrupt(msg: str):
    """Non loop blocking get input."""
    echo(msg + ", press Ctrl-C to cancel\n")

    with suppress(asyncio.CancelledError):
        await asyncio.Event().wait()


async def _get_host_ip() -> str:
    def get_ip() -> str:
        #  From https://stackoverflow.com/a/28950776
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            # doesn't even have to be reachable
            s.connect(("10.254.254.254", 1))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return ip

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_ip)


@click.command()
@click.option(
    "--rest-port",
    default=8080,
    required=False,
    help="Port for rest api.",
)
@click.option(
    "--rest-host",
    default=None,
    required=False,
    envvar="KASA_LISTEN_IP",
    help="Host for rest api.",
)
@click.option(
    "--cert-file",
    default=None,
    required=False,
    help="Cert file for https.",
)
@click.option(
    "--key-file",
    default=None,
    required=False,
    help="Key file for https.",
)
@click.option(
    "--key-passphrase",
    default=None,
    required=False,
    help="Passphrase for https key.",
)
@click.option(
    "--https/--no-https",
    default=True,
    is_flag=True,
    type=bool,
    help=(
        "Use https, recommended to ensure passwords are not sent unencrypted. "
        "If no cert-file provided will auto-create self-signed cert."
    ),
)
@click.option(
    "--localhost/--no-localhost",
    default=True,
    is_flag=True,
    type=bool,
    help=("Start server on localhost or primary device ip. "),
)
@click.option(
    "--self-signed-folder",
    default="./self-signed",
    help="Location to store auto-created self-signed cert files.",
)
@click.option(
    "--secure/--no-secure",
    default=True,
    is_flag=True,
    type=bool,
    help=(
        "Require username and password in requests for "
        "devices that require authentication."
    ),
)
@click.pass_context
async def rest(
    ctx: click.Context,
    rest_port: int,
    rest_host: str | None,
    cert_file: str | None,
    key_file: str | None,
    key_passphrase: str | None,
    https: bool,
    self_signed_folder: str,
    localhost: bool,
    secure: bool,
) -> None:
    """Start the rest api.

    Example calls:

    List all device attributes:
    POST /device?host=<device_ip>

    Username and password required in all requests for devices that require
    authentication unless --no-secure is set:
    POST /device?host=<device_ip> '{"username": "user@example.com", "password": "pwd"}'

    Set a device attribute
    POST /device?host=<device_ip> '{"name": "set_alias", "value": "Study cam"}'

    List all device module ids:
    POST /module?host=<device_ip>

    List all module attributes
    POST /module?host=<device_ip> '{"id": "Light"}'

    Set a module attribute
    POST /module?host=<device_ip> '{"id": "Light", "name": "set_brightness",
    "value": 50}'

    List all device feature ids:
    POST /feature?host=<device_ip>

    Set a feature value
    POST /feature?host=<device_ip> '{"id": "brightness", "value": 50}'
    """
    if not rest_host:
        if localhost:
            rest_host = "localhost"
        else:
            rest_host = await _get_host_ip()

    scheme = "https" if https or cert_file else "http"
    echo(f"Starting the rest api on {scheme}://{rest_host}:{rest_port}")

    devices = await _discover(ctx.parent)

    if https and not cert_file:
        if not key_passphrase:
            key_passphrase = DEFAULT_PASSPHRASE

        self_signed_path = Path(self_signed_folder)
        cert_file_path = self_signed_path / CERT_FILENAME
        key_file_path = self_signed_path / KEY_FILENAME
        cert_file = str(cert_file_path)
        key_file = str(key_file_path)

        if not cert_file_path.exists() or not key_file_path.exists():
            echo("Creating self-signed certificate")

            self_signed_path.mkdir(exist_ok=True)
            _create_self_signed_key(key_file, cert_file, key_passphrase)

    if TYPE_CHECKING:
        assert ctx.parent
    username = ctx.parent.params["username"]
    password = ctx.parent.params["password"]
    server = RestServer(devices, username=username, password=password, secure=secure)

    await server.start(
        rest_host,
        rest_port,
        cert_file=cert_file,
        key_file=key_file,
        key_passphrase=key_passphrase,
    )

    msg = f"Started rest api on {scheme}://{rest_host}:{rest_port}"

    await wait_on_keyboard_interrupt(msg)

    echo("\nStopping rest api")

    await server.stop()


class RestServer:
    """Rest server class."""

    def __init__(
        self,
        devices: dict[str, Device],
        *,
        username: str | None,
        password: str | None,
        secure: bool,
    ) -> None:
        self.devices = devices
        self.running = False
        self._username = username
        self._password = password
        self._secure = secure

    @staticmethod
    def _serializable(o: object, attr_name: str) -> Any | None:
        val = getattr(o, attr_name)
        if hasattr(val, "to_dict"):
            return val.to_dict()
        try:
            json_dumps(val)
            return val
        except (TypeError, OverflowError):
            return None

    def _check_auth(self, request_dict: dict[str, Any], device: Device) -> bool:
        if not self._secure:
            return True

        if not device.device_info.requires_auth:
            return True

        if (un := request_dict.get("username")) and (
            pw := request_dict.get("password")
        ):
            return (un == self._username) and (pw == self._password)

        return False

    async def _module(self, request: web.Request) -> web.Response:
        if not (host := request.query.get("host")):
            return web.Response(status=400, text="No host provided")

        def _get_interface(mod):
            for base in mod.__class__.__bases__:
                if base.__module__.startswith("kasa.interfaces"):
                    return base
            return None

        dev = self.devices[host]
        await dev.update()

        if req_body := await request.read():
            req = json_loads(req_body.decode())
        else:
            req = {}

        if not self._check_auth(req, dev):
            return web.Response(status=401)

        if not (module_id := req.get("id")):
            list_result = {
                "result": [
                    mod_name
                    for mod_name, mod in dev.modules.items()
                    if _get_interface(mod) is not None
                ]
            }
            body = json_dumps(list_result)
            return web.Response(body=body)

        if not (module := dev.modules.get(module_id)) or not (
            interface_cls := _get_interface(module)
        ):
            return web.Response(status=400)

        # TODO make valid_temperature_range a FeatureAttribute
        skip = {
            "valid_temperature_range",
            "is_color",
            "is_dimmable",
            "is_variable_color_temp",
            "has_effects",
        }
        properties = {
            attr_name: val
            for attr_name in vars(interface_cls)
            if attr_name[0] != "_"
            and attr_name not in skip
            and (attr := getattr(module.__class__, attr_name))
            and isinstance(attr, property)
            and (not _is_bound_feature(attr) or module.has_feature(attr_name))
            and (val := self._serializable(module, attr_name))
        }

        # Return all the properties
        if "name" not in req:
            result = {"result": properties}
            body = json_dumps(result)
            return web.Response(body=body)

        setter_properties = {
            attr_name
            for attr_name in vars(interface_cls)
            if attr_name[:3] == "set"
            and (attr := getattr(module.__class__, attr_name))
            and inspect.iscoroutinefunction(attr)
        }

        # Set a value on the module
        if (value := req.get("value")) is not None:
            if req["name"] not in setter_properties:
                return web.Response(status=400)
            res = await getattr(module, req["name"])(value)
            result = {"result": res}
            return web.Response(body=json_dumps(result))

        # Call a method with no params
        callable_methods = {
            attr_name
            for attr_name in vars(interface_cls)
            if (attr := getattr(module.__class__, attr_name))
            and inspect.iscoroutinefunction(attr)
        }
        if req["name"] not in callable_methods:
            return web.Response(status=400)

        res = await getattr(module, req["name"])()
        result = {"result": res}
        return web.Response(body=json_dumps(result))

    async def _device(self, request: web.Request) -> web.Response:
        if not (host := request.query.get("host")):
            return web.Response(status=400, text="No host provided")

        dev = self.devices[host]
        await dev.update()

        if req_body := await request.read():
            req = json_loads(req_body.decode())
        else:
            req = {}

        if not self._check_auth(req, dev):
            return web.Response(status=401)

        if not (name := req.get("name")):
            skip = {"internal_state", "sys_info", "config", "hw_info"}
            properties = {
                attr_name: val
                for attr_name in vars(Device)
                if attr_name[0] != "_"
                and attr_name not in skip
                and (attr := getattr(Device, attr_name))
                and isinstance(attr, property)
                and (val := self._serializable(dev, attr_name))
            }

            result = {"result": properties}
            return web.Response(body=json_dumps(result))

        setter_properties = {
            attr_name
            for attr_name in vars(Device)
            if attr_name[:3] == "set"
            and (attr := getattr(Device, attr_name))
            and inspect.iscoroutinefunction(attr)
        }
        if name not in setter_properties:
            return web.Response(status=400)

        res = await getattr(dev, name)(req["value"])
        result = {"result": res}
        return web.Response(body=json_dumps(result))

    async def _feature(self, request: web.Request) -> web.Response:
        if not (host := request.query.get("host")):
            return web.Response(status=400, text="No host provided")

        dev = self.devices[host]
        await dev.update()
        features = dev.features

        if req_body := await request.read():
            req = json_loads(req_body.decode())
        else:
            req = {}

        if not self._check_auth(req, dev):
            return web.Response(status=401)

        if not (feat_id := req.get("id")):
            feats = {feat.id: feat.value for feat in features.values()}
            result = {"result": feats}
            body = json_dumps(result)
            return web.Response(body=body)

        if not (feat := features.get(feat_id)):
            return web.Response(status=400)

        await feat.set_value(req["value"])
        return web.Response()

    async def start(
        self,
        rest_ip: str,
        rest_port: int,
        *,
        cert_file: str | None = None,
        key_file: str | None = None,
        key_passphrase: str | None = None,
    ) -> None:
        """Start the server."""
        app = web.Application()
        app.add_routes(
            [
                web.post("/device", self._device),
                web.post("/module", self._module),
                web.post("/feature", self._feature),
            ]
        )

        self.runner = web.AppRunner(app)
        await self.runner.setup()

        if cert_file:
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(cert_file, key_file, key_passphrase)
        else:
            ssl_context = None

        self.site = web.TCPSite(
            self.runner, rest_ip, rest_port, ssl_context=ssl_context
        )
        try:
            await self.site.start()
        except Exception as ex:
            _LOGGER.exception(
                "Error trying to start rest api on %s:%s: %s", rest_ip, rest_port, ex
            )
            raise

        _LOGGER.debug(
            "Rest api running on %s:%s",
            rest_ip,
            rest_port,
        )
        self.running = True

    async def stop(self) -> None:
        """Stop the rest api."""
        if not self.running:
            _LOGGER.debug("Rest api already stopped")
            return

        _LOGGER.debug("Stopping rest api")
        self.running = False

        await self.site.stop()
        await self.runner.shutdown()


def _create_self_signed_key(key_file: str, certificate_file: str, passphrase: str):
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    # Write our key to disk for safe keeping
    with open(key_file, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.BestAvailableEncryption(
                    passphrase.encode()
                ),
            )
        )

    # Various details about who we are. For a self-signed certificate the
    # subject and issuer are always the same.
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "My Company"),
            x509.NameAttribute(NameOID.COMMON_NAME, "mysite.com"),
        ]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(
            # Our certificate will be valid for 10 days
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=10)
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]),
            critical=False,
            # Sign our certificate with our private key
        )
        .sign(key, hashes.SHA256())
    )
    # Write our certificate out to disk.
    with open(certificate_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
