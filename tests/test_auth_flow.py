"""Unit tests for the authenticate() flow.

Tests callback-server-primary flow, manual fallback on server failure,
request_token extraction from redirect URLs, and error handling.
"""

from unittest.mock import MagicMock, patch

import pytest
import typer

from src.cli.auth import _extract_request_token, authenticate


class TestExtractRequestToken:
    """Tests for _extract_request_token helper."""

    def test_bare_token(self):
        """A bare request_token is returned as-is."""
        assert _extract_request_token("abc123") == "abc123"

    def test_full_redirect_url(self):
        """request_token is extracted from a full redirect URL."""
        url = "https://127.0.0.1:61035/callback?request_token=xyz789"
        assert _extract_request_token(url) == "xyz789"

    def test_relative_url_with_query(self):
        """request_token is extracted from a relative URL with query."""
        url = "/?request_token=rel_token"
        assert _extract_request_token(url) == "rel_token"

    def test_empty_string(self):
        """Empty string returns None."""
        assert _extract_request_token("") is None

    def test_no_token(self):
        """URL without request_token returns None."""
        assert _extract_request_token("https://example.com/") is None

    def test_whitespace_token(self):
        """Whitespace around token is stripped."""
        assert _extract_request_token("  token_with_spaces  ") == "token_with_spaces"


class TestAuthenticateCallbackFlow:
    """Tests for authenticate() with callback server."""

    def test_callback_server_success(self, monkeypatch, tmp_path):
        """authenticate() succeeds via callback server when token is captured."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61041/callback")

        from src.core.settings import Settings

        config = Settings.from_env()

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {"access_token": "new_access_token"}

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer"
        ) as mock_server_cls:
            mock_server = MagicMock()
            mock_server.wait_for_token.return_value = "captured_token"
            mock_server_cls.return_value = mock_server

            with patch("rich.prompt.Prompt.ask") as mock_prompt:
                result = authenticate(config)

            # Callback server was used
            mock_server_cls.assert_called_once_with(config)
            mock_server.start.assert_called_once()
            mock_server.wait_for_token.assert_called_once()
            # Manual prompt was NOT used
            mock_prompt.assert_not_called()
            # Session was completed
            mock_kite.generate_session.assert_called_once_with(
                "captured_token", api_secret="env_secret"
            )
            assert result == mock_kite

    def test_callback_server_falls_back_to_manual(self, monkeypatch, tmp_path):
        """authenticate() falls back to manual Prompt.ask when callback server fails."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61042/callback")

        from src.core.settings import Settings

        config = Settings.from_env()

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {"access_token": "new_access_token"}

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer"
        ) as mock_server_cls:
            mock_server = MagicMock()
            mock_server.start.side_effect = OSError("port in use")
            mock_server_cls.return_value = mock_server

            with patch(
                "rich.prompt.Prompt.ask", return_value="manual_token"
            ) as mock_prompt:
                result = authenticate(config)

            # Callback server was attempted
            mock_server.start.assert_called_once()
            # Manual prompt was used as fallback
            mock_prompt.assert_called_once()
            # Session completed with manual token
            mock_kite.generate_session.assert_called_once_with(
                "manual_token", api_secret="env_secret"
            )
            assert result == mock_kite

    def test_callback_server_timeout_falls_back_to_manual(self, monkeypatch, tmp_path):
        """authenticate() falls back to manual when callback server times out."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61043/callback")

        from src.core.settings import Settings

        config = Settings.from_env()

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {"access_token": "new_access_token"}

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer"
        ) as mock_server_cls:
            mock_server = MagicMock()
            mock_server.wait_for_token.return_value = None  # timeout
            mock_server_cls.return_value = mock_server

            with patch(
                "rich.prompt.Prompt.ask", return_value="fallback_token"
            ) as mock_prompt:
                result = authenticate(config)

            mock_server.wait_for_token.assert_called_once()
            mock_prompt.assert_called_once()
            mock_kite.generate_session.assert_called_once_with(
                "fallback_token", api_secret="env_secret"
            )
            assert result == mock_kite

    def test_no_redirect_url_uses_manual_flow(self, monkeypatch, tmp_path):
        """authenticate() uses manual flow when no redirect URL is configured."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.delenv("KITE_REDIRECT_URL", raising=False)

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.kite_redirect_url is None

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {"access_token": "new_access_token"}

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer"
        ) as mock_server_cls, patch(
            "rich.prompt.Prompt.ask", return_value="manual_token"
        ):
            result = authenticate(config)

        # Callback server was NOT used
        mock_server_cls.assert_not_called()
        # Manual prompt was used
        mock_kite.generate_session.assert_called_once_with(
            "manual_token", api_secret="env_secret"
        )
        assert result == mock_kite

    def test_manual_entry_with_full_redirect_url(self, monkeypatch, tmp_path):
        """Manual entry accepts a full redirect URL and extracts request_token."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.delenv("KITE_REDIRECT_URL", raising=False)

        from src.core.settings import Settings

        config = Settings.from_env()

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {"access_token": "new_access_token"}

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "rich.prompt.Prompt.ask",
            return_value="https://127.0.0.1:61035/callback?request_token=url_token",
        ):
            result = authenticate(config)

        mock_kite.generate_session.assert_called_once_with(
            "url_token", api_secret="env_secret"
        )
        assert result == mock_kite

    def test_manual_entry_no_token_raises(self, monkeypatch, tmp_path):
        """Manual entry with no token raises typer.Exit."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.delenv("KITE_REDIRECT_URL", raising=False)

        from src.core.settings import Settings

        config = Settings.from_env()

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "rich.prompt.Prompt.ask", return_value=""
        ), pytest.raises(typer.Exit):
            authenticate(config)

    def test_existing_session_skips_login(self, monkeypatch, tmp_path):
        """authenticate() returns early when existing session is valid."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_ACCESS_TOKEN", "existing_token")
        monkeypatch.delenv("KITE_REDIRECT_URL", raising=False)

        from src.core.settings import Settings

        config = Settings.from_env()

        mock_kite = MagicMock()
        mock_kite.profile.return_value = {"user_id": "user123"}

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer"
        ) as mock_server_cls:
            result = authenticate(config)

        # No login flow initiated
        mock_kite.profile.assert_called_once()
        mock_server_cls.assert_not_called()
        mock_kite.generate_session.assert_not_called()
        assert result == mock_kite
