"""Unit tests for auth token storage location.

Tests that the Kite access token is written to the correct .env file:
- The .env that was loaded (CWD or project root), or
- A new .env in CWD when no .env was loaded.
"""

from unittest.mock import MagicMock, patch

from src.cli.auth import authenticate


class TestAuthTokenStorage:
    """Tests for where authenticate() writes the access token."""

    def test_writes_token_to_cwd_env_when_dotenv_loaded_from_cwd(
        self, monkeypatch, tmp_path
    ):
        """Token written to CWD .env when .env was loaded from CWD."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "KITE_API_KEY=cwd_key\nKITE_API_SECRET=cwd_secret\n"
        )

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.env_loaded is True
        assert config.env_path == str(tmp_path / ".env")

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {
            "access_token": "new_access_token"
        }

        mock_server = MagicMock()
        mock_server.wait_for_token.return_value = "captured_token"

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer", return_value=mock_server
        ), patch(
            "rich.prompt.Prompt.ask", return_value="request_token_123"
        ):
            authenticate(config)

        # Verify token was written to CWD .env
        env_content = (tmp_path / ".env").read_text()
        assert "KITE_ACCESS_TOKEN=new_access_token" in env_content

    def test_writes_token_to_project_root_env_when_dotenv_loaded_from_project_root(
        self, monkeypatch, tmp_path
    ):
        """Token written to project root .env when .env loaded from project root."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        project_root = tmp_path / "project_root"
        project_root.mkdir()
        (project_root / ".env").write_text(
            "KITE_API_KEY=root_key\nKITE_API_SECRET=root_secret\n"
        )

        import src.core.settings as config_module
        from src.core.settings import Settings

        monkeypatch.setattr(
            config_module, "PROJECT_ROOT", project_root.resolve()
        )
        config = Settings.from_env()
        assert config.env_loaded is True
        assert config.env_path == str(project_root / ".env")

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {
            "access_token": "new_access_token"
        }

        mock_server = MagicMock()
        mock_server.wait_for_token.return_value = "captured_token"

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer", return_value=mock_server
        ), patch(
            "rich.prompt.Prompt.ask", return_value="request_token_123"
        ):
            authenticate(config)

        # Verify token was written to project root .env
        env_content = (project_root / ".env").read_text()
        assert "KITE_ACCESS_TOKEN=new_access_token" in env_content

    def test_writes_token_to_cwd_env_when_no_dotenv_loaded(
        self, monkeypatch, tmp_path
    ):
        """Token written to new CWD .env when no .env was loaded (vars from env)."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.env_loaded is False
        assert config.env_path is None

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {
            "access_token": "new_access_token"
        }

        mock_server = MagicMock()
        mock_server.wait_for_token.return_value = "captured_token"

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer", return_value=mock_server
        ), patch(
            "rich.prompt.Prompt.ask", return_value="request_token_123"
        ):
            authenticate(config)

        # Verify token was written to new CWD .env
        env_content = (tmp_path / ".env").read_text()
        assert "KITE_ACCESS_TOKEN=new_access_token" in env_content

    def test_creates_new_cwd_env_when_none_exists(self, monkeypatch, tmp_path):
        """Creates new .env in CWD when none exists and vars from environment."""
        monkeypatch.chdir(tmp_path)
        assert not (tmp_path / ".env").exists()
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.env_loaded is False

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {
            "access_token": "new_access_token"
        }

        mock_server = MagicMock()
        mock_server.wait_for_token.return_value = "captured_token"

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer", return_value=mock_server
        ), patch(
            "rich.prompt.Prompt.ask", return_value="request_token_123"
        ):
            authenticate(config)

        # Verify new .env was created in CWD
        assert (tmp_path / ".env").exists()
        env_content = (tmp_path / ".env").read_text()
        assert "KITE_ACCESS_TOKEN=new_access_token" in env_content

    def test_appends_to_existing_cwd_env(self, monkeypatch, tmp_path):
        """Appends token line to existing CWD .env without overwriting."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "KITE_API_KEY=env_key\nKITE_API_SECRET=env_secret\n"
        )
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.env_loaded is True
        assert config.env_path == str(tmp_path / ".env")

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {
            "access_token": "new_access_token"
        }

        mock_server = MagicMock()
        mock_server.wait_for_token.return_value = "captured_token"

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer", return_value=mock_server
        ), patch(
            "rich.prompt.Prompt.ask", return_value="request_token_123"
        ):
            authenticate(config)

        # Verify existing content preserved and token appended
        env_content = (tmp_path / ".env").read_text()
        assert "KITE_API_KEY=env_key" in env_content
        assert "KITE_API_SECRET=env_secret" in env_content
        assert "KITE_ACCESS_TOKEN=new_access_token" in env_content

    def test_updating_existing_token_does_not_create_duplicate(
        self, monkeypatch, tmp_path
    ):
        """Updating an existing KITE_ACCESS_TOKEN does not append a duplicate line."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "KITE_API_KEY=env_key\nKITE_API_SECRET=env_secret\nKITE_ACCESS_TOKEN=old_token\n"
        )
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.env_loaded is True
        assert config.env_path == str(tmp_path / ".env")

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {
            "access_token": "new_access_token"
        }

        mock_server = MagicMock()
        mock_server.wait_for_token.return_value = "captured_token"

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer", return_value=mock_server
        ), patch(
            "rich.prompt.Prompt.ask", return_value="request_token_123"
        ):
            authenticate(config)

        # Verify exactly one KITE_ACCESS_TOKEN line exists with the new value
        env_content = (tmp_path / ".env").read_text()
        token_lines = [
            line for line in env_content.splitlines() if line.startswith("KITE_ACCESS_TOKEN=")
        ]
        assert len(token_lines) == 1, f"Expected 1 token line, got {len(token_lines)}: {token_lines}"
        assert token_lines[0] == "KITE_ACCESS_TOKEN=new_access_token"
        assert "KITE_API_KEY=env_key" in env_content
        assert "KITE_API_SECRET=env_secret" in env_content

    def test_first_time_token_creation_when_key_absent(
        self, monkeypatch, tmp_path
    ):
        """When no KITE_ACCESS_TOKEN exists, a single line is added."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "KITE_API_KEY=env_key\nKITE_API_SECRET=env_secret\n"
        )
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.env_loaded is True
        assert config.env_path == str(tmp_path / ".env")

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {
            "access_token": "new_access_token"
        }

        mock_server = MagicMock()
        mock_server.wait_for_token.return_value = "captured_token"

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer", return_value=mock_server
        ), patch(
            "rich.prompt.Prompt.ask", return_value="request_token_123"
        ):
            authenticate(config)

        # Verify exactly one KITE_ACCESS_TOKEN line exists with the new value
        env_content = (tmp_path / ".env").read_text()
        token_lines = [
            line for line in env_content.splitlines() if line.startswith("KITE_ACCESS_TOKEN=")
        ]
        assert len(token_lines) == 1, f"Expected 1 token line, got {len(token_lines)}: {token_lines}"
        assert token_lines[0] == "KITE_ACCESS_TOKEN=new_access_token"

    def test_preserves_other_env_entries_on_token_update(
        self, monkeypatch, tmp_path
    ):
        """Updating KITE_ACCESS_TOKEN preserves all other .env entries unchanged."""
        monkeypatch.chdir(tmp_path)
        original_env = (
            "# Zerodha Kite Connect API credentials (required)\n"
            "KITE_API_KEY=env_key\n"
            "KITE_API_SECRET=env_secret\n"
            "\n"
            "# Zerodha Kite Connect access token (optional, auto-populated after login)\n"
            "KITE_ACCESS_TOKEN=old_token\n"
        )
        (tmp_path / ".env").write_text(original_env)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.env_loaded is True
        assert config.env_path == str(tmp_path / ".env")

        mock_kite = MagicMock()
        mock_kite.profile.side_effect = Exception("session expired")
        mock_kite.login_url.return_value = "https://example.com/login"
        mock_kite.generate_session.return_value = {
            "access_token": "new_access_token"
        }

        mock_server = MagicMock()
        mock_server.wait_for_token.return_value = "captured_token"

        with patch("src.cli.auth.KiteConnect", return_value=mock_kite), patch(
            "src.cli.auth.CallbackServer", return_value=mock_server
        ), patch(
            "rich.prompt.Prompt.ask", return_value="request_token_123"
        ):
            authenticate(config)

        # Verify token updated and all other entries preserved exactly
        env_content = (tmp_path / ".env").read_text()
        expected_env = (
            "# Zerodha Kite Connect API credentials (required)\n"
            "KITE_API_KEY=env_key\n"
            "KITE_API_SECRET=env_secret\n"
            "\n"
            "# Zerodha Kite Connect access token (optional, auto-populated after login)\n"
            "KITE_ACCESS_TOKEN=new_access_token\n"
        )
        assert env_content == expected_env, (
            f"Expected:\n{expected_env!r}\nGot:\n{env_content!r}"
        )
