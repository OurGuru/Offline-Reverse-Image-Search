"""
Search history management functionality for the Offline Reverse Image Search application.
"""

import json
import os
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QGridLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)


class HistoryManager:
    """Manages search history including saving, loading, and UI operations."""

    def __init__(self, parent):
        self.parent = parent
        self.search_history = []  # List of dicts with search info
        self.max_history_entries = 100  # Maximum number of history entries to keep

        # UI components (initialized in setup_search_history_tab)
        self.history_table = None
        self.clear_history_button = None
        self.load_search_button = None

        # Preview tooltip components
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.show_preview)
        self.current_hover_item = None
        self.preview_label = None

    def setup_search_history_tab(self, tab_widget: QWidget) -> None:
        """
        Set up the search history tab with table and controls.

        Parameters
        ----------
        tab_widget : QWidget
            The tab widget to add the history tab to.
        """
        # Create layout for search history tab
        self.parent.tab4 = QWidget()
        self.parent.tab4.setObjectName("tab4")
        history_layout = QVBoxLayout(self.parent.tab4)

        # Create buttons for history management
        buttons_layout = QGridLayout()
        self.clear_history_button = QPushButton("Clear History", self.parent.tab4)
        self.clear_history_button.clicked.connect(self.clear_search_history)
        self.load_search_button = QPushButton("Load Search", self.parent.tab4)
        self.load_search_button.clicked.connect(self.load_from_history)
        self.load_search_button.setEnabled(False)

        buttons_layout.addWidget(self.clear_history_button, 0, 0)
        buttons_layout.addWidget(self.load_search_button, 0, 1)
        history_layout.addLayout(buttons_layout)

        # Create table for search history
        self.history_table = QTableWidget(self.parent.tab4)
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(
            ["Date/Time", "Search Image", "Results Found", "Search Range", "Status"]
        )

        # Set column widths
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        # Enable row selection
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.itemSelectionChanged.connect(self.on_history_selection_changed)

        # Enable mouse tracking for hover events
        self.history_table.setMouseTracking(True)
        self.history_table.itemEntered.connect(self.on_item_hover)

        history_layout.addWidget(self.history_table)
        tab_widget.addTab(self.parent.tab4, "Search History")

    def load_search_history(self) -> None:
        """
        Load search history from file.
        """
        history_file = os.path.join(self.parent.dir_path, "search_history.json")
        if os.path.exists(history_file):
            try:
                with open(history_file, encoding="utf-8") as f:
                    self.search_history = json.load(f)
                self.update_history_table()
            except Exception as e:
                self.parent.log_box_append(f"Failed to load search history: {str(e)}")
                self.search_history = []

    def save_search_history(self) -> None:
        """
        Save search history to file.
        """
        history_file = os.path.join(self.parent.dir_path, "search_history.json")
        try:
            # Keep only the most recent entries
            if len(self.search_history) > self.max_history_entries:
                self.search_history = self.search_history[-self.max_history_entries :]

            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(self.search_history, f, indent=2)
        except Exception as e:
            self.parent.log_box_append(f"Failed to save search history: {str(e)}")

    def update_history_table(self) -> None:
        """
        Update the search history table with current history data.
        """
        if not self.history_table:
            return

        self.history_table.setRowCount(len(self.search_history))

        for row, entry in enumerate(reversed(self.search_history)):  # Show newest first
            # Date/Time
            date_item = QTableWidgetItem(entry.get("timestamp", "Unknown"))
            date_item.setFlags(date_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.history_table.setItem(row, 0, date_item)

            # Search Image
            search_path = entry.get("search_image", "Unknown")
            image_item = QTableWidgetItem(os.path.basename(search_path))
            # Store full path in item data for preview
            image_item.setData(Qt.ItemDataRole.UserRole, search_path)
            # Set simple text tooltip with path
            image_item.setToolTip(f"Path: {search_path}\n(Hover to preview)")
            image_item.setFlags(image_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.history_table.setItem(row, 1, image_item)

            # Results Found
            results_item = QTableWidgetItem(str(entry.get("results_count", 0)))
            results_item.setFlags(results_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.history_table.setItem(row, 2, results_item)

            # Search Range
            range_item = QTableWidgetItem(str(entry.get("search_range", "N/A")))
            range_item.setFlags(range_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.history_table.setItem(row, 3, range_item)

            # Status
            status_item = QTableWidgetItem(entry.get("status", "Unknown"))
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.history_table.setItem(row, 4, status_item)

    def on_history_selection_changed(self) -> None:
        """
        Handle selection changes in the history table.
        """
        if not self.history_table or not self.load_search_button:
            return

        selected_rows = self.history_table.selectionModel().selectedRows()
        self.load_search_button.setEnabled(len(selected_rows) > 0)

    def load_from_history(self) -> None:
        """
        Load the selected search from history.
        """
        if not self.history_table:
            return

        selected_rows = self.history_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        # Get the selected row
        row = selected_rows[0].row()
        history_index = len(self.search_history) - 1 - row

        if 0 <= history_index < len(self.search_history):
            entry = self.search_history[history_index]

            # Load the search image and results
            search_image = entry.get("search_image", "")
            results = entry.get("results", [])
            search_range = entry.get("search_range", 6)

            if os.path.exists(search_image):
                # Update search range
                self.parent.search_range.setValue(search_range)

                # Set the search image
                self.parent.file_path = search_image
                self.parent.current_image_path = search_image
                self.parent.photo_main.set_image(search_image)
                self.parent.label_image.setText(os.path.basename(search_image))

                # Enable the search button since we have an image loaded
                self.parent.search_button.setEnabled(True)

                # Display results if available
                if results:
                    # Clear existing results
                    self.parent.images_found.clear()
                    self.parent.list_widget.clear()

                    # Clear hash data
                    if hasattr(self.parent, "image_hashes"):
                        self.parent.image_hashes.clear()
                    if hasattr(self.parent, "hash_to_paths"):
                        self.parent.hash_to_paths.clear()

                    # Filter results to only existing files
                    existing_results = []
                    for result in results:
                        if os.path.exists(result):
                            existing_results.append(result)

                    if existing_results:
                        # Add results to the list
                        self.parent.images_found = existing_results
                        self.parent.current_index = 0

                        # Update the list widget with proper numbering
                        for i, img_path in enumerate(existing_results):
                            file_name = os.path.basename(img_path)
                            list_text = f"{i+1}. {file_name}"
                            self.parent.list_widget.addItem(list_text)

                        # Display the first result
                        if self.parent.images_found:
                            self.parent.current_result_path = self.parent.images_found[0]
                            self.parent.display_current_result()

                        # Update labels
                        self.parent.label_result.setText(
                            f"Results: {len(self.parent.images_found)} (from history)"
                        )
                        self.parent.label_current.setText(
                            f"Current: 1/{len(self.parent.images_found)}"
                        )

                        # Enable navigation buttons
                        self.parent.previous_button.setEnabled(False)
                        self.parent.next_button.setEnabled(len(self.parent.images_found) > 1)
                        self.parent.open_image_button.setEnabled(True)

                        # Enable thumbnails button
                        self.parent.toggle_thumbnails_button.setEnabled(True)

                        # Update window title
                        self.parent.setWindowTitle(
                            f"Offline Reverse Image Search - {len(self.parent.images_found)} results found (from history)"
                        )

                        self.parent.log_box_append(
                            f"Loaded search from history: {os.path.basename(search_image)} with {len(existing_results)} results"
                        )
                    else:
                        self.parent.log_box_append(
                            f"Loaded search image from history: {os.path.basename(search_image)} (no results found in saved locations)"
                        )
                else:
                    self.parent.log_box_append(
                        f"Loaded search image from history: {os.path.basename(search_image)} (no results saved)"
                    )
            else:
                self.parent.log_box_append(f"Search image no longer exists: {search_image}")

    def clear_search_history(self) -> None:
        """
        Clear all search history after confirmation.
        """
        if not self.search_history:
            QMessageBox.information(
                self.parent, "History Empty", "Search history is already empty."
            )
            return

        reply = QMessageBox.question(
            self.parent,
            "Confirm Clear History",
            f"Are you sure you want to clear all {len(self.search_history)} search history entries?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.search_history.clear()
            self.save_search_history()
            self.update_history_table()
            self.parent.log_box_append("Search history cleared")

    def add_to_search_history(
        self, search_image: str, results: list[str], search_range: int, status: str = "Success"
    ) -> None:
        """
        Add a new entry to search history.

        Parameters
        ----------
        search_image : str
            Path to the search image.
        results : list
            List of result image paths.
        search_range : int
            The search range used.
        status : str
            Status of the search (Success/Failed/etc).
        """
        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "search_image": search_image,
            "results": results[:20],  # Store only first 20 results to avoid huge file
            "results_count": len(results),
            "search_range": search_range,
            "status": status,
        }

        self.search_history.append(entry)
        self.save_search_history()
        self.update_history_table()

    def on_item_hover(self, item: QTableWidgetItem) -> None:
        """
        Handle hover events on table items to show image preview.

        Parameters
        ----------
        item : QTableWidgetItem
            The table item being hovered over.
        """
        # Only show preview for image column (column 1)
        if item and item.column() == 1:
            # Cancel any pending preview
            self.preview_timer.stop()

            # Store the current item and start timer for delayed preview
            self.current_hover_item = item
            self.preview_timer.start(500)  # 500ms delay before showing preview
        else:
            # Cancel preview if hovering over other columns
            self.preview_timer.stop()
            self.hide_preview()

    def show_preview(self) -> None:
        """Show a preview tooltip of the hovered image."""
        if not self.current_hover_item:
            return

        # Get the image path from item data
        image_path = self.current_hover_item.data(Qt.ItemDataRole.UserRole)

        if not image_path or not os.path.exists(image_path):
            # Show text tooltip if image doesn't exist
            if image_path:
                QToolTip.showText(
                    self.history_table.cursor().pos(),
                    f"Image not found:\n{os.path.basename(image_path)}",
                    self.history_table,
                )
            return

        try:
            # Load and scale the image
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                QToolTip.showText(
                    self.history_table.cursor().pos(),
                    f"Failed to load image:\n{os.path.basename(image_path)}",
                    self.history_table,
                )
                return

            # Scale image to reasonable preview size (max 300x300)
            preview_size = 300
            if pixmap.width() > preview_size or pixmap.height() > preview_size:
                pixmap = pixmap.scaled(
                    preview_size,
                    preview_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

            # Create a label to show the image
            if not self.preview_label:
                self.preview_label = QLabel()
                self.preview_label.setWindowFlags(
                    Qt.WindowType.ToolTip
                    | Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.WindowStaysOnTopHint
                )
                self.preview_label.setStyleSheet(
                    """
                    QLabel {
                        border: 2px solid #333;
                        border-radius: 5px;
                        background-color: white;
                        padding: 5px;
                    }
                """
                )

            # Set the pixmap and show the preview
            self.preview_label.setPixmap(pixmap)

            # Calculate position (near cursor but ensure it's visible)
            cursor_pos = self.history_table.cursor().pos()

            # Adjust position to avoid going off-screen
            screen_geometry = self.parent.screen().geometry()
            preview_x = cursor_pos.x() + 20
            preview_y = cursor_pos.y() + 20

            # Check if preview would go off the right edge
            if preview_x + self.preview_label.width() > screen_geometry.right():
                preview_x = cursor_pos.x() - self.preview_label.width() - 20

            # Check if preview would go off the bottom edge
            if preview_y + self.preview_label.height() > screen_geometry.bottom():
                preview_y = cursor_pos.y() - self.preview_label.height() - 20

            self.preview_label.move(preview_x, preview_y)
            self.preview_label.show()

            # Hide preview after mouse leaves
            self.history_table.leaveEvent = lambda event: self.hide_preview()

        except Exception as e:
            self.parent.log_box_append(f"Error showing preview: {str(e)}")

    def hide_preview(self) -> None:
        """Hide the image preview tooltip."""
        self.preview_timer.stop()
        if self.preview_label and self.preview_label.isVisible():
            self.preview_label.hide()
        QToolTip.hideText()
