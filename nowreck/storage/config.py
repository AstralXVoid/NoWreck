from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class NowreckConfig:
    """Minimal configuration manager for Nowreck.

    Stores configuration as a JSON file under the ``.nowreck/`` directory
    in the current working directory. This is a Phase 1 foundation only
    and will be extended when model connection (Phase 7) is implemented.

    Attributes:
        CONFIG_DIR: Name of the config directory (``.nowreck``).
        CONFIG_FILE: Name of the config file (``config.json``).
    """

    CONFIG_DIR = ".nowreck"
    CONFIG_FILE = "config.json"

    def __init__(self, base_dir: str | Path | None = None) -> None:
        """Initialize the config manager.

        Args:
            base_dir: The directory under which ``.nowreck/`` lives.
                Defaults to the current working directory.
        """
        self._base_dir = Path(base_dir).resolve() if base_dir else Path.cwd()
        self._config_dir = self._base_dir / self.CONFIG_DIR
        self._config_path = self._config_dir / self.CONFIG_FILE

    @property
    def config_path(self) -> Path:
        """Full path to the configuration file."""
        return self._config_path

    def exists(self) -> bool:
        """Check whether a configuration file already exists."""
        return self._config_path.exists()

    def load(self) -> dict[str, object]:
        """Load configuration from disk.

        Returns an empty dict if no configuration file exists yet.
        Returns an empty dict and logs a warning if the config file
        contains invalid JSON (e.g. after a crash or manual edit error).
        """
        if self._config_path.exists():
            try:
                return json.loads(self._config_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError, OSError):
                logger.warning(
                    "Corrupted config file, resetting: %s", self._config_path
                )
        return {}

    def save(self, data: dict[str, object]) -> None:
        """Save configuration to disk, creating the directory if needed.

        Args:
            data: A dictionary of configuration key-value pairs.
        """
        self._config_dir.mkdir(parents=True, exist_ok=True)

        # Create/open with owner-only permissions from the start —
        # writing first and chmodding after would expose the key to a
        # brief race window under permissive umasks.  fchmod() is also
        # required because the open() mode argument applies only when
        # the file is *created*; a pre-existing (loose) file from an
        # older version must be tightened on every save.
        payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
        fd = os.open(
            self._config_path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
        except BaseException:
            # Never leave a partially-written or mis-permissioned file
            # behind on failure.
            self._config_path.unlink(missing_ok=True)
            raise
