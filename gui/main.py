"""
Comix Downloader GUI - Main Entry Point
PyQt6 + QML Application
"""

import sys
import os
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase

from gui.app import build_engine
from src.utils.logger import setup_logging
from src.utils.config import ConfigManager

# Mirror CLI behaviour: honour `enable_logs` from config.json. The GUI was
# previously skipping this, so logger.info / logger.warning calls in
# providers were swallowed even with the toggle on.
setup_logging(enable=bool(ConfigManager().get("enable_logs", False)))


def load_fonts():
    """Load custom fonts."""
    fonts_dir = Path(__file__).parent / "resources" / "fonts"
    if fonts_dir.exists():
        for font_file in fonts_dir.glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font_file))


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Comix Downloader GUI")
    parser.add_argument(
        "--cpu", 
        action="store_true",
        help="Use software (CPU) rendering instead of GPU"
    )
    return parser.parse_args()


def main():
    """Main entry point for the GUI application."""
    args = parse_args()
    
    # Suppress Qt/QML warnings (they are harmless but noisy)
    # os.environ["QT_LOGGING_RULES"] = "*=false"  # Suppress all Qt debug/warning messages
    
    # Set rendering backend (must be set BEFORE QApplication)
    if args.cpu:
        # Full software rendering - works on all systems
        os.environ["QT_QUICK_BACKEND"] = "software"
        os.environ["QT_OPENGL"] = "software"
        os.environ["QSG_RENDER_LOOP"] = "basic"
        print("Using software (CPU) rendering")
    
    # Enable high DPI scaling
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    
    app = QApplication(sys.argv)
    app.setApplicationName("Comix Downloader")
    app.setOrganizationName("ComixDownloader")
    
    # Load fonts
    load_fonts()
    
    # Force Fusion style via environment variable to avoid DLL loading issues with native styles
    # This also avoids needing the PyQt6.QtQuickControls2 module which might be missing
    os.environ["QT_QUICK_CONTROLS_STYLE"] = "Fusion"
    
    # Bridges, context properties and main.qml (shared with the tests)
    engine, _bridges = build_engine()
    
    # Check if QML loaded successfully
    if not engine.rootObjects():
        print("Error: Failed to load QML")
        sys.exit(-1)
    
    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

