"""
Settings Bridge - Exposes configuration to QML
"""

import sys
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, pyqtProperty

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.config import ConfigManager
from src.utils.secrets import (
    get_provider_secrets,
    save_provider_secrets,
    SecretsError,
)


class SettingsBridge(QObject):
    """Bridge for settings/configuration."""

    # Signals
    settingsChanged = pyqtSignal()
    toomicsStatus = pyqtSignal(str, str)  # level ("ok"|"warn"|"err"), message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config_manager = ConfigManager()
    
    # Output Format
    @pyqtProperty(str, notify=settingsChanged)
    def outputFormat(self):
        return self._config_manager.get("output_format", "images")
    
    @outputFormat.setter
    def outputFormat(self, value: str):
        self._config_manager.set("output_format", value)
        self.settingsChanged.emit()
    
    # Keep Images
    @pyqtProperty(bool, notify=settingsChanged)
    def keepImages(self):
        return self._config_manager.get("keep_images", False)
    
    @keepImages.setter
    def keepImages(self, value: bool):
        self._config_manager.set("keep_images", value)
        self.settingsChanged.emit()
    
    # Download Path
    @pyqtProperty(str, notify=settingsChanged)
    def downloadPath(self):
        return self._config_manager.get("download_path", "downloads")
    
    @downloadPath.setter
    def downloadPath(self, value: str):
        self._config_manager.set("download_path", value)
        self.settingsChanged.emit()
    
    # Max Chapter Workers
    @pyqtProperty(int, notify=settingsChanged)
    def maxChapterWorkers(self):
        return self._config_manager.get("max_chapter_workers", 3)
    
    @maxChapterWorkers.setter
    def maxChapterWorkers(self, value: int):
        self._config_manager.set("max_chapter_workers", max(1, min(10, value)))
        self.settingsChanged.emit()
    
    # Max Image Workers
    @pyqtProperty(int, notify=settingsChanged)
    def maxImageWorkers(self):
        return self._config_manager.get("max_image_workers", 5)
    
    @maxImageWorkers.setter
    def maxImageWorkers(self, value: int):
        self._config_manager.set("max_image_workers", max(1, min(20, value)))
        self.settingsChanged.emit()
    
    # Theme (ink | neon | ember). Unknown values read back as "ink" and
    # are ignored on write.
    THEMES = ("ink", "neon", "ember")

    @pyqtProperty(str, notify=settingsChanged)
    def theme(self):
        value = self._config_manager.get("theme", "ink")
        return value if value in self.THEMES else "ink"

    @theme.setter
    def theme(self, value: str):
        if value not in self.THEMES or value == self.theme:
            return
        self._config_manager.set("theme", value)
        self.settingsChanged.emit()

    # GUI motion master switch
    @pyqtProperty(bool, notify=settingsChanged)
    def animationsEnabled(self):
        return bool(self._config_manager.get("animations_enabled", True))

    @animationsEnabled.setter
    def animationsEnabled(self, value: bool):
        self._config_manager.set("animations_enabled", bool(value))
        self.settingsChanged.emit()

    # Drifting background glow
    @pyqtProperty(bool, notify=settingsChanged)
    def ambientGlow(self):
        return bool(self._config_manager.get("ambient_glow", True))

    @ambientGlow.setter
    def ambientGlow(self, value: bool):
        self._config_manager.set("ambient_glow", bool(value))
        self.settingsChanged.emit()

    # Slots for QML
    @pyqtSlot(str, 'QVariant')
    def setValue(self, key: str, value):
        """Generic setter for any config value."""
        self._config_manager.set(key, value)
        self.settingsChanged.emit()
    
    @pyqtSlot(str, result='QVariant')
    def getValue(self, key: str):
        """Generic getter for any config value."""
        return self._config_manager.get(key)
    
    @pyqtSlot()
    def resetToDefaults(self):
        """Reset all settings to defaults."""
        self._config_manager.reset_to_defaults()
        self.settingsChanged.emit()
    
    @pyqtSlot(result=str)
    def getDownloadPathAbsolute(self):
        """Get absolute path to downloads folder."""
        path = Path(self._config_manager.get("download_path", "downloads"))
        return str(path.absolute())

    # ---- Toomics auth (cookie + UA stored in secrets.json) ---------

    def _toomics_secrets(self) -> dict:
        try:
            return get_provider_secrets("toomics") or {}
        except SecretsError as e:
            self.toomicsStatus.emit("err", f"secrets.json: {e}")
            return {}

    @pyqtProperty(str, notify=settingsChanged)
    def toomicsCookie(self):
        return (self._toomics_secrets().get("cookie") or "").strip()

    @pyqtProperty(str, notify=settingsChanged)
    def toomicsUserAgent(self):
        return (self._toomics_secrets().get("user_agent") or "").strip()

    @pyqtSlot(str, str)
    def saveToomicsAuth(self, cookie: str, user_agent: str):
        """Persist toomics cookie + UA to secrets.json."""
        try:
            save_provider_secrets(
                "toomics",
                {"cookie": (cookie or "").strip(),
                 "user_agent": (user_agent or "").strip()},
            )
            self.settingsChanged.emit()
            self.toomicsStatus.emit("ok", "Saved to secrets.json")
        except Exception as e:
            self.toomicsStatus.emit("err", f"Save failed: {e}")

    @pyqtSlot()
    def clearToomicsAuth(self):
        try:
            save_provider_secrets("toomics", {})
            self.settingsChanged.emit()
            self.toomicsStatus.emit("ok", "Cleared")
        except Exception as e:
            self.toomicsStatus.emit("err", f"Clear failed: {e}")

    @pyqtProperty(str, notify=settingsChanged)
    def toomicsEmail(self):
        return (self._toomics_secrets().get("email") or "").strip()

    @pyqtProperty(str, notify=settingsChanged)
    def toomicsPassword(self):
        # Returned to the GUI so the field can re-populate after restart.
        return self._toomics_secrets().get("password") or ""

    @pyqtSlot(str, str, bool)
    def loginToomics(self, email: str, password: str, keep_login: bool = True):
        """
        Run the email/password login flow, persist the resulting
        cookie + UA into secrets.json, and report status.

        Stores email + password in secrets.json so the user doesn't
        have to re-type on every cookie expiry. The file is mode 0600
        and gitignored — same protection as the cookie itself.
        """
        try:
            # Lazy import — keeps Qt startup fast.
            from src.utils.toomics_login import login as toomics_login

            # Pass any previously-saved cookies in so the login flow
            # *merges* server-issued refreshes on top of them. This
            # preserves persistent state cookies (GTOOMICSTOOMICS_USERTYPE,
            # tw_adultYN, etc.) that toomics sets on separate post-login
            # AJAX calls we don't replay — without those, VIP listings
            # come back empty.
            existing = (self._toomics_secrets().get("cookie") or "").strip()
            result = toomics_login(
                email=email.strip(),
                password=password,
                existing_cookies=existing or None,
            )
            save_provider_secrets(
                "toomics",
                {
                    "email": email.strip(),
                    "password": password,
                    "cookie": result.cookie,
                    "user_agent": result.user_agent,
                },
            )
            self.settingsChanged.emit()
            tier = (
                "VG (VIP)" if result.user_type == "VG"
                else result.user_type or "?"
            )
            self.toomicsStatus.emit(
                "ok",
                f"Logged in — session cookie saved. Account tier: {tier}",
            )
        except Exception as e:
            self.toomicsStatus.emit("err", f"Login failed: {e}")

    @pyqtSlot()
    def testToomicsAuth(self):
        """
        Hit a known-FREE toon listing with whatever cookie+UA is on
        disk and report whether the parser sees accessible chapters.
        Doesn't touch the network if no cookie is configured.
        """
        sec = self._toomics_secrets()
        if not (sec.get("cookie") or "").strip():
            self.toomicsStatus.emit(
                "warn", "No cookie saved yet — paste one and Save first."
            )
            return
        try:
            # Lazy import — keeps Qt startup fast.
            from src.providers.toomics import ToomicsProvider

            prov = ToomicsProvider()
            # toon 4698 is a stable mixed FREE+VIP series we used for
            # testing; works for both free-only and VIP-tier members.
            chapters = prov.get_chapters("4698")
            if chapters:
                self.toomicsStatus.emit(
                    "ok",
                    f"OK — saw {len(chapters)} accessible episodes on the "
                    "test toon.",
                )
            else:
                self.toomicsStatus.emit(
                    "warn",
                    "Logged-out response. Cookie may be expired or your "
                    "IP changed — re-paste from devtools.",
                )
        except Exception as e:
            self.toomicsStatus.emit("err", f"Test failed: {e}")
