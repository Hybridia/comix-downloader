"""
Bridge module for Python↔QML communication
"""
from .manga_bridge import MangaBridge
from .download_bridge import DownloadBridge
from .settings_bridge import SettingsBridge
from .library_bridge import LibraryBridge

__all__ = ["MangaBridge", "DownloadBridge", "SettingsBridge", "LibraryBridge"]
