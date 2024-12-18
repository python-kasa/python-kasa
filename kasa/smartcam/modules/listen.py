"""Implementation of motion detection module."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from collections.abc import Callable
from datetime import timedelta
from enum import StrEnum, auto
from subprocess import check_output

import onvif  # type: ignore[import-untyped]
from aiohttp import web
from onvif.managers import NotificationManager  # type: ignore[import-untyped]

from ...credentials import Credentials
from ..smartcammodule import SmartCamModule

_LOGGER = logging.getLogger(__name__)


class EventType(StrEnum):
    """Listen event types."""

    MOTION_DETECTED = auto()
    PERSON_DETECTED = auto()
    TAMPER_DETECTED = auto()
    BABY_CRY_DETECTED = auto()


TOPIC_EVENT_TYPE = {
    "tns1:RuleEngine/CellMotionDetector/Motion": EventType.MOTION_DETECTED,
    "tns1:RuleEngine/CellMotionDetector/People": EventType.PERSON_DETECTED,
    "tns1:RuleEngine/TamperDetector/Tamper": EventType.TAMPER_DETECTED,
}


class Listen(SmartCamModule):
    """Implementation of lens mask module."""

    manager: NotificationManager
    callback: Callable[[EventType], None]
    topics: set[EventType] | None
    listening = False
    site: web.TCPSite
    runner: web.AppRunner

    async def _invoke_callback(self, event: EventType) -> None:
        self.callback(event)

    async def _handle_event(self, request: web.Request) -> web.Response:
        content = await request.read()
        result = self.manager.process(content)
        for msg in result.NotificationMessage:
            if (event := TOPIC_EVENT_TYPE.get(msg.Topic._value_1)) and (
                not self.topics or event in self.topics
            ):
                asyncio.create_task(self._invoke_callback(event))
        return web.Response()

    async def listen(
        self,
        callback: Callable[[EventType], None],
        camera_credentials: Credentials,
        *,
        topics: set[EventType] | None = None,
        listen_ip: str | None = None,
    ) -> None:
        """Start listening for events."""
        self.callback = callback
        self.topics = topics

        def subscription_lost() -> None:
            pass

        wsdl = f"{os.path.dirname(onvif.__file__)}/wsdl/"

        mycam = onvif.ONVIFCamera(
            self._device.host,
            2020,
            camera_credentials.username,
            camera_credentials.password,
            wsdl,
        )
        await mycam.update_xaddrs()

        address = await self._start_server(listen_ip)

        self.manager = await mycam.create_notification_manager(
            address=address,
            interval=timedelta(minutes=10),
            subscription_lost_callback=subscription_lost,
        )

        self.listening = True
        _LOGGER.debug("Listener started for %s", self._device.host)

    async def stop(self) -> None:
        """Stop the listener."""
        if not self.listening:
            return
        self.listening = False
        await self.site.stop()
        await self.runner.shutdown()

    async def _get_host_port(self, listen_ip: str | None) -> tuple[str, int]:
        def _create_socket(listen_ip: str | None) -> tuple[str, int]:
            if not listen_ip:
                res = check_output(["hostname", "-I"])  # noqa: S603, S607
                listen_ip, _, _ = res.decode().partition(" ")

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind((listen_ip, 0))
            port = sock.getsockname()[1]
            sock.close()
            return listen_ip, port

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _create_socket, listen_ip)

    async def _start_server(self, listen_ip: str | None) -> str:
        app = web.Application()
        app.add_routes([web.post("/", self._handle_event)])

        self.runner = web.AppRunner(app)
        await self.runner.setup()

        listen_ip, port = await self._get_host_port(listen_ip)

        self.site = web.TCPSite(self.runner, listen_ip, port)
        await self.site.start()

        _LOGGER.debug(
            "Listen handler for %s running on %s:%s", self._device.host, listen_ip, port
        )

        return f"http://{listen_ip}:{port}"
