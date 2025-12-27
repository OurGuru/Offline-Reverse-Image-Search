"""
UI components for the Duplicates tab.

Provides interface for viewing and managing duplicate images.
This module handles the detection, display, and management of duplicate
images in the database, including selection strategies and batch operations.
"""

import logging
import os
import platform
import subprocess

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..managers.duplicates_manager import DuplicateGroup, DuplicatesManager


class DuplicateGroupWidget(QFrame):
    """Widget to display a single duplicate group with thumbnails and controls."""

    selection_changed = pyqtSignal()
    thumbnail_clicked = pyqtSignal(str)  # Emit path when thumbnail is clicked

    def __init__(self, group: DuplicateGroup, parent=None):
        super().__init__(parent)
        self.group = group
        self.parent_window = parent
        self.thumbnail_widgets = []
        self.setup_ui()

    def setup_ui(self):
        """Set up the UI for the duplicate group widget."""
        self.setFrameStyle(QFrame.Shape.Box)
        # Remove hardcoded background color to follow theme
        self.setStyleSheet(
            """
            DuplicateGroupWidget {
                border: 1px solid palette(mid);
                border-radius: 5px;
                margin: 5px;
                padding: 10px;
            }
        """
        )

        layout = QVBoxLayout(self)

        # Header with group info
        header_layout = QHBoxLayout()

        # Group title
        title = QLabel(f"Duplicate Group (Hash: {self.group.hash_value[:16]}...)")
        title.setStyleSheet("font-weight: bold; font-size: 12pt;")
        header_layout.addWidget(title)

        # Stats - count actual files in the group
        file_count = len(self.group.file_paths)

        # Try to update file sizes from accessible files before calculating wasted space
        self._try_update_file_sizes()

        # Get actual wasted space calculation
        wasted_space = self.group.get_wasted_space()

        # Store stats label for later updates
        self.stats_label = QLabel(f"{file_count} files | Wasted: {self._format_size(wasted_space)}")
        # Remove hardcoded color to follow theme
        self.stats_label.setStyleSheet("color: palette(text);")
        header_layout.addWidget(self.stats_label)

        header_layout.addStretch()

        # Expand/Collapse button
        self.toggle_button = QPushButton("▼")
        self.toggle_button.setMaximumWidth(30)
        self.toggle_button.clicked.connect(self.toggle_details)
        header_layout.addWidget(self.toggle_button)

        layout.addLayout(header_layout)

        # Details container (collapsible)
        self.details_widget = QWidget()
        details_layout = QGridLayout(self.details_widget)

        # Create a grid of file entries
        col = 0
        row = 0
        max_cols = 4  # Maximum columns for thumbnails

        for file_path in self.group.file_paths:
            # Create file widget for each file path
            file_widget = self.create_file_widget(file_path)
            details_layout.addWidget(file_widget, row, col)

            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        layout.addWidget(self.details_widget)

        # Initially collapsed
        self.details_widget.setVisible(False)
        self.is_expanded = False

    def create_file_widget(self, file_path: str) -> QWidget:
        """Create a widget for a single file in the duplicate group."""
        widget = QFrame()
        widget.setFrameStyle(QFrame.Shape.Box)
        widget.setMaximumWidth(200)
        layout = QVBoxLayout(widget)

        # Checkbox for selection
        checkbox = QCheckBox()
        checkbox.setChecked(file_path in self.group.selected_for_deletion)
        checkbox.toggled.connect(lambda checked: self.on_file_selected(file_path, checked))
        layout.addWidget(checkbox)

        # Try to load actual thumbnail if ThumbnailWidget is available
        thumbnail_loaded = False
        try:
            from ..ui.ui_components import ThumbnailWidget

            # Create actual thumbnail widget
            thumb = ThumbnailWidget(file_path, parent=self)
            thumb.clicked.connect(lambda p=file_path: self.thumbnail_clicked.emit(p))
            thumb.setMaximumSize(120, 120)
            thumb.setMinimumSize(120, 120)
            # Connect context menu from ThumbnailWidget's own signal
            thumb.context_menu_requested.connect(lambda p, pos: self.show_file_context_menu(p, pos))
            layout.addWidget(thumb)
            self.thumbnail_widgets.append(thumb)
            thumbnail_loaded = True
            logging.debug(f"Thumbnail widget created for: {file_path}")
        except ImportError as e:
            logging.warning(f"ThumbnailWidget not available: {e}")
        except Exception as e:
            logging.error(f"Error creating thumbnail for {file_path}: {e}")

        if not thumbnail_loaded:
            # Fallback to simple label if ThumbnailWidget not available
            thumbnail_label = QLabel("📷")
            thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumbnail_label.setMinimumSize(120, 120)
            thumbnail_label.setMaximumSize(120, 120)
            # Remove hardcoded background color to follow theme
            thumbnail_label.setStyleSheet(
                """
                QLabel {
                    border: 1px solid palette(mid);
                    font-size: 48pt;
                }
            """
            )
            thumbnail_label.setCursor(Qt.CursorShape.PointingHandCursor)
            thumbnail_label.mousePressEvent = lambda e: self.thumbnail_clicked.emit(file_path)
            layout.addWidget(thumbnail_label)

        # File name - displayed prominently below the image
        filename = os.path.basename(file_path)
        name_label = QLabel(filename)
        name_label.setToolTip(file_path)  # Full path on hover
        name_label.setWordWrap(True)
        name_label.setMaximumWidth(180)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Make filename more prominent
        name_label.setStyleSheet("font-weight: bold; font-size: 9pt;")
        layout.addWidget(name_label)

        # Get metadata and try to update it if missing
        meta = self.group.metadata.get(file_path, {})
        size = meta.get("size", 0)

        # If size is 0 or None, try to get it from the file system
        if (size is None or size == 0) and os.path.exists(file_path):
            try:
                size = os.path.getsize(file_path)
                # Update the metadata - ensure path exists in metadata dict
                if file_path not in self.group.metadata:
                    self.group.metadata[file_path] = {}
                self.group.metadata[file_path]["size"] = size
                logging.debug(f"Updated size for {file_path}: {size} bytes")

                # Also trigger recalculation of wasted space for the group
                # by updating all file sizes if one is found
                if size > 0:
                    # Update all other files in the group with the same size
                    # since duplicates should have the same size
                    for other_path in self.group.file_paths:
                        if other_path != file_path and other_path in self.group.metadata:
                            if self.group.metadata[other_path].get("size", 0) == 0:
                                self.group.metadata[other_path]["size"] = size
            except Exception as e:
                logging.warning(f"Could not get size for {file_path}: {e}")
                size = 0

        size_text = self._format_size(size if size else 0)

        modified = meta.get("modified")
        if modified:
            try:
                if hasattr(modified, "strftime"):
                    date_text = modified.strftime("%Y-%m-%d")
                else:
                    date_text = str(modified)[:10] if modified else "Unknown"
            except:
                date_text = "Unknown"
        else:
            # Try to get modification date if missing
            if os.path.exists(file_path):
                try:
                    import datetime

                    mtime = os.path.getmtime(file_path)
                    date_text = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                    # Update the metadata
                    self.group.metadata[file_path]["modified"] = datetime.datetime.fromtimestamp(
                        mtime
                    )
                except:
                    date_text = "Unknown"
            else:
                date_text = "Unknown"

        info_label = QLabel(f"{size_text}\n{date_text}")
        info_label.setStyleSheet("font-size: 8pt; color: palette(text);")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info_label)

        # Highlight if this is the recommended keep
        if hasattr(self, "recommended_keep") and file_path == self.recommended_keep:
            # Use palette colors for theme compatibility
            widget.setStyleSheet(
                """
                QFrame {
                    border: 2px solid #4CAF50;
                }
            """
            )

        return widget

    def on_file_selected(self, file_path: str, checked: bool):
        """Handle file selection change."""
        if checked:
            self.group.selected_for_deletion.add(file_path)
        else:
            self.group.selected_for_deletion.discard(file_path)
        self.selection_changed.emit()

    def toggle_details(self):
        """Toggle the visibility of the details section."""
        self.is_expanded = not self.is_expanded
        self.details_widget.setVisible(self.is_expanded)
        self.toggle_button.setText("▲" if self.is_expanded else "▼")

    def set_recommended_keep(self, file_path: str):
        """Mark a file as the recommended one to keep."""
        self.recommended_keep = file_path
        # Refresh the UI to show the highlight
        # This would require recreating the widgets, simplified here

    def show_file_context_menu(self, file_path: str, global_pos):
        """Show context menu for a file."""
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)

        # Open file action
        open_action = QAction("Open File", self)
        open_action.triggered.connect(lambda: self.parent_window.open_file(file_path))
        menu.addAction(open_action)

        # Open folder action
        folder_action = QAction("Open Containing Folder", self)
        folder_action.triggered.connect(lambda: self.parent_window.open_folder(file_path))
        menu.addAction(folder_action)

        menu.addSeparator()

        # Copy path action
        copy_path_action = QAction("Copy File Path", self)
        copy_path_action.triggered.connect(lambda: self.copy_to_clipboard(file_path))
        menu.addAction(copy_path_action)

        # If file doesn't exist, disable open actions
        if not os.path.exists(file_path):
            open_action.setEnabled(False)
            folder_action.setEnabled(False)
            open_action.setText("Open File (Not Found)")

        menu.exec(global_pos)

    def copy_to_clipboard(self, text: str):
        """Copy text to clipboard."""
        from PyQt6.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        if self.parent_window:
            self.parent_window.show_message(f"Copied to clipboard: {text}")

    def _try_update_file_sizes(self):
        """Try to update file sizes from accessible files."""
        # Find at least one accessible file to get the size
        found_size = 0
        for file_path in self.group.file_paths:
            if os.path.exists(file_path):
                try:
                    size = os.path.getsize(file_path)
                    if size > 0:
                        found_size = size
                        break
                except Exception:
                    pass

        # If we found a size, update all files in the group
        # (duplicates should have the same size)
        if found_size > 0:
            for file_path in self.group.file_paths:
                if file_path not in self.group.metadata:
                    self.group.metadata[file_path] = {}
                if self.group.metadata[file_path].get("size", 0) == 0:
                    self.group.metadata[file_path]["size"] = found_size
                    self.group.metadata[file_path]["exists"] = True

    def _format_size(self, size_bytes: int) -> str:
        """Format size in bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"


class DuplicatesTab(QWidget):
    """Main tab widget for duplicate management."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.duplicates_manager = DuplicatesManager(parent)
        self.group_widgets = []

        # Pagination settings - start with smaller page size for large datasets
        self.groups_per_page = 20  # Reduced from 50 to prevent UI lag with 100k+ groups
        self.current_page = 0
        self.total_pages = 0
        self.all_duplicate_groups = []  # Store all groups
        self.displayed_groups = []  # Currently displayed groups

        self.setup_ui()
        self.connect_signals()

        # Don't load duplicates on initialization - wait for user to click refresh
        # This prevents freezing on startup
        # QTimer.singleShot(100, self.refresh_duplicates)

    def setup_ui(self):
        """Set up the main UI for the duplicates tab."""
        main_layout = QVBoxLayout(self)

        # Statistics panel
        self.stats_group = QGroupBox("Duplicate Statistics")
        stats_layout = QGridLayout(self.stats_group)

        # Statistics labels
        self.stats_labels = {
            "groups": QLabel("0"),
            "files": QLabel("0"),
            "wasted": QLabel("0 B"),
            "selected": QLabel("0"),
            "recoverable": QLabel("0 B"),
        }

        # Add stats to grid
        stats_layout.addWidget(QLabel("Duplicate Groups:"), 0, 0)
        stats_layout.addWidget(self.stats_labels["groups"], 0, 1)
        stats_layout.addWidget(QLabel("Total Duplicate Files:"), 0, 2)
        stats_layout.addWidget(self.stats_labels["files"], 0, 3)

        stats_layout.addWidget(QLabel("Wasted Space:"), 1, 0)
        stats_layout.addWidget(self.stats_labels["wasted"], 1, 1)
        stats_layout.addWidget(QLabel("Selected for Deletion:"), 1, 2)
        stats_layout.addWidget(self.stats_labels["selected"], 1, 3)

        stats_layout.addWidget(QLabel("Recoverable Space:"), 2, 0)
        stats_layout.addWidget(self.stats_labels["recoverable"], 2, 1)

        # Make stats bold
        for label in self.stats_labels.values():
            font = label.font()
            font.setBold(True)
            label.setFont(font)
            label.setStyleSheet("color: #0d7377;")

        stats_layout.setColumnStretch(4, 1)  # Add stretch to last column
        main_layout.addWidget(self.stats_group)

        # Control toolbar
        toolbar_layout = QHBoxLayout()

        # Strategy selection
        strategy_group = QGroupBox("Keep Strategy")
        strategy_layout = QHBoxLayout(strategy_group)

        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(
            ["Manual Selection", "Keep Newest", "Keep Largest", "Keep by Location"]
        )
        strategy_layout.addWidget(self.strategy_combo)

        # Location priority (shown only when "Keep by Location" is selected)
        self.location_priority_button = QPushButton("Set Priorities...")
        self.location_priority_button.setVisible(False)
        strategy_layout.addWidget(self.location_priority_button)

        self.apply_strategy_button = QPushButton("Apply Strategy")
        self.apply_strategy_button.clicked.connect(self.apply_strategy)
        strategy_layout.addWidget(self.apply_strategy_button)

        toolbar_layout.addWidget(strategy_group)

        # Action buttons
        action_group = QGroupBox("Actions")
        action_layout = QHBoxLayout(action_group)

        self.preview_button = QPushButton("Preview")
        self.preview_button.setToolTip("Show what would be deleted without actually deleting")
        self.preview_button.clicked.connect(lambda: self.execute_deletion(dry_run=True))
        action_layout.addWidget(self.preview_button)

        self.delete_button = QPushButton("Delete Selected")
        self.delete_button.setStyleSheet(
            """
            QPushButton {
                background-color: #f44336;
                color: white;
                font-weight: bold;
                padding: 5px 15px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """
        )
        self.delete_button.clicked.connect(self.confirm_deletion)
        action_layout.addWidget(self.delete_button)

        self.clear_button = QPushButton("Clear Selection")
        self.clear_button.clicked.connect(self.clear_selection)
        action_layout.addWidget(self.clear_button)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_duplicates)
        action_layout.addWidget(self.refresh_button)

        self.export_button = QPushButton("Export Report...")
        self.export_button.clicked.connect(self.export_report)
        action_layout.addWidget(self.export_button)

        toolbar_layout.addWidget(action_group)
        toolbar_layout.addStretch()

        main_layout.addLayout(toolbar_layout)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        # Duplicate groups scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        self.groups_container = QWidget()
        self.groups_layout = QVBoxLayout(self.groups_container)
        self.groups_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # "No duplicates" message
        self.no_duplicates_label = QLabel(
            "No duplicate images found in the database.\nIndex your image folders first to detect duplicates."
        )
        self.no_duplicates_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_duplicates_label.setStyleSheet("color: #666; font-size: 12pt; padding: 40px;")
        self.groups_layout.addWidget(self.no_duplicates_label)

        scroll_area.setWidget(self.groups_container)
        main_layout.addWidget(scroll_area)

        # Pagination controls
        pagination_layout = QHBoxLayout()

        self.prev_page_button = QPushButton("◀ Previous")
        self.prev_page_button.clicked.connect(self.prev_page)
        self.prev_page_button.setEnabled(False)
        pagination_layout.addWidget(self.prev_page_button)

        self.page_label = QLabel("Page 0 of 0")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_label.setStyleSheet("font-weight: bold; padding: 0 20px;")
        pagination_layout.addWidget(self.page_label)

        self.next_page_button = QPushButton("Next ▶")
        self.next_page_button.clicked.connect(self.next_page)
        self.next_page_button.setEnabled(False)
        pagination_layout.addWidget(self.next_page_button)

        pagination_layout.addStretch()

        self.groups_per_page_spin = QSpinBox()
        self.groups_per_page_spin.setRange(10, 100)  # Reduced max from 200 to 100
        self.groups_per_page_spin.setValue(20)  # Reduced from 50 to 20
        self.groups_per_page_spin.setSuffix(" groups/page")
        self.groups_per_page_spin.valueChanged.connect(self.on_groups_per_page_changed)
        pagination_layout.addWidget(QLabel("Show:"))
        pagination_layout.addWidget(self.groups_per_page_spin)

        main_layout.addLayout(pagination_layout)

        # Connect strategy combo change
        self.strategy_combo.currentTextChanged.connect(self.on_strategy_changed)

    def connect_signals(self):
        """Connect signals from the duplicates manager."""
        self.duplicates_manager.duplicates_updated.connect(self.on_duplicates_loaded)
        self.duplicates_manager.operation_completed.connect(self.on_operation_completed)
        self.duplicates_manager.operation_failed.connect(self.on_operation_failed)

    def refresh_duplicates(self):
        """Refresh the list of duplicates from the database."""
        # Check if database is ready
        if (
            not hasattr(self.parent_window, "database_manager")
            or not self.parent_window.database_manager
        ):
            if self.parent_window:
                self.parent_window.log_message("Database is still loading, please wait...")
            QMessageBox.information(
                self,
                "Database Loading",
                "The database is still loading. Please wait a moment and try again.",
            )
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate

        # Disable refresh button during loading
        self.refresh_button.setEnabled(False)

        # Load duplicates using background thread to prevent freezing
        self.duplicates_manager.load_duplicates(use_thread=True)

    @pyqtSlot(list)
    def on_duplicates_loaded(self, duplicate_groups: list[DuplicateGroup]):
        """Handle when duplicates are loaded from the database."""
        self.progress_bar.setVisible(False)

        # Re-enable refresh button
        self.refresh_button.setEnabled(True)

        # Store all groups
        self.all_duplicate_groups = duplicate_groups

        # Calculate pagination
        if duplicate_groups:
            self.total_pages = (
                len(duplicate_groups) + self.groups_per_page - 1
            ) // self.groups_per_page
            self.current_page = 0

            # Display first page
            self.display_page(0)
        else:
            self.total_pages = 0
            self.current_page = 0
            self.clear_display()

            # Show "no duplicates" message
            self.no_duplicates_label = QLabel(
                "No duplicate images found in the database.\nIndex your image folders first to detect duplicates."
            )
            self.no_duplicates_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.no_duplicates_label.setStyleSheet("color: #666; font-size: 12pt; padding: 40px;")
            self.groups_layout.addWidget(self.no_duplicates_label)

        # Update pagination controls
        self.update_pagination_controls()

        # Update statistics (for all groups, not just displayed)
        self.update_statistics()

    def display_page(self, page_num: int):
        """Display a specific page of duplicate groups."""
        if page_num < 0 or page_num >= self.total_pages:
            return

        self.current_page = page_num
        self.clear_display()

        # Calculate range
        start_idx = page_num * self.groups_per_page
        end_idx = min(start_idx + self.groups_per_page, len(self.all_duplicate_groups))

        # Get groups for this page
        self.displayed_groups = self.all_duplicate_groups[start_idx:end_idx]

        # Create widgets only for the current page
        for group in self.displayed_groups:
            group_widget = DuplicateGroupWidget(group, self)
            group_widget.selection_changed.connect(self.update_statistics)
            group_widget.thumbnail_clicked.connect(self.on_thumbnail_clicked)
            self.groups_layout.addWidget(group_widget)
            self.group_widgets.append(group_widget)

        # Update pagination controls
        self.update_pagination_controls()

        # Show status
        self.show_message(
            f"Showing groups {start_idx + 1}-{end_idx} of {len(self.all_duplicate_groups)}"
        )

    def clear_display(self):
        """Clear the current display of duplicate groups."""
        # Clear existing widgets
        for widget in self.group_widgets:
            widget.deleteLater()
        self.group_widgets.clear()

        # Clear layout
        while self.groups_layout.count():
            item = self.groups_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def prev_page(self):
        """Go to the previous page."""
        if self.current_page > 0:
            self.display_page(self.current_page - 1)

    def next_page(self):
        """Go to the next page."""
        if self.current_page < self.total_pages - 1:
            self.display_page(self.current_page + 1)

    def update_pagination_controls(self):
        """Update the state of pagination controls."""
        if self.total_pages > 0:
            self.page_label.setText(f"Page {self.current_page + 1} of {self.total_pages}")
            self.prev_page_button.setEnabled(self.current_page > 0)
            self.next_page_button.setEnabled(self.current_page < self.total_pages - 1)
        else:
            self.page_label.setText("Page 0 of 0")
            self.prev_page_button.setEnabled(False)
            self.next_page_button.setEnabled(False)

    def on_groups_per_page_changed(self, value: int):
        """Handle change in groups per page setting."""
        self.groups_per_page = value
        if self.all_duplicate_groups:
            # Recalculate pagination and redisplay
            self.total_pages = (
                len(self.all_duplicate_groups) + self.groups_per_page - 1
            ) // self.groups_per_page
            self.current_page = min(self.current_page, self.total_pages - 1)
            self.display_page(self.current_page)

    def update_statistics(self):
        """Update the statistics display."""
        stats = self.duplicates_manager.get_statistics()

        self.stats_labels["groups"].setText(str(stats["total_groups"]))
        self.stats_labels["files"].setText(str(stats["total_duplicate_files"]))
        self.stats_labels["wasted"].setText(self._format_size(stats["wasted_space"]))
        self.stats_labels["selected"].setText(str(stats["selected_for_deletion"]))
        self.stats_labels["recoverable"].setText(self._format_size(stats["recoverable_space"]))

        # Update button states
        has_selection = stats["selected_for_deletion"] > 0
        self.preview_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self.clear_button.setEnabled(has_selection)

    def on_strategy_changed(self, strategy: str):
        """Handle strategy selection change."""
        # Show/hide location priority button
        self.location_priority_button.setVisible(strategy == "Keep by Location")

    def apply_strategy(self):
        """Apply the selected keep strategy to the current page only."""
        strategy = self.strategy_combo.currentText()

        # Only apply to currently displayed groups
        if not self.displayed_groups:
            self.show_message("No duplicate groups on current page")
            return

        total_marked = 0

        for group in self.displayed_groups:
            group.selected_for_deletion.clear()
            existing_paths = [
                p for p in group.file_paths if group.metadata.get(p, {}).get("exists", True)
            ]

            if len(existing_paths) <= 1:
                continue  # Nothing to delete if only one file exists

            keep_path = None

            if strategy == "Manual Selection":
                # Clear selections for manual mode
                continue
            elif strategy == "Keep Newest":
                keep_path = group.get_newest_path()
            elif strategy == "Keep Largest":
                keep_path = group.get_largest_path()
            elif strategy == "Keep by Location":
                # Get folder priorities
                priorities = self.get_location_priorities()
                if priorities:
                    sorted_paths = group.get_paths_by_location_priority(priorities)
                    if sorted_paths:
                        keep_path = sorted_paths[0]  # Keep the highest priority

            if keep_path:
                # Mark all others for deletion
                for path in existing_paths:
                    if path != keep_path:
                        group.selected_for_deletion.add(path)
                        total_marked += 1

        # Show message based on strategy
        if strategy == "Manual Selection":
            self.show_message("Cleared selections for manual mode")
        else:
            self.show_message(
                f"Marked {total_marked} files for deletion on current page ({strategy})"
            )

        # Refresh the current page display
        if self.all_duplicate_groups:
            self.display_page(self.current_page)
        self.update_statistics()

    def get_location_priorities(self) -> list[str]:
        """Get folder priorities for location-based keeping."""
        # For now, return a default priority list
        # In a full implementation, this would show a dialog
        return ["/Photos/Organized/", "/Pictures/", "/Documents/", "/Desktop/", "/Downloads/"]

    def clear_selection(self):
        """Clear all selections."""
        self.duplicates_manager.clear_selection()
        # Refresh current page
        if self.all_duplicate_groups:
            self.display_page(self.current_page)
        self.update_statistics()

    def execute_deletion(self, dry_run: bool = False):
        """Execute the deletion operation."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)

        # Disable buttons during operation
        self.delete_button.setEnabled(False)
        self.preview_button.setEnabled(False)

        # Start deletion
        self.duplicates_manager.delete_selected(use_recycle_bin=True, dry_run=dry_run)

    def confirm_deletion(self):
        """Show confirmation dialog before deletion."""
        stats = self.duplicates_manager.get_statistics()

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Confirm Deletion")
        msg.setText(f"Are you sure you want to delete {stats['selected_for_deletion']} files?")
        msg.setInformativeText(
            f"This will free up {self._format_size(stats['recoverable_space'])} of disk space.\n\nFiles will be moved to the recycle bin."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.No)

        if msg.exec() == QMessageBox.StandardButton.Yes:
            self.execute_deletion(dry_run=False)

    def export_report(self):
        """Export a report of duplicates."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Duplicate Report",
            "duplicate_report.html",
            "HTML Files (*.html);;Text Files (*.txt);;CSV Files (*.csv);;JSON Files (*.json)",
        )

        if file_path:
            # Determine format from extension
            if file_path.endswith(".html"):
                # Use HTML exporter for HTML format
                self.export_to_html(file_path)
            elif file_path.endswith(".csv"):
                format_type = "csv"
                report = self.duplicates_manager.export_report(format_type)
                self._write_report(file_path, report)
            elif file_path.endswith(".json"):
                format_type = "json"
                report = self.duplicates_manager.export_report(format_type)
                self._write_report(file_path, report)
            else:
                format_type = "text"
                report = self.duplicates_manager.export_report(format_type)
                self._write_report(file_path, report)

    def _write_report(self, file_path: str, content: str):
        """Write report content to file."""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.show_message(f"Report exported to {file_path}")
        except Exception as e:
            self.show_message(f"Error exporting report: {str(e)}", error=True)

    def export_to_html(self, file_path: str):
        """Export duplicates to interactive HTML report."""
        try:
            # Import HTML exporter
            from ..utils.html_exporter import HTMLExporter

            # Create exporter instance
            exporter = HTMLExporter()

            # Prepare duplicates dictionary
            duplicates_dict = {}
            for group in self.all_duplicate_groups:
                # Use hash as key and file paths as value
                duplicates_dict[group.hash_value] = group.file_paths

            # Export to HTML
            success = exporter.export_duplicates(
                duplicates_dict, file_path, include_thumbnails=True
            )

            if success:
                self.show_message(f"HTML report exported to {file_path}")

                # Try to open in browser
                try:
                    import webbrowser

                    webbrowser.open(f"file:///{file_path}")
                except:
                    pass
            else:
                self.show_message("Failed to export HTML report", error=True)

        except Exception as e:
            self.show_message(f"Error exporting to HTML: {str(e)}", error=True)

    @pyqtSlot(str)
    def on_thumbnail_clicked(self, image_path: str):
        """Handle thumbnail click - open the image file."""
        self.open_file(image_path)

    def open_file(self, file_path: str):
        """Open a file with the default system application."""
        try:
            if not os.path.exists(file_path):
                self.show_message(f"File not found: {file_path}", error=True)
                return

            # Open file with default application based on OS
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", file_path])
            else:  # Linux and others
                subprocess.run(["xdg-open", file_path])

            # Log the action
            if hasattr(self.parent_window, "log_message"):
                self.parent_window.log_message(f"Opened file: {file_path}")

        except Exception as e:
            logging.error(f"Error opening file {file_path}: {e}")
            self.show_message(f"Error opening file: {str(e)}", error=True)

    def open_folder(self, file_path: str):
        """Open the folder containing the file."""
        try:
            if not os.path.exists(file_path):
                self.show_message(f"File not found: {file_path}", error=True)
                return

            folder_path = os.path.dirname(file_path)

            # Open folder based on OS
            if platform.system() == "Windows":
                # On Windows, we can highlight the file in Explorer
                subprocess.run(["explorer", "/select,", os.path.normpath(file_path)])
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", "-R", file_path])
            else:  # Linux and others
                subprocess.run(["xdg-open", folder_path])

            # Log the action
            if hasattr(self.parent_window, "log_message"):
                self.parent_window.log_message(f"Opened folder: {folder_path}")

        except Exception as e:
            logging.error(f"Error opening folder for {file_path}: {e}")
            self.show_message(f"Error opening folder: {str(e)}", error=True)

    @pyqtSlot(str)
    def on_operation_completed(self, message: str):
        """Handle operation completion."""
        self.progress_bar.setVisible(False)
        self.delete_button.setEnabled(True)
        self.preview_button.setEnabled(True)
        self.show_message(message)
        # Refresh the display
        self.refresh_duplicates()

    @pyqtSlot(str)
    def on_operation_failed(self, message: str):
        """Handle operation failure."""
        self.progress_bar.setVisible(False)
        self.delete_button.setEnabled(True)
        self.preview_button.setEnabled(True)
        self.show_message(message, error=True)

    def update_progress(self, percentage: int, message: str):
        """Update progress bar."""
        self.progress_bar.setValue(percentage)
        self.progress_bar.setFormat(f"{message} ({percentage}%)")

    def show_message(self, message: str, error: bool = False):
        """Show a message to the user."""
        if hasattr(self.parent_window, "log_message"):
            self.parent_window.log_message(message)

        # Also show in status bar if available
        if hasattr(self.parent_window, "update_status_bar"):
            self.parent_window.update_status_bar(message)

    def _format_size(self, size_bytes: int) -> str:
        """Format size in bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
