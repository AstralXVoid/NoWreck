from __future__ import annotations

from pathlib import Path

from nowreck.storage.config import NowreckConfig

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNowreckConfigPaths:
    def test_default_base_is_cwd(self) -> None:
        cfg = NowreckConfig()
        assert cfg.config_path == Path.cwd() / ".nowreck" / "config.json"

    def test_custom_base_dir(self, tmp_path: Path) -> None:
        cfg = NowreckConfig(tmp_path)
        assert cfg.config_path == (tmp_path / ".nowreck" / "config.json").resolve()


class TestNowreckConfigExists:
    def test_not_exists_initially(self, tmp_path: Path) -> None:
        cfg = NowreckConfig(tmp_path)
        assert cfg.exists() is False

    def test_exists_after_save(self, tmp_path: Path) -> None:
        cfg = NowreckConfig(tmp_path)
        cfg.save({})
        assert cfg.exists() is True


class TestNowreckConfigSaveAndLoad:
    def test_save_then_load_roundtrip(self, tmp_path: Path) -> None:
        cfg = NowreckConfig(tmp_path)
        original = {"api_key": "sk-test123", "model": "gpt-4"}
        cfg.save(original)
        loaded = cfg.load()
        assert loaded == original

    def test_load_empty_dict_when_no_file(self, tmp_path: Path) -> None:
        cfg = NowreckConfig(tmp_path)
        assert cfg.load() == {}


class TestNowreckConfigCorruptedJson:
    def test_load_corrupted_json_returns_empty_dict(self, tmp_path: Path) -> None:
        """If the config file contains invalid JSON (e.g. truncated write,
        manual editing error), load() should return {} instead of crashing
        with a JSONDecodeError."""
        cfg = NowreckConfig(tmp_path)
        # Write a directory and a corrupted file
        cfg._config_dir.mkdir(parents=True, exist_ok=True)
        cfg._config_path.write_text("{invalid json content!!!", encoding="utf-8")

        result = cfg.load()
        assert result == {}

    def test_load_corrupted_json_does_not_overwrite_file(self, tmp_path: Path) -> None:
        """load() on corrupted JSON returns {} but does NOT touch the file
        on disk — only save() writes."""
        cfg = NowreckConfig(tmp_path)
        cfg._config_dir.mkdir(parents=True, exist_ok=True)
        cfg._config_path.write_text("{corrupted", encoding="utf-8")

        # load() should return {} but leave the file alone
        cfg.load()

        # File still contains the original corrupt data
        assert cfg._config_path.read_text(encoding="utf-8") == "{corrupted"

    def test_save_after_corrupted_load_roundtrip(self, tmp_path: Path) -> None:
        """A typical recovery flow: load corrupted config (gets {}),
        set new values, save."""
        cfg = NowreckConfig(tmp_path)
        cfg._config_dir.mkdir(parents=True, exist_ok=True)
        cfg._config_path.write_text("{corrupted", encoding="utf-8")

        # Act as a CLI command would: load (gets {}), update, save
        data = cfg.load()
        assert data == {}
        data["api_key"] = "sk-recovered"
        cfg.save(data)

        # Next load should return the new data
        loaded = cfg.load()
        assert loaded == {"api_key": "sk-recovered"}


class TestNowreckConfigEmptyFile:
    def test_load_empty_file_returns_empty_dict(self, tmp_path: Path) -> None:
        """A completely empty config file should not crash."""
        cfg = NowreckConfig(tmp_path)
        cfg._config_dir.mkdir(parents=True, exist_ok=True)
        cfg._config_path.write_text("", encoding="utf-8")

        result = cfg.load()
        assert result == {}
