"""
Settings management functionality for the Offline Reverse Image Search application.
"""

import os
from typing import Any

from PyQt6 import QtCore, QtGui

from ..core.constants import (
    DEFAULT_SEARCH_RANGE,
    MAX_SEARCH_RANGE,
    MIN_SEARCH_RANGE,
    ErrorMessages,
)


class SettingsManager:
    """Manages application settings and configuration."""

    def __init__(self, parent):
        self.parent = parent
        self.settings = None
        self.initialize_settings()

    def initialize_settings(self) -> None:
        """Initialize settings file and configuration."""
        settings_path = os.path.join(self.parent.dir_path, "settings.ini")

        if not os.path.isfile(settings_path):
            with open(settings_path, "w", encoding="utf-8") as f:
                vp_tree_path = os.path.join(self.parent.dir_path, "VPtree.pickle")
                hashing_path = os.path.join(self.parent.dir_path, "Hashing.pickle")
                # Convert to forward slashes for INI file compatibility
                vp_tree_path = vp_tree_path.replace(os.sep, "/")
                hashing_path = hashing_path.replace(os.sep, "/")
                f.write(f"[General]\nVPTree={vp_tree_path}\nHashing={hashing_path}\nsearch_range=6")
            print("no settings file, created one")

        self.settings = QtCore.QSettings(settings_path, QtCore.QSettings.Format.IniFormat)
        self.parent.settings = self.settings

    def validate_and_load_settings(self) -> None:
        """
        Validate and load settings with proper error handling.
        """
        # Validate VP-Tree path
        vp_tree_path = self.settings.value("VPTree", "")
        if vp_tree_path:
            self.parent.vp_tree_dir.setText(vp_tree_path)
        else:
            default_path = os.path.join(self.parent.dir_path, "VPtree.pickle")
            self.parent.vp_tree_dir.setText(default_path)
            self.settings.setValue("VPTree", default_path)
            self.parent.log_box_append("VP-Tree path not found in settings, using default")

        # Validate Hashing path
        hashing_path = self.settings.value("Hashing", "")
        if hashing_path:
            self.parent.hash_dir.setText(hashing_path)
        else:
            default_path = os.path.join(self.parent.dir_path, "Hashing.pickle")
            self.parent.hash_dir.setText(default_path)
            self.settings.setValue("Hashing", default_path)
            self.parent.log_box_append("Hashing path not found in settings, using default")

        # Validate search range
        try:
            search_range = self.settings.value("search_range", str(DEFAULT_SEARCH_RANGE))
            search_range_int = int(search_range)
            # Validate range bounds
            if search_range_int < MIN_SEARCH_RANGE:
                search_range_int = MIN_SEARCH_RANGE
                self.parent.log_box_append(
                    f"Search range too low, setting to minimum ({MIN_SEARCH_RANGE})"
                )
            elif search_range_int > MAX_SEARCH_RANGE:
                search_range_int = MAX_SEARCH_RANGE
                self.parent.log_box_append(
                    f"Search range too high, setting to maximum ({MAX_SEARCH_RANGE})"
                )
            self.parent.search_range.setValue(search_range_int)
            self.parent.search_range.setMinimum(MIN_SEARCH_RANGE)
            self.parent.search_range.setMaximum(MAX_SEARCH_RANGE)
        except (ValueError, TypeError):
            # If conversion fails, use default
            self.parent.search_range.setValue(DEFAULT_SEARCH_RANGE)
            self.parent.search_range.setMinimum(MIN_SEARCH_RANGE)
            self.parent.search_range.setMaximum(MAX_SEARCH_RANGE)
            self.settings.setValue("search_range", DEFAULT_SEARCH_RANGE)
            self.parent.log_box_append(
                f"Invalid search range in settings, using default ({DEFAULT_SEARCH_RANGE})"
            )

        # Load and apply saved theme (default to Dark theme)
        saved_theme = self.settings.value("theme", "Dark")
        self.parent.theme_selector.setCurrentText(saved_theme)
        self.parent.theme_manager.apply_theme(saved_theme)

    def save_settings(self) -> None:
        """
        Save the settings to the settings file with validation.
        """
        # Validate paths before saving
        vp_tree_path = self.parent.vp_tree_dir.text().strip()
        hashing_path = self.parent.hash_dir.text().strip()

        if not vp_tree_path:
            self.parent.append_colored_text(ErrorMessages.VP_TREE_PATH_EMPTY, QtGui.QColor("red"))
            return

        if not hashing_path:
            self.parent.append_colored_text(ErrorMessages.HASHING_PATH_EMPTY, QtGui.QColor("red"))
            return

        # Validate that paths have proper extensions
        if not vp_tree_path.endswith(".pickle"):
            self.parent.append_colored_text(
                ErrorMessages.VP_TREE_PATH_WARNING, QtGui.QColor("orange")
            )

        if not hashing_path.endswith(".pickle"):
            self.parent.append_colored_text(
                ErrorMessages.HASHING_PATH_WARNING, QtGui.QColor("orange")
            )

        # Save validated settings
        self.settings.setValue("VPTree", vp_tree_path)
        self.settings.setValue("Hashing", hashing_path)
        self.settings.setValue("search_range", self.parent.search_range.value())
        self.settings.setValue("parallel_workers", self.parent.parallel_workers.value())
        self.settings.setValue("similarity_threshold", self.parent.similarity_threshold.value())

        # Save advanced filter settings
        self.settings.setValue(
            "filter_enabled",
            self.parent.file_type_check.isChecked()
            or self.parent.file_size_check.isChecked()
            or self.parent.dimensions_check.isChecked(),
        )
        self.settings.setValue("file_type_filter_enabled", self.parent.file_type_check.isChecked())
        self.settings.setValue("file_type_filter", self.parent.file_type_filter.text())
        self.settings.setValue("file_size_filter_enabled", self.parent.file_size_check.isChecked())
        self.settings.setValue("min_file_size", self.parent.min_size_spin.value())
        self.settings.setValue("max_file_size", self.parent.max_size_spin.value())
        self.settings.setValue(
            "dimensions_filter_enabled", self.parent.dimensions_check.isChecked()
        )
        self.settings.setValue("min_width", self.parent.min_width_spin.value())
        self.settings.setValue("min_height", self.parent.min_height_spin.value())

        self.parent.log_box_append("Settings saved successfully")
        try:
            from chime import success as SuccessSound

            SuccessSound()
        except ImportError:
            pass

    def save_window_state(self) -> None:
        """Save window geometry and state."""
        self.settings.setValue("window_geometry", self.parent.saveGeometry())
        self.settings.setValue("window_state", self.parent.saveState())

    def restore_window_state(self) -> None:
        """Restore window geometry and state if saved."""
        saved_geometry = self.settings.value("window_geometry")
        saved_state = self.settings.value("window_state")

        if saved_geometry:
            self.parent.restoreGeometry(saved_geometry)
        if saved_state:
            self.parent.restoreState(saved_state)

    def get_value(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value.

        Parameters
        ----------
        key : str
            The setting key.
        default : Any
            Default value if key not found.

        Returns
        -------
        Any
            The setting value.
        """
        return self.settings.value(key, default)

    def set_value(self, key: str, value: Any) -> None:
        """
        Set a setting value.

        Parameters
        ----------
        key : str
            The setting key.
        value : Any
            The value to set.
        """
        self.settings.setValue(key, value)
