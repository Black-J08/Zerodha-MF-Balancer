"""Unit tests for Settings class.

Tests .env loading priority, project root resolution, safe data_dir
resolution, output_dir/reports_dir under CWD, and access token storage
location tracking.
"""

from pathlib import Path

import pytest

from src.core.settings import (
    Settings,
    _is_inside_site_packages_or_venv,
    _resolve_data_dir,
    _resolve_env_path,
    _resolve_project_root,
)


class TestResolveProjectRoot:
    """Tests for _resolve_project_root()."""

    def test_from_mf_balancer_home_env_var(self, monkeypatch, tmp_path):
        """MF_BALANCER_HOME env var takes precedence."""
        monkeypatch.setenv("MF_BALANCER_HOME", str(tmp_path))
        assert _resolve_project_root() == tmp_path.resolve()

    def test_from_file_location(self, monkeypatch):
        """Derived from __file__ when no override and markers exist."""
        monkeypatch.delenv("MF_BALANCER_HOME", raising=False)
        # The actual project root should be resolved from __file__
        result = _resolve_project_root()
        assert result is not None
        assert (result / "pyproject.toml").exists() or (result / ".env").exists()

    def test_upward_search_from_cwd(self, monkeypatch, tmp_path):
        """Upward search from CWD finds project root with pyproject.toml."""
        monkeypatch.delenv("MF_BALANCER_HOME", raising=False)
        # Mock __file__ so __file__-based resolution doesn't find the real project root
        fake_file = tmp_path / "src" / "core" / "settings.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.write_text("")
        monkeypatch.setattr("src.core.settings.__file__", str(fake_file))
        # Create a fake project root with pyproject.toml
        fake_root = tmp_path / "fake_project"
        fake_root.mkdir()
        (fake_root / "pyproject.toml").write_text("")
        # Create a subdirectory and chdir there
        subdir = fake_root / "subdir"
        subdir.mkdir()
        monkeypatch.chdir(subdir)
        result = _resolve_project_root()
        assert result == fake_root.resolve()

    def test_fallback_to_cwd(self, monkeypatch, tmp_path):
        """Falls back to CWD when no markers found anywhere."""
        monkeypatch.delenv("MF_BALANCER_HOME", raising=False)
        # Mock __file__ so __file__-based resolution doesn't find the real project root
        fake_file = tmp_path / "src" / "core" / "settings.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.write_text("")
        monkeypatch.setattr("src.core.settings.__file__", str(fake_file))
        # Ensure no .env or pyproject.toml in tmp_path or its parents
        monkeypatch.chdir(tmp_path)
        result = _resolve_project_root()
        assert result == tmp_path.resolve()


class TestIsInsideSitePackagesOrVenv:
    """Tests for _is_inside_site_packages_or_venv()."""

    def test_inside_site_packages(self, tmp_path):
        """Returns True when path is inside site-packages."""
        site_packages = tmp_path / "lib" / "python3.13" / "site-packages"
        site_packages.mkdir(parents=True)
        target = site_packages / "mf_balancer" / "settings.py"
        assert _is_inside_site_packages_or_venv(target) is True

    def test_inside_venv(self, tmp_path):
        """Returns True when path is inside a virtual environment."""
        venv_root = tmp_path / ".venv"
        venv_root.mkdir()
        (venv_root / "pyvenv.cfg").write_text("")
        target = venv_root / "lib" / "python3.13" / "site-packages" / "mf_balancer"
        target.mkdir(parents=True)
        assert _is_inside_site_packages_or_venv(target) is True

    def test_not_inside_site_packages_or_venv(self, tmp_path):
        """Returns False for normal project directories."""
        target = tmp_path / "src" / "core" / "settings.py"
        target.parent.mkdir(parents=True)
        assert _is_inside_site_packages_or_venv(target) is False


