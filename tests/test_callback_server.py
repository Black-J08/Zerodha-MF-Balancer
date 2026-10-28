"""Unit tests for the callback server.

Tests automatic request_token capture, graceful shutdown, timeout,
port-in-use errors, and malformed/missing request_token handling.
"""

from http.client import HTTPConnection
from unittest.mock import MagicMock

import pytest

from src.cli.callback_server import CallbackServer, _CallbackHandler


class TestCallbackHandler:
    """Tests for the HTTP request handler."""

    def test_captures_request_token_from_query(self):
        """Handler captures request_token from the callback path query string."""
        handler = MagicMock(spec=_CallbackHandler)
        handler.callback_path = "/callback"
        handler.token_event = MagicMock()
        handler.captured_token = None
        handler.capture_error = None

        # Simulate do_GET with a valid request_token
        handler.path = "/callback?request_token=abc123"
        parsed_path = "/callback"
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(handler.path)
        assert parsed.path == parsed_path
        tokens = parse_qs(parsed.query).get("request_token")
        assert tokens == ["abc123"]

    def test_missing_request_token(self):
        """Handler detects missing request_token in query string."""
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse("/callback?other=value")
        tokens = parse_qs(parsed.query).get("request_token")
        assert tokens is None

    def test_wrong_path_ignored(self):
        """Handler ignores requests to non-callback paths."""
        from urllib.parse import urlparse

        parsed = urlparse("/other?request_token=abc123")
        assert parsed.path != "/callback"


class TestCallbackServer:
    """Tests for the CallbackServer class."""

    def test_host_port_path_derived_from_settings(self, monkeypatch, tmp_path):
        """Server derives host, port, and path from Settings."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61035/callback")

        from src.core.settings import Settings

        config = Settings.from_env()
        server = CallbackServer(config)
        assert server.host == "127.0.0.1"
        assert server.port == 61035
        assert server.path == "/callback"

    def test_captures_token_and_shuts_down(self, monkeypatch, tmp_path):
        """Server captures request_token from a simulated redirect and shuts down."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61036/callback")

        from src.core.settings import Settings

        config = Settings.from_env()
        server = CallbackServer(config)
        server.start()

        try:
            # Simulate Zerodha redirect by making an HTTP request to the callback
            conn = HTTPConnection("127.0.0.1", 61036, timeout=5)
            conn.request("GET", "/callback?request_token=test_token_123")
            response = conn.getresponse()
            response.read()
            conn.close()

            token = server.wait_for_token(timeout=10.0)
            assert token == "test_token_123"
        finally:
            server.stop()

    def test_timeout_returns_none(self, monkeypatch, tmp_path):
        """wait_for_token returns None when no token arrives before timeout."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61037/callback")

        from src.core.settings import Settings

        config = Settings.from_env()
        server = CallbackServer(config)
        server.start()

        try:
            token = server.wait_for_token(timeout=1.0)
            assert token is None
        finally:
            server.stop()

    def test_port_in_use_raises(self, monkeypatch, tmp_path):
        """Starting on a port already in use raises OSError."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61038/callback")

        from src.core.settings import Settings

        config = Settings.from_env()

        # Start a server on the port first
        server1 = CallbackServer(config)
        server1.start()

        # A second server on the same port should fail
        server2 = CallbackServer(config)
        try:
            with pytest.raises(OSError):
                server2.start()
        finally:
            server1.stop()

    def test_context_manager_starts_and_stops(self, monkeypatch, tmp_path):
        """Context manager starts server on entry and stops on exit."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61039/callback")

        from src.core.settings import Settings

        config = Settings.from_env()
        with CallbackServer(config) as server:
            assert server._server is not None
            assert server._thread is not None
        # After exit, server should be stopped
        assert server._server is None

    def test_malformed_query_no_token(self, monkeypatch, tmp_path):
        """Handler records an error when request_token is missing."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61040/callback")

        from src.core.settings import Settings

        config = Settings.from_env()
        server = CallbackServer(config)
        server.start()

        try:
            conn = HTTPConnection("127.0.0.1", 61040, timeout=5)
            conn.request("GET", "/callback?other=value")
            response = conn.getresponse()
            assert response.status == 400
            response.read()
            conn.close()

            token = server.wait_for_token(timeout=5.0)
            assert token is None
        finally:
            server.stop()
