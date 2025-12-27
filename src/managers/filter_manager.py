"""
Filter management functionality for the Offline Reverse Image Search application.
"""

import os

from PIL import Image
from PyQt6 import QtCore
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
)


class FilterManager:
    """Manages search and result filters for image searching."""

    def __init__(self, parent):
        self.parent = parent

        # Search filter components
        self.filters_group = None
        self.file_type_check = None
        self.file_type_filter = None
        self.file_size_check = None
        self.min_size_spin = None
        self.max_size_spin = None
        self.dimensions_check = None
        self.min_width_spin = None
        self.min_height_spin = None

        # Result filter components
        self.result_filters_group = None
        self.result_type_check = None
        self.result_type_filter = None
        self.result_size_check = None
        self.result_min_size = None
        self.result_max_size = None
        self.result_dim_check = None
        self.result_min_width = None
        self.result_min_height = None
        self.apply_filters_button = None
        self.clear_filters_button = None

        # Filter state
        self.original_results = []
        self.filtered_results = []
        self.is_filtered = False

    def setup_search_filters(self, tab_widget) -> QGroupBox:
        """
        Set up search filters for the Indexer tab.

        Parameters
        ----------
        tab_widget : QWidget
            The parent widget for the filters.

        Returns
        -------
        QGroupBox
            The configured filters group box.
        """
        # Advanced filters group box
        self.filters_group = QGroupBox("Advanced Filters", tab_widget)
        self.filters_group.setGeometry(QtCore.QRect(10, 350, 770, 150))
        self.filters_group.setObjectName("filters_group")

        # File type filter
        self.file_type_check = QCheckBox("Filter by file type", self.filters_group)
        self.file_type_check.setGeometry(QtCore.QRect(10, 30, 150, 20))
        self.file_type_check.setObjectName("file_type_check")
        self.file_type_filter = QLineEdit(self.filters_group)
        self.file_type_filter.setGeometry(QtCore.QRect(160, 30, 200, 22))
        self.file_type_filter.setPlaceholderText("e.g., .jpg,.png,.gif")
        self.file_type_filter.setEnabled(False)
        self.file_type_filter.setObjectName("file_type_filter")
        self.file_type_check.toggled.connect(self.file_type_filter.setEnabled)

        # File size filter
        self.file_size_check = QCheckBox("Filter by file size", self.filters_group)
        self.file_size_check.setGeometry(QtCore.QRect(10, 60, 150, 20))
        self.file_size_check.setObjectName("file_size_check")

        min_size_label = QLabel("Min (MB):", self.filters_group)
        min_size_label.setGeometry(QtCore.QRect(160, 60, 60, 20))
        self.min_size_spin = QDoubleSpinBox(self.filters_group)
        self.min_size_spin.setGeometry(QtCore.QRect(220, 60, 80, 22))
        self.min_size_spin.setMinimum(0.0)
        self.min_size_spin.setMaximum(999999.0)
        self.min_size_spin.setSingleStep(0.1)
        self.min_size_spin.setEnabled(False)
        self.min_size_spin.setObjectName("min_size_spin")

        max_size_label = QLabel("Max (MB):", self.filters_group)
        max_size_label.setGeometry(QtCore.QRect(310, 60, 60, 20))
        self.max_size_spin = QDoubleSpinBox(self.filters_group)
        self.max_size_spin.setGeometry(QtCore.QRect(370, 60, 80, 22))
        self.max_size_spin.setMinimum(0.0)
        self.max_size_spin.setMaximum(999999.0)
        self.max_size_spin.setSingleStep(0.1)
        self.max_size_spin.setValue(100.0)
        self.max_size_spin.setEnabled(False)
        self.max_size_spin.setObjectName("max_size_spin")

        self.file_size_check.toggled.connect(self.min_size_spin.setEnabled)
        self.file_size_check.toggled.connect(self.max_size_spin.setEnabled)

        # Dimensions filter
        self.dimensions_check = QCheckBox("Filter by dimensions", self.filters_group)
        self.dimensions_check.setGeometry(QtCore.QRect(10, 90, 150, 20))
        self.dimensions_check.setObjectName("dimensions_check")

        min_width_label = QLabel("Min Width:", self.filters_group)
        min_width_label.setGeometry(QtCore.QRect(160, 90, 70, 20))
        self.min_width_spin = QSpinBox(self.filters_group)
        self.min_width_spin.setGeometry(QtCore.QRect(230, 90, 70, 22))
        self.min_width_spin.setMinimum(0)
        self.min_width_spin.setMaximum(99999)
        self.min_width_spin.setEnabled(False)
        self.min_width_spin.setObjectName("min_width_spin")

        min_height_label = QLabel("Min Height:", self.filters_group)
        min_height_label.setGeometry(QtCore.QRect(310, 90, 70, 20))
        self.min_height_spin = QSpinBox(self.filters_group)
        self.min_height_spin.setGeometry(QtCore.QRect(380, 90, 70, 22))
        self.min_height_spin.setMinimum(0)
        self.min_height_spin.setMaximum(99999)
        self.min_height_spin.setEnabled(False)
        self.min_height_spin.setObjectName("min_height_spin")

        self.dimensions_check.toggled.connect(self.min_width_spin.setEnabled)
        self.dimensions_check.toggled.connect(self.min_height_spin.setEnabled)

        return self.filters_group

    def setup_result_filters(self, parent_widget, grid_layout) -> None:
        """
        Set up result filters for the Finder tab.

        Parameters
        ----------
        parent_widget : QWidget
            The parent widget for the filters.
        grid_layout : QGridLayout
            The layout to add the filters to.
        """
        # Create collapsible filter section
        self.result_filters_group = QGroupBox("Result Filters", parent_widget)
        self.result_filters_group.setCheckable(True)
        self.result_filters_group.setChecked(False)  # Collapsed by default
        self.result_filters_group.setStyleSheet(
            """
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 20px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """
        )

        # Create layout for filters
        filter_layout = QGridLayout(self.result_filters_group)

        # File type filter
        self.result_type_check = QCheckBox("Filter by type", self.result_filters_group)
        self.result_type_filter = QLineEdit(self.result_filters_group)
        self.result_type_filter.setPlaceholderText("e.g., .jpg,.png")
        self.result_type_filter.setEnabled(False)
        self.result_type_check.toggled.connect(self.result_type_filter.setEnabled)
        filter_layout.addWidget(self.result_type_check, 0, 0)
        filter_layout.addWidget(self.result_type_filter, 0, 1)

        # File size filter
        self.result_size_check = QCheckBox("Filter by size", self.result_filters_group)
        self.result_min_size = QDoubleSpinBox(self.result_filters_group)
        self.result_min_size.setMinimum(0.0)
        self.result_min_size.setMaximum(999999.0)
        self.result_min_size.setSingleStep(0.1)
        self.result_min_size.setSuffix(" MB")
        self.result_min_size.setEnabled(False)
        self.result_max_size = QDoubleSpinBox(self.result_filters_group)
        self.result_max_size.setMinimum(0.0)
        self.result_max_size.setMaximum(999999.0)
        self.result_max_size.setSingleStep(0.1)
        self.result_max_size.setSuffix(" MB")
        self.result_max_size.setValue(100.0)
        self.result_max_size.setEnabled(False)
        self.result_size_check.toggled.connect(self.result_min_size.setEnabled)
        self.result_size_check.toggled.connect(self.result_max_size.setEnabled)

        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Min:"))
        size_layout.addWidget(self.result_min_size)
        size_layout.addWidget(QLabel("Max:"))
        size_layout.addWidget(self.result_max_size)
        size_layout.addStretch()

        filter_layout.addWidget(self.result_size_check, 1, 0)
        filter_layout.addLayout(size_layout, 1, 1)

        # Dimensions filter
        self.result_dim_check = QCheckBox("Filter by dimensions", self.result_filters_group)
        self.result_min_width = QSpinBox(self.result_filters_group)
        self.result_min_width.setMinimum(0)
        self.result_min_width.setMaximum(99999)
        self.result_min_width.setSuffix("px")
        self.result_min_width.setEnabled(False)
        self.result_min_height = QSpinBox(self.result_filters_group)
        self.result_min_height.setMinimum(0)
        self.result_min_height.setMaximum(99999)
        self.result_min_height.setSuffix("px")
        self.result_min_height.setEnabled(False)
        self.result_dim_check.toggled.connect(self.result_min_width.setEnabled)
        self.result_dim_check.toggled.connect(self.result_min_height.setEnabled)

        dim_layout = QHBoxLayout()
        dim_layout.addWidget(QLabel("Min Width:"))
        dim_layout.addWidget(self.result_min_width)
        dim_layout.addWidget(QLabel("Min Height:"))
        dim_layout.addWidget(self.result_min_height)
        dim_layout.addStretch()

        filter_layout.addWidget(self.result_dim_check, 2, 0)
        filter_layout.addLayout(dim_layout, 2, 1)

        # Apply filters button
        self.apply_filters_button = QPushButton("Apply Filters", self.result_filters_group)
        self.apply_filters_button.clicked.connect(self.apply_result_filters)
        self.apply_filters_button.setStyleSheet(
            """
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """
        )

        # Clear filters button
        self.clear_filters_button = QPushButton("Clear Filters", self.result_filters_group)
        self.clear_filters_button.clicked.connect(self.clear_result_filters)
        self.clear_filters_button.setStyleSheet(
            """
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """
        )

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.apply_filters_button)
        button_layout.addWidget(self.clear_filters_button)
        filter_layout.addLayout(button_layout, 3, 0, 1, 2)

        # Add filters group to the main layout
        grid_layout.addWidget(self.result_filters_group, 5, 0, 1, 4)  # Span all columns

    def apply_result_filters(self) -> None:
        """
        Apply filters to the current search results.
        """
        if not self.parent.images_found:
            self.parent.log_box_append("No results to filter")
            return

        # Store original results if not already filtered
        if not self.is_filtered:
            self.original_results = self.parent.images_found.copy()

        # Start with all original results
        filtered = self.original_results.copy()
        initial_count = len(filtered)

        # Apply file type filter
        if self.result_type_check.isChecked() and self.result_type_filter.text():
            allowed_extensions = [
                ext.strip().lower() for ext in self.result_type_filter.text().split(",")
            ]
            filtered = [
                img for img in filtered if os.path.splitext(img)[1].lower() in allowed_extensions
            ]

        # Apply file size filter
        if self.result_size_check.isChecked():
            min_size_mb = self.result_min_size.value()
            max_size_mb = self.result_max_size.value()
            size_filtered = []
            for img in filtered:
                try:
                    size_mb = os.path.getsize(img) / (1024 * 1024)
                    if min_size_mb <= size_mb <= max_size_mb:
                        size_filtered.append(img)
                except OSError:
                    pass  # Skip inaccessible files
            filtered = size_filtered

        # Apply dimensions filter
        if self.result_dim_check.isChecked():
            min_width = self.result_min_width.value()
            min_height = self.result_min_height.value()
            dim_filtered = []
            for img in filtered:
                try:
                    with Image.open(img) as image:
                        width, height = image.size
                        if width >= min_width and height >= min_height:
                            dim_filtered.append(img)
                except:
                    pass  # Skip files that can't be opened
            filtered = dim_filtered

        # Update the display with filtered results
        self.filtered_results = filtered
        self.is_filtered = True

        # Update images_found with filtered results
        with self.parent.images_lock:
            self.parent.images_found = filtered.copy()

        # Update display
        self.parent.list_widget.clear()
        for img_path in self.parent.images_found:
            self.parent.list_widget.addItem(os.path.basename(img_path))

        if self.parent.images_found:
            # Reset to first image
            self.parent.current_image_index = 0
            if hasattr(self.parent, "set_image"):
                self.parent.label_current.setText(
                    f"Current 1/{len(self.parent.images_found)}"
                    + (" (filtered)" if self.is_filtered else "")
                )
                self.parent.set_image(self.parent.images_found[0])
            else:
                # No results after filtering
                self.parent.photo_viewer.setText("No results match the filter criteria")
                self.parent.next_button.setEnabled(False)
                self.parent.prev_button.setEnabled(False)

        # Update result counts
        self.parent.found_label.setText(str(len(self.parent.images_found)))
        self.parent.label_result.setText(
            f"Total results: {len(self.parent.images_found)}" + f" (filtered from {initial_count})"
            if self.is_filtered
            else ""
        )

        # Enable/disable navigation buttons
        self.parent.next_button.setEnabled(len(self.parent.images_found) > 1)
        self.parent.prev_button.setEnabled(len(self.parent.images_found) > 1)

        # Log the filtering action
        self.parent.log_box_append(
            f"Filtered results: {len(self.parent.images_found)} out of {initial_count} original results"
        )

        # Update window title
        self.parent.setWindowTitle(
            f"Offline Reverse Image Search - {len(self.parent.images_found)} results"
            + " (filtered)"
            if self.is_filtered
            else ""
        )

    def clear_result_filters(self) -> None:
        """
        Clear all result filters and restore original results.
        """
        if not self.original_results:
            self.parent.log_box_append("No filters to clear")
            return

        # Clear filter checkboxes
        self.result_type_check.setChecked(False)
        self.result_size_check.setChecked(False)
        self.result_dim_check.setChecked(False)

        # Clear filter values
        self.result_type_filter.clear()
        self.result_min_size.setValue(0.0)
        self.result_max_size.setValue(100.0)
        self.result_min_width.setValue(0)
        self.result_min_height.setValue(0)

        # Restore original results
        self.is_filtered = False
        with self.parent.images_lock:
            self.parent.images_found = self.original_results.copy()

        # Update display
        self.parent.list_widget.clear()
        for img_path in self.parent.images_found:
            self.parent.list_widget.addItem(os.path.basename(img_path))

        # Reset to first image
        if self.parent.images_found:
            self.parent.current_image_index = 0
            if hasattr(self.parent, "set_image"):
                self.parent.set_image(self.parent.images_found[0])
            self.parent.label_current.setText(f"Current 1/{len(self.parent.images_found)}")

        # Update counts and labels
        self.parent.found_label.setText(str(len(self.parent.images_found)))
        self.parent.label_result.setText(f"Total results: {len(self.parent.images_found)}")

        # Enable navigation buttons if there are results
        self.parent.next_button.setEnabled(len(self.parent.images_found) > 1)
        self.parent.prev_button.setEnabled(len(self.parent.images_found) > 1)

        # Update window title
        self.parent.setWindowTitle(
            f"Offline Reverse Image Search - {len(self.parent.images_found)} results"
        )

        # Log the action
        self.parent.log_box_append(
            f"Filters cleared. Showing all {len(self.parent.images_found)} results"
        )

    def get_search_filter_params(self) -> dict:
        """
        Get the current search filter parameters.

        Returns
        -------
        dict
            Dictionary with filter parameters for the worker thread.
        """
        return {
            "file_type_filter_enabled": self.file_type_check.isChecked(),
            "file_type_filter": self.file_type_filter.text(),
            "file_size_filter_enabled": self.file_size_check.isChecked(),
            "min_file_size": self.min_size_spin.value(),
            "max_file_size": self.max_size_spin.value(),
            "dimensions_filter_enabled": self.dimensions_check.isChecked(),
            "min_width": self.min_width_spin.value(),
            "min_height": self.min_height_spin.value(),
        }

    def reset_filters(self) -> None:
        """Reset all filters to their default state."""
        # Clear search filters
        if self.file_type_check:
            self.file_type_check.setChecked(False)
        if self.file_type_filter:
            self.file_type_filter.clear()
        if self.file_size_check:
            self.file_size_check.setChecked(False)
        if self.min_size_spin:
            self.min_size_spin.setValue(0.0)
        if self.max_size_spin:
            self.max_size_spin.setValue(100.0)
        if self.dimensions_check:
            self.dimensions_check.setChecked(False)
        if self.min_width_spin:
            self.min_width_spin.setValue(0)
        if self.min_height_spin:
            self.min_height_spin.setValue(0)

        # Clear result filters
        if hasattr(self, "original_results"):
            self.original_results.clear()
            self.filtered_results.clear()
            self.is_filtered = False

        # Clear result filter UI
        if self.result_type_check:
            self.result_type_check.setChecked(False)
        if self.result_size_check:
            self.result_size_check.setChecked(False)
        if self.result_dim_check:
            self.result_dim_check.setChecked(False)
        if self.result_type_filter:
            self.result_type_filter.clear()
        if self.result_min_size:
            self.result_min_size.setValue(0.0)
        if self.result_max_size:
            self.result_max_size.setValue(100.0)
        if self.result_min_width:
            self.result_min_width.setValue(0)
        if self.result_min_height:
            self.result_min_height.setValue(0)