class TestResolveEnvPath:
    """Tests for _resolve_env_path()."""

    def test_cwd_env_takes_precedence(self, monkeypatch, tmp_path):
        """Priority 1: .env in CWD is loaded even if project root .env exists."""
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("KITE_API_KEY=cwd_key\nKITE_API_SECRET=cwd_secret\n")
        result = _resolve_env_path()
        assert result == tmp_path / ".env"

    def test_skips_when_vars_in_environment(self, monkeypatch, tmp_path):
        """Priority 2: Skip .env search if credentials already in os.environ."""
        monkeypatch.chdir(tmp_path)
        # No .env in CWD
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        result = _resolve_env_path()
        assert result is None

    def test_loads_project_root_env_when_cwd_missing_and_vars_not_in_env(
        self, monkeypatch, tmp_path
    ):
        """Priority 3: Load .env from project root when CWD missing and vars not in env."""
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        # No .env in CWD
        project_root = tmp_path / "project_root"
        project_root.mkdir()
        (project_root / ".env").write_text(
            "KITE_API_KEY=root_key\nKITE_API_SECRET=root_secret\n"
        )
        monkeypatch.setattr("src.core.settings.PROJECT_ROOT", project_root.resolve())
        result = _resolve_env_path()
        assert result == project_root / ".env"

    def test_returns_none_when_no_env_anywhere(self, monkeypatch, tmp_path):
        """Priority 4: Returns None when no .env found and vars not in env."""
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        # No .env anywhere
        monkeypatch.setattr("src.core.settings.PROJECT_ROOT", tmp_path)
        result = _resolve_env_path()
        assert result is None


class TestResolveDataDir:
    """Tests for _resolve_data_dir()."""

    def test_under_env_dir_when_safe(self, tmp_path):
        """data_dir under env_dir when not inside site-packages/venv."""
        env_dir = tmp_path / "project"
        env_dir.mkdir()
        result = _resolve_data_dir(env_dir)
        assert result == env_dir / "data"
        assert result.is_absolute()

    def test_fallback_when_inside_site_packages(self, tmp_path, monkeypatch):
        """data_dir falls back to CWD/output/data when env_dir is inside site-packages."""
        site_packages = tmp_path / "lib" / "python3.13" / "site-packages"
        site_packages.mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        result = _resolve_data_dir(site_packages)
        assert result == tmp_path / "output" / "data"

    def test_fallback_when_inside_venv(self, tmp_path, monkeypatch):
        """data_dir falls back to CWD/output/data when env_dir is inside a venv."""
        venv_root = tmp_path / ".venv"
        venv_root.mkdir()
        (venv_root / "pyvenv.cfg").write_text("")
        monkeypatch.chdir(tmp_path)
        result = _resolve_data_dir(venv_root)
        assert result == tmp_path / "output" / "data"

    def test_fallback_when_env_dir_none(self, monkeypatch, tmp_path):
        """data_dir falls back to CWD/output/data when env_dir is None."""
        monkeypatch.chdir(tmp_path)
        result = _resolve_data_dir(None)
        assert result == tmp_path / "output" / "data"


class TestFromEnvLoadingPriority:
    """Tests for Settings.from_env() .env loading priority."""

    def test_loads_dotenv_from_cwd_when_present(self, monkeypatch, tmp_path):
        """Loads .env from CWD when present and vars not in environment."""
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "KITE_API_KEY=cwd_key\nKITE_API_SECRET=cwd_secret\n"
        )
        config = Settings.from_env()
        assert config.kite_api_key == "cwd_key"
        assert config.kite_api_secret == "cwd_secret"
        assert config.env_loaded is True
        assert config.env_path == str(tmp_path / ".env")

    def test_skips_dotenv_when_vars_in_environment(self, monkeypatch, tmp_path):
        """Skips .env loading when KITE_API_KEY and KITE_API_SECRET in os.environ."""
        monkeypatch.chdir(tmp_path)
        # No .env in CWD
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        config = Settings.from_env()
        assert config.kite_api_key == "env_key"
        assert config.kite_api_secret == "env_secret"
        assert config.env_loaded is False
        assert config.env_path is None

    def test_loads_dotenv_from_project_root_when_cwd_missing(
        self, monkeypatch, tmp_path
    ):
        """Loads .env from project root when CWD missing and vars not in env."""
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        # No .env in CWD
        project_root = tmp_path / "project_root"
        project_root.mkdir()
        (project_root / ".env").write_text(
            "KITE_API_KEY=root_key\nKITE_API_SECRET=root_secret\n"
        )
        monkeypatch.setattr("src.core.settings.PROJECT_ROOT", project_root.resolve())
        config = Settings.from_env()
        assert config.kite_api_key == "root_key"
        assert config.kite_api_secret == "root_secret"
        assert config.env_loaded is True
        assert config.env_path == str(project_root / ".env")

    def test_cwd_env_takes_precedence_over_project_root(self, monkeypatch, tmp_path):
        """CWD .env takes precedence over project root .env."""
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "KITE_API_KEY=cwd_key\nKITE_API_SECRET=cwd_secret\n"
        )
        project_root = tmp_path / "project_root"
        project_root.mkdir()
        (project_root / ".env").write_text(
            "KITE_API_KEY=root_key\nKITE_API_SECRET=root_secret\n"
        )
        monkeypatch.setattr("src.core.settings.PROJECT_ROOT", project_root.resolve())
        config = Settings.from_env()
        assert config.kite_api_key == "cwd_key"
        assert config.kite_api_secret == "cwd_secret"
        assert config.env_path == str(tmp_path / ".env")

    def test_skips_project_root_dotenv_when_vars_in_environment(
        self, monkeypatch, tmp_path
    ):
        """Skips project root .env when vars already in environment."""
        monkeypatch.chdir(tmp_path)
        # No .env in CWD
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        project_root = tmp_path / "project_root"
        project_root.mkdir()
        (project_root / ".env").write_text(
            "KITE_API_KEY=root_key\nKITE_API_SECRET=root_secret\n"
        )
        monkeypatch.setattr("src.core.settings.PROJECT_ROOT", project_root.resolve())
        config = Settings.from_env()
        assert config.kite_api_key == "env_key"
        assert config.kite_api_secret == "env_secret"
        assert config.env_loaded is False
        assert config.env_path is None

    def test_raises_when_vars_missing_and_no_dotenv_anywhere(
        self, monkeypatch, tmp_path
    ):
        """Raises ValueError when no env vars and no .env found anywhere."""
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        # No .env anywhere
        monkeypatch.setattr("src.core.settings.PROJECT_ROOT", tmp_path)
        with pytest.raises(ValueError, match="KITE_API_KEY and KITE_API_SECRET"):
            Settings.from_env()

    def test_raises_when_dotenv_incomplete(self, monkeypatch, tmp_path):
        """Raises ValueError when .env present but missing one required var."""
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("KITE_API_KEY=only_key\n")
        with pytest.raises(ValueError, match="KITE_API_KEY and KITE_API_SECRET"):
            Settings.from_env()


