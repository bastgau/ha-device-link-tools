"""Typing helpers for Home Assistant tests."""

from collections.abc import Callable, Coroutine
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

from aiohttp import ClientWebSocketResponse
from aiohttp.test_utils import TestClient

if TYPE_CHECKING:
    # Local import to avoid processing recorder module when running a
    # testcase which does not use the recorder.
    from homeassistant.components.recorder import Recorder # pyright: ignore[reportPrivateImportUsage]


class MockHAClientWebSocket(ClientWebSocketResponse):
    """Protocol for a wrapped ClientWebSocketResponse."""

    client: TestClient # pyright: ignore[reportMissingTypeArgument]
    send_json_auto_id: Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
    remove_device: Callable[[str, str], Coroutine[Any, Any, Any]]


type ClientSessionGenerator = Callable[..., Coroutine[Any, Any, TestClient]] # pyright: ignore[reportMissingTypeArgument]
type MqttMockPahoClient = MagicMock
"""MagicMock for `paho.mqtt.client.Client`"""
type MqttMockHAClient = MagicMock  # pylint: disable=invalid-name
"""MagicMock for `homeassistant.components.mqtt.MQTT`."""
type MqttMockHAClientGenerator = Callable[..., Coroutine[Any, Any, MqttMockHAClient]]  # pylint: disable=invalid-name
"""MagicMock generator for `homeassistant.components.mqtt.MQTT`."""
type RecorderInstanceContextManager = Callable[..., AbstractAsyncContextManager[Recorder]]
"""ContextManager for `homeassistant.components.recorder.Recorder`."""
type RecorderInstanceGenerator = Callable[..., Coroutine[Any, Any, Recorder]]
"""Instance generator for `homeassistant.components.recorder.Recorder`."""
type WebSocketGenerator = Callable[..., Coroutine[Any, Any, MockHAClientWebSocket]]
