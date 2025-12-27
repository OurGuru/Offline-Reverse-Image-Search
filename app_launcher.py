"""
Optimized launcher for Offline Reverse Image Search
Loads only necessary modules to reduce memory footprint
"""

import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# Optimize imports - load only what's needed
def main():
    # Lazy load heavy modules
    from PyQt6 import QtGui
    from PyQt6.QtWidgets import QApplication

    # Import main window
    from app import MyWindow

    # Create application
    app = QApplication(sys.argv)

    # Quick splash screen
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QSplashScreen

    # Load logo
    logo_path = "logo.png"
    if os.path.exists(logo_path):
        pixmap = QtGui.QPixmap(logo_path)
        splash = QSplashScreen(pixmap)
        splash.show()
        app.processEvents()
    else:
        splash = None

    # Create main window
    window = MyWindow()
    window.show()

    # Close splash after short delay
    if splash:
        QTimer.singleShot(1000, splash.close)

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