class TestSettingsDirectoryPaths:
    """Tests for Settings directory path attributes."""

    def test_data_dir_under_cwd_when_env_loaded_from_cwd(
        self, monkeypatch, tmp_path
    ):
        """data_dir under CWD when .env loaded from CWD."""
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "KITE_API_KEY=cwd_key\nKITE_API_SECRET=cwd_secret\n"
        )
        config = Settings.from_env()
        assert config.data_dir == str(tmp_path / "data")
        assert Path(config.data_dir).is_absolute()

    def test_data_dir_under_project_root_when_env_loaded_from_project_root(
        self, monkeypatch, tmp_path
    ):
        """data_dir under project root when .env loaded from project root."""
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        project_root = tmp_path / "project_root"
        project_root.mkdir()
        (project_root / ".env").write_text(
            "KITE_API_KEY=root_key\nKITE_API_SECRET=root_secret\n"
        )
        monkeypatch.setattr("src.core.settings.PROJECT_ROOT", project_root.resolve())
        config = Settings.from_env()
        assert config.data_dir == str(project_root / "data")
        assert Path(config.data_dir).is_absolute()

    def test_data_dir_fallback_when_no_env_loaded(self, monkeypatch, tmp_path):
        """data_dir falls back to CWD/output/data when no .env loaded."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        config = Settings.from_env()
        assert config.data_dir == str(tmp_path / "output" / "data")
        assert Path(config.data_dir).is_absolute()

    def test_data_dir_is_always_absolute(self, monkeypatch, tmp_path):
        """data_dir is always an absolute path."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        config = Settings.from_env()
        assert Path(config.data_dir).is_absolute()

    def test_output_dir_is_absolute_under_cwd(self, monkeypatch, tmp_path):
        """output_dir is absolute and under CWD."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        config = Settings.from_env()
        assert config.output_dir == str(tmp_path / "output")
        assert Path(config.output_dir).is_absolute()

    def test_reports_dir_is_absolute_under_cwd_output(
        self, monkeypatch, tmp_path
    ):
        """reports_dir is absolute and under CWD/output."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        config = Settings.from_env()
        assert config.reports_dir == str(tmp_path / "output" / "reports")
        assert Path(config.reports_dir).is_absolute()


