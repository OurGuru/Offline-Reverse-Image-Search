"""
Theme management module for Offline Reverse Image Search application.
Handles theme selection and application of dark/light themes.
"""

from PyQt6 import QtCore
from PyQt6.QtWidgets import QComboBox, QWidget


class ThemeManager:
    """
    Manages application themes and styling.

    Attributes
    ----------
    settings : QtCore.QSettings
        Application settings object.
    parent_window : QWidget
        Reference to the main window for applying themes.
    theme_selector : QComboBox
        Theme selection combo box.
    """

    def __init__(self, settings: QtCore.QSettings, parent_window: QWidget):
        """
        Initialize the ThemeManager.

        Parameters
        ----------
        settings : QtCore.QSettings
            Application settings object.
        parent_window : QWidget
            Reference to the main window.
        """
        self.settings = settings
        self.parent_window = parent_window
        self.theme_selector = None
        self.current_theme = "Light"

        # Dark theme stylesheet
        self.dark_style = """
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTabWidget::pane {
                background-color: #3c3c3c;
                border: 1px solid #555555;
            }
            QTabBar::tab {
                background-color: #3c3c3c;
                color: #ffffff;
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #4a4a4a;
            }
            QTabBar::tab:hover {
                background-color: #525252;
            }
            QPushButton {
                background-color: #0d7377;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #14a085;
            }
            QPushButton:pressed {
                background-color: #0a5d61;
            }
            QPushButton:disabled {
                background-color: #4a4a4a;
                color: #888888;
            }
            QLineEdit, QTextEdit, QPlainTextEdit {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 4px;
                border-radius: 4px;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
                border: 1px solid #0d7377;
            }
            QLabel {
                color: #ffffff;
            }
            QGroupBox {
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QComboBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 4px;
                border-radius: 4px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 4px solid #ffffff;
                width: 0;
                height: 0;
                margin-right: 4px;
            }
            QSpinBox, QDoubleSpinBox {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                padding: 4px;
                border-radius: 4px;
            }
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                background-color: #4a4a4a;
                border: none;
                width: 16px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover,
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #525252;
            }
            QCheckBox {
                color: #ffffff;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                background-color: #3c3c3c;
                border: 1px solid #555555;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                background-color: #0d7377;
                border: 1px solid #0d7377;
            }
            QTableWidget {
                background-color: #3c3c3c;
                color: #ffffff;
                gridline-color: #555555;
                border: 1px solid #555555;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QTableWidget::item:selected {
                background-color: #0d7377;
            }
            QHeaderView::section {
                background-color: #4a4a4a;
                color: #ffffff;
                padding: 4px;
                border: 1px solid #555555;
            }
            QScrollBar:vertical {
                background-color: #3c3c3c;
                width: 12px;
                border: none;
            }
            QScrollBar::handle:vertical {
                background-color: #555555;
                min-height: 20px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #666666;
            }
            QScrollBar:horizontal {
                background-color: #3c3c3c;
                height: 12px;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background-color: #555555;
                min-width: 20px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal:hover {
                background-color: #666666;
            }
            QScrollBar::add-line, QScrollBar::sub-line {
                border: none;
                background: none;
            }
        """

    def setup_theme_selector(self, parent: QWidget, geometry: QtCore.QRect) -> QComboBox:
        """
        Create and setup the theme selector combo box.

        Parameters
        ----------
        parent : QWidget
            Parent widget for the combo box.
        geometry : QtCore.QRect
            Geometry for the combo box.

        Returns
        -------
        QComboBox
            The configured theme selector.
        """
        self.theme_selector = QComboBox(parent)
        self.theme_selector.setGeometry(geometry)
        self.theme_selector.setObjectName("theme_selector")
        self.theme_selector.addItems(["Light", "Dark"])

        # Connect signal
        self.theme_selector.currentTextChanged.connect(self.apply_theme)

        return self.theme_selector

    def apply_theme(self, theme_name: str) -> None:
        """
        Apply the selected theme to the application.

        Parameters
        ----------
        theme_name : str
            The name of the theme to apply ("Light" or "Dark").
        """
        self.current_theme = theme_name

        if theme_name == "Dark":
            self.parent_window.setStyleSheet(self.dark_style)
        else:
            # Light theme (default)
            self.parent_window.setStyleSheet("")

        # Save theme preference
        self.settings.setValue("theme", theme_name)

    def load_saved_theme(self) -> None:
        """
        Load and apply the saved theme from settings.
        """
        saved_theme = self.settings.value("theme", "Light")
        if self.theme_selector:
            self.theme_selector.setCurrentText(saved_theme)
        self.apply_theme(saved_theme)

    def get_current_theme(self) -> str:
        """
        Get the currently applied theme.

        Returns
        -------
        str
            The name of the current theme.
        """
        return self.current_theme

    def is_dark_theme(self) -> bool:
        """
        Check if dark theme is currently active.

        Returns
        -------
        bool
            True if dark theme is active, False otherwise.
        """
        return self.current_theme == "Dark"
