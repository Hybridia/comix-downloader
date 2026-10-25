"""
Configuration management - load/save settings from config.json.
"""

import json
from pathlib import Path
from typing import Any
from ..core.models import DownloadConfig, OutputFormat
from .logger import get_logger

logger = get_logger(__name__)


# Project root = parent of `src/`. Anchoring config.json here keeps the
# CLI and GUI on the same file regardless of the current working
# directory the user launched from.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config.json"


class ConfigManager:
    """Manages application configuration."""
    
    DEFAULT_CONFIG = {
        "output_format": "images",
        "keep_images": False,
        "enable_logs": False,
        "max_chapter_workers": 3,
        "max_image_workers": 5,
        "download_path": "downloads",
        "retry_count": 3,
        "retry_delay": 2.0,
        "chapters_display_limit": 20,  # 0 = show all
        # HTTP / anti-block settings
        "flaresolverr_url": "http://localhost:8191/v1",
        "flaresolverr_autostart": True,       # launch local FlareSolverr on first CF human check
        "flaresolverr_dir": "",               # "" = ~/Documents/FlareSolverr
        "flaresolverr_hidden": True,          # macOS: run its Chrome in the background
        "use_curl_cffi": True,                # browser fingerprinting via curl_cffi
        "impersonate": "chrome120",           # any curl_cffi impersonate target
        "requests_per_second_per_host": 4.0,  # adaptive starting rate
        "min_requests_per_second": 0.5,       # floor when throttled
        "max_requests_per_second": 8.0,       # ceiling when recovering
        "verify_ssl": True,                   # set false only if local CA store is broken
        # GUI look & motion
        "theme": "ink",                       # ink | neon | ember
        "animations_enabled": True,           # master switch for GUI motion
        "ambient_glow": True,                 # drifting background glow blobs
    }
    
    def __init__(self, config_path: str | Path | None = None):
        # Resolve to the project-root config by default so CLI and GUI
        # always read/write the same file. A caller can still override
        # by passing an explicit path.
        if config_path is None:
            self.config_path = _DEFAULT_CONFIG_PATH
        else:
            p = Path(config_path)
            self.config_path = p if p.is_absolute() else _PROJECT_ROOT / p
        self._config: dict[str, Any] = {}
        self.load()
    
    def load(self) -> None:
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
                logger.debug(f"Loaded config from {self.config_path}")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load config: {e}. Using defaults.")
                self._config = self.DEFAULT_CONFIG.copy()
        else:
            self._config = self.DEFAULT_CONFIG.copy()
            self.save()
    
    def save(self) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
            logger.debug(f"Saved config to {self.config_path}")
        except IOError as e:
            logger.error(f"Failed to save config: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self._config.get(key, self.DEFAULT_CONFIG.get(key, default))
    
    def set(self, key: str, value: Any) -> None:
        """Set a configuration value and save."""
        self._config[key] = value
        self.save()
    
    def get_download_config(self) -> DownloadConfig:
        """Get DownloadConfig from current settings."""
        return DownloadConfig(
            output_format=OutputFormat(self.get("output_format", "images")),
            keep_images=self.get("keep_images", False),
            enable_logs=self.get("enable_logs", False),
            max_chapter_workers=self.get("max_chapter_workers", 3),
            max_image_workers=self.get("max_image_workers", 5),
            download_path=self.get("download_path", "downloads"),
            retry_count=self.get("retry_count", 3),
            retry_delay=self.get("retry_delay", 2.0)
        )
    
    def update_from_download_config(self, config: DownloadConfig) -> None:
        """Update settings from DownloadConfig."""
        self._config.update({
            "output_format": config.output_format.value,
            "keep_images": config.keep_images,
            "enable_logs": config.enable_logs,
            "max_chapter_workers": config.max_chapter_workers,
            "max_image_workers": config.max_image_workers,
            "download_path": config.download_path,
            "retry_count": config.retry_count,
            "retry_delay": config.retry_delay
        })
        self.save()
    
    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        self._config = self.DEFAULT_CONFIG.copy()
        self.save()
    
    @property
    def all_settings(self) -> dict[str, Any]:
        """Get all current settings."""
        return {**self.DEFAULT_CONFIG, **self._config}