class TestSettingsEnvTracking:
    """Tests for Settings env_loaded and env_path attributes."""

    def test_env_loaded_true_when_dotenv_loaded_from_cwd(
        self, monkeypatch, tmp_path
    ):
        """env_loaded is True when .env loaded from CWD."""
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "KITE_API_KEY=cwd_key\nKITE_API_SECRET=cwd_secret\n"
        )
        config = Settings.from_env()
        assert config.env_loaded is True
        assert config.env_path == str(tmp_path / ".env")

    def test_env_loaded_false_when_vars_from_environment(
        self, monkeypatch, tmp_path
    ):
        """env_loaded is False when vars come from environment."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        config = Settings.from_env()
        assert config.env_loaded is False
        assert config.env_path is None

    def test_env_path_points_to_project_root_when_loaded_from_there(
        self, monkeypatch, tmp_path
    ):
        """env_path points to project root .env when loaded from there."""
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        project_root = tmp_path / "project_root"
        project_root.mkdir()
        (project_root / ".env").write_text(
            "KITE_API_KEY=root_key\nKITE_API_SECRET=root_secret\n"
        )
        monkeypatch.setattr("src.core.settings.PROJECT_ROOT", project_root.resolve())
        config = Settings.from_env()
        assert config.env_loaded is True
        assert config.env_path == str(project_root / ".env")


class TestRedirectUrl:
    """Tests for KITE_REDIRECT_URL parsing, derivation, and validation."""

    def test_redirect_url_loaded_from_env(self, monkeypatch, tmp_path):
        """KITE_REDIRECT_URL is loaded from environment variables."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61035/callback")

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.kite_redirect_url == "http://127.0.0.1:61035/callback"

    def test_redirect_url_loaded_from_dotenv(self, monkeypatch, tmp_path):
        """KITE_REDIRECT_URL is loaded from .env file."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.delenv("KITE_REDIRECT_URL", raising=False)
        (tmp_path / ".env").write_text(
            "KITE_API_KEY=cwd_key\n"
            "KITE_API_SECRET=cwd_secret\n"
            "KITE_REDIRECT_URL=http://127.0.0.1:61035/callback\n"
        )

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.kite_redirect_url == "http://127.0.0.1:61035/callback"

    def test_redirect_url_none_when_not_set(self, monkeypatch, tmp_path):
        """kite_redirect_url is None when KITE_REDIRECT_URL is not set."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("KITE_API_KEY", raising=False)
        monkeypatch.delenv("KITE_API_SECRET", raising=False)
        monkeypatch.delenv("KITE_REDIRECT_URL", raising=False)
        (tmp_path / ".env").write_text(
            "KITE_API_KEY=env_key\nKITE_API_SECRET=env_secret\n"
        )

        import src.core.settings as config_module
        monkeypatch.setattr(
            config_module, "PROJECT_ROOT", tmp_path.resolve()
        )

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.kite_redirect_url is None

    def test_derived_callback_host(self, monkeypatch, tmp_path):
        """kite_callback_host is derived from the redirect URL."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61035/callback")

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.kite_callback_host == "127.0.0.1"

    def test_derived_callback_port(self, monkeypatch, tmp_path):
        """kite_callback_port is derived from the redirect URL exactly as configured."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61035/callback")

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.kite_callback_port == 61035

    def test_derived_callback_path(self, monkeypatch, tmp_path):
        """kite_callback_path is derived from the redirect URL."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61035/callback")

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.kite_callback_path == "/callback"

    def test_redirect_url_invalid_scheme_raises(self, monkeypatch, tmp_path):
        """Invalid scheme raises ValueError."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "ftp://127.0.0.1:61035/callback")

        from src.core.settings import Settings

        with pytest.raises(ValueError, match="must use http or https scheme"):
            Settings.from_env()

    def test_redirect_url_missing_hostname_raises(self, monkeypatch, tmp_path):
        """Missing hostname raises ValueError."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://:61035/callback")

        from src.core.settings import Settings

        with pytest.raises(ValueError, match="must include a hostname"):
            Settings.from_env()

    def test_redirect_url_missing_port_raises(self, monkeypatch, tmp_path):
        """Missing explicit port raises ValueError."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1/callback")

        from src.core.settings import Settings

        with pytest.raises(ValueError, match="must include an explicit port"):
            Settings.from_env()

    def test_redirect_url_missing_path_raises(self, monkeypatch, tmp_path):
        """Missing path raises ValueError."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61035")

        from src.core.settings import Settings

        with pytest.raises(ValueError, match="must include a path"):
            Settings.from_env()

    def test_redirect_url_root_path_accepted(self, monkeypatch, tmp_path):
        """Path of just '/' is accepted."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("KITE_API_KEY", "env_key")
        monkeypatch.setenv("KITE_API_SECRET", "env_secret")
        monkeypatch.setenv("KITE_REDIRECT_URL", "http://127.0.0.1:61035/")

        from src.core.settings import Settings

        config = Settings.from_env()
        assert config.kite_redirect_url == "http://127.0.0.1:61035/"
        assert config.kite_callback_path == "/"
