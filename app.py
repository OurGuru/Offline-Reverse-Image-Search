"""
Main application entry point for Offline Reverse Image Search.

This module orchestrates the UI and coordinates between different managers.
"""

import logging
import os
import sys

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplashScreen,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.core.workers_paginated import HTMLExportWorker as PaginatedHTMLExportWorker
from src.managers.database_manager import DatabaseManager
from src.managers.filter_manager import FilterManager
from src.managers.history_manager import HistoryManager
from src.managers.index_manager import IndexManager
from src.managers.metadata_manager import MetadataManager
from src.managers.search_manager import SearchManager
from src.managers.settings_manager import SettingsManager
from src.managers.theme_manager import ThemeManager
from src.ui.async_thumbnail_loader import ThumbnailLoaderManager
from src.ui.ui_components import ThumbnailWidget
from src.ui.zoomable_image_viewer import ZoomableImageViewer

# Import all the extracted modules
from src.utils import get_app_logo
from src.utils.file_handler import DragDropWidget, FileHandler
from src.utils.html_exporter import HTMLExporter
from src.utils.utils import convert_hash, dhash, hamming


class MyWindow(QMainWindow):
    """
    Main application window that coordinates all the managers and UI components.
    """

    # Compatibility wrappers for pickled index files that reference old locations
    @staticmethod
    def hamming(a: int, b: int) -> int:
        """Compatibility wrapper for pickled index files."""
        return hamming(a, b)

    @staticmethod
    def dhash(image: str, hash_size: int = 8) -> int:
        """Compatibility wrapper for pickled index files."""
        return dhash(image, hash_size)

    @staticmethod
    def convert_hash(h):
        """Compatibility wrapper for pickled index files."""
        return convert_hash(h)

    def __init__(self):
        super(MyWindow, self).__init__()

        # Initialize minimal properties needed for UI
        self.test_file_ext = ""
        self.current = ""
        self.file_path = ""
        self.main_image_path = ""
        self.dir_path = os.getcwd()
        self.is_processing = False
        self.current_image_path = None
        self.current_result_path = None
        self.current_index = 0

        # Initialize data structures
        self.images_found = []
        self.display_queue = None
        self.settings = {}
        self.image_hashes = {}
        self.hash_to_paths = {}

        # Initialize threading locks
        self.images_lock = QtCore.QMutex()
        self.queue_lock = QtCore.QMutex()
        self.current_lock = QtCore.QMutex()

        # Database will be initialized async
        self.database_manager = None

        # Initialize HTML exporter
        self.html_exporter = HTMLExporter()

        # Minimal settings for UI setup
        self.settings = SettingsManager(self)

        # Create file handler early (needed for UI)
        self.file_handler = FileHandler(self)

        # Set up the UI first (fast)
        self.setup_ui()

        # Set up keyboard shortcuts
        self.setup_keyboard_shortcuts()

        # Schedule initialization after UI is shown
        # Use 0ms to defer to next event loop iteration
        QTimer.singleShot(0, self.init_managers_async)

    def setup_ui(self):
        """Set up the user interface."""
        # Basic window setup
        self.setObjectName("Offline")
        self.setWindowTitle("Offline Reverse Image Search")
        self.resize(1200, 900)
        self.setAcceptDrops(True)
        self.setWindowIcon(QtGui.QIcon(get_app_logo()))

        # Create central widget
        self.central_widget = DragDropWidget(self.file_handler, self)
        self.central_widget.setObjectName("central_widget")
        self.setCentralWidget(self.central_widget)

        # Main layout
        main_layout = QVBoxLayout(self.central_widget)

        # Top section for search controls
        top_group = QGroupBox("Search Controls")
        top_layout = QGridLayout(top_group)

        # Search image path
        self.label_image = QLabel("No image selected")
        top_layout.addWidget(QLabel("Search Image:"), 0, 0)
        top_layout.addWidget(self.label_image, 0, 1, 1, 3)

        # Search range
        self.search_range = QSpinBox()
        self.search_range.setRange(1, 50)
        self.search_range.setValue(6)
        top_layout.addWidget(QLabel("Search Range:"), 1, 0)
        top_layout.addWidget(self.search_range, 1, 1)

        # Search button
        self.search_button = QPushButton("Start Search")
        self.search_button.setEnabled(False)
        self.search_button.setToolTip("Loading database...")
        top_layout.addWidget(self.search_button, 1, 2)

        # Database loading indicator label
        self.db_loading_label = QLabel("⏳ Database loading...")
        self.db_loading_label.setStyleSheet("color: orange; font-weight: bold;")
        top_layout.addWidget(self.db_loading_label, 1, 3)

        # Progress bar for search indication
        self.search_progress = QProgressBar()
        self.search_progress.setMaximum(0)  # Indeterminate progress
        self.search_progress.setMinimum(0)
        self.search_progress.setVisible(False)
        self.search_progress.setTextVisible(False)
        self.search_progress.setStyleSheet(
            """
            QProgressBar {
                border: 1px solid #999;
                border-radius: 4px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #0d7377;
                border-radius: 3px;
            }
        """
        )
        top_layout.addWidget(self.search_progress, 2, 0, 1, 3)

        main_layout.addWidget(top_group)

        # Middle section with tabs
        self.tab_widget = QTabWidget()

        # Results tab
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)

        # Toggle buttons at the top
        toggle_layout = QHBoxLayout()

        self.toggle_search_image_button = QPushButton("Hide Search Image")
        self.toggle_search_image_button.clicked.connect(self.toggle_search_image)
        toggle_layout.addWidget(self.toggle_search_image_button)

        self.toggle_file_list_button = QPushButton("Hide File List")
        self.toggle_file_list_button.clicked.connect(self.toggle_file_list)
        toggle_layout.addWidget(self.toggle_file_list_button)

        self.toggle_thumbnails_button = QPushButton("Show Thumbnails")
        self.toggle_thumbnails_button.setEnabled(False)
        self.toggle_thumbnails_button.clicked.connect(self.toggle_thumbnails)
        toggle_layout.addWidget(self.toggle_thumbnails_button)

        self.toggle_filters_button = QPushButton("Show Filters")
        self.toggle_filters_button.clicked.connect(self.toggle_filters)
        toggle_layout.addWidget(self.toggle_filters_button)

        toggle_layout.addStretch()
        results_layout.addLayout(toggle_layout)

        # Add collapsible filter section
        self.filters_container = QGroupBox("Search Result Filters")
        self.filters_container.setCheckable(True)
        self.filters_container.setChecked(False)  # Hidden by default
        self.filters_container.setVisible(False)  # Actually hide it
        self.filters_container.setMaximumHeight(200)
        self.filters_container.setStyleSheet(
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

        # Create filter controls inside the container
        filters_layout = QVBoxLayout(self.filters_container)

        # File name filter with regex support
        name_layout = QHBoxLayout()
        self.filter_name_check = QCheckBox("Filter by name (regex):")
        self.filter_name_input = QLineEdit()
        self.filter_name_input.setPlaceholderText(r"e.g., ^IMG.*, .*\.jpg$, photo[0-9]+")
        self.filter_name_input.setEnabled(False)
        self.filter_name_check.toggled.connect(self.filter_name_input.setEnabled)
        name_layout.addWidget(self.filter_name_check)
        name_layout.addWidget(self.filter_name_input)
        name_layout.addStretch()
        filters_layout.addLayout(name_layout)

        # File size filter
        size_layout = QHBoxLayout()
        self.filter_size_check = QCheckBox("Filter by size (MB):")
        self.filter_size_min = QDoubleSpinBox()
        self.filter_size_min.setMinimum(0.0)
        self.filter_size_min.setMaximum(999999.0)
        self.filter_size_min.setSingleStep(0.1)
        self.filter_size_min.setEnabled(False)
        self.filter_size_max = QDoubleSpinBox()
        self.filter_size_max.setMinimum(0.0)
        self.filter_size_max.setMaximum(999999.0)
        self.filter_size_max.setSingleStep(0.1)
        self.filter_size_max.setValue(100.0)
        self.filter_size_max.setEnabled(False)
        self.filter_size_check.toggled.connect(self.filter_size_min.setEnabled)
        self.filter_size_check.toggled.connect(self.filter_size_max.setEnabled)
        size_layout.addWidget(self.filter_size_check)
        size_layout.addWidget(QLabel("Min:"))
        size_layout.addWidget(self.filter_size_min)
        size_layout.addWidget(QLabel("Max:"))
        size_layout.addWidget(self.filter_size_max)
        size_layout.addStretch()
        filters_layout.addLayout(size_layout)

        # Dimensions filter
        dim_layout = QHBoxLayout()
        self.filter_dim_check = QCheckBox("Min dimensions (px):")
        self.filter_width_min = QSpinBox()
        self.filter_width_min.setMinimum(0)
        self.filter_width_min.setMaximum(99999)
        self.filter_width_min.setEnabled(False)
        self.filter_height_min = QSpinBox()
        self.filter_height_min.setMinimum(0)
        self.filter_height_min.setMaximum(99999)
        self.filter_height_min.setEnabled(False)
        self.filter_dim_check.toggled.connect(self.filter_width_min.setEnabled)
        self.filter_dim_check.toggled.connect(self.filter_height_min.setEnabled)
        dim_layout.addWidget(self.filter_dim_check)
        dim_layout.addWidget(QLabel("Width:"))
        dim_layout.addWidget(self.filter_width_min)
        dim_layout.addWidget(QLabel("Height:"))
        dim_layout.addWidget(self.filter_height_min)
        dim_layout.addStretch()
        filters_layout.addLayout(dim_layout)

        # Filter action buttons
        button_layout = QHBoxLayout()
        self.apply_filters_button = QPushButton("Apply Filters")
        self.apply_filters_button.clicked.connect(self.apply_filters)
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
        self.clear_filters_button = QPushButton("Clear Filters")
        self.clear_filters_button.clicked.connect(self.clear_filters)
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
        button_layout.addWidget(self.apply_filters_button)
        button_layout.addWidget(self.clear_filters_button)
        button_layout.addStretch()
        filters_layout.addLayout(button_layout)

        results_layout.addWidget(self.filters_container)

        # Track filter state
        self.filters_visible = False
        self.original_results = []
        self.is_filtered = False

        # Main content area
        self.content_layout = QHBoxLayout()

        # Left side - Original search image (2/5 of width)
        self.left_panel = QWidget()
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.addWidget(QLabel("Search Image:"))

        self.photo_main = ZoomableImageViewer("Drop an image here to search")
        self.photo_main.setMinimumSize(300, 250)
        left_layout.addWidget(self.photo_main)

        # Middle - Result viewer (2/5 of width)
        self.middle_panel = QWidget()
        middle_layout = QVBoxLayout(self.middle_panel)
        middle_layout.addWidget(QLabel("Result Image:"))

        self.photo_viewer = ZoomableImageViewer("Results will appear here")
        self.photo_viewer.setMinimumSize(300, 250)
        middle_layout.addWidget(self.photo_viewer)

        # Right side - Results list (1/5 of width)
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.addWidget(QLabel("File List:"))

        self.list_widget = QListWidget()
        self.list_widget.setMinimumWidth(150)
        right_layout.addWidget(self.list_widget)

        # Add panels with specific stretch factors (2:2:1 ratio)
        self.content_layout.addWidget(self.left_panel, 2)
        self.content_layout.addWidget(self.middle_panel, 2)
        self.content_layout.addWidget(self.right_panel, 1)

        results_layout.addLayout(self.content_layout)

        # Track visibility states
        self.search_image_visible = True
        self.file_list_visible = True

        # Thumbnails container (initially hidden)
        self.thumbnails_container = QWidget()
        self.thumbnails_container.setMaximumHeight(400)  # Increased height for grid layout
        self.thumbnails_container.setVisible(False)
        self.thumbnails_container.setStyleSheet("QWidget { background-color: transparent; }")

        # Container layout
        container_layout = QVBoxLayout(self.thumbnails_container)
        container_layout.addWidget(QLabel("Thumbnails:"))

        # Thumbnails scroll area
        self.thumbnails_scroll = QScrollArea()
        self.thumbnails_scroll.setWidgetResizable(True)
        self.thumbnails_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumbnails_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.thumbnails_scroll.setStyleSheet(
            """
            QScrollArea {
                background-color: transparent;
                border: 1px solid #999;
            }
        """
        )

        # Thumbnails widget
        self.thumbnails_widget = QWidget()
        self.thumbnails_layout = QGridLayout(self.thumbnails_widget)
        self.thumbnails_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.thumbnails_layout.setSpacing(10)
        self.thumbnails_scroll.setWidget(self.thumbnails_widget)

        # Add scroll area to container
        container_layout.addWidget(self.thumbnails_scroll)

        results_layout.addWidget(self.thumbnails_container)

        # Note: FilterManager's setup_result_filters expects a grid layout but we have VBox
        # For now, skip the filter setup to avoid errors
        # TODO: Either update FilterManager or add filters manually

        self.tab_widget.addTab(results_widget, "Search Results")

        # Track thumbnail visibility
        self.thumbnails_visible = False

        # Add pagination controls for thumbnails
        pagination_layout = QHBoxLayout()

        self.prev_page_button = QPushButton("Previous Page")
        self.prev_page_button.clicked.connect(self.prev_thumbnail_page)
        self.prev_page_button.setEnabled(False)
        pagination_layout.addWidget(self.prev_page_button)

        self.page_label = QLabel("Page 1 of 1")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pagination_layout.addWidget(self.page_label)

        self.next_page_button = QPushButton("Next Page")
        self.next_page_button.clicked.connect(self.next_thumbnail_page)
        self.next_page_button.setEnabled(False)
        pagination_layout.addWidget(self.next_page_button)

        pagination_layout.addStretch()

        container_layout.addLayout(pagination_layout)

        # Settings tab
        settings_widget = QWidget()
        settings_layout = QVBoxLayout(settings_widget)

        # VP-Tree path
        vp_tree_layout = QHBoxLayout()
        vp_tree_layout.addWidget(QLabel("VP-Tree Path:"))
        self.vp_tree_dir = QLineEdit()
        self.vp_tree_dir.setText(os.path.join(self.dir_path, "VPtree.pickle"))
        vp_tree_layout.addWidget(self.vp_tree_dir)
        settings_layout.addLayout(vp_tree_layout)

        # Hash path
        hash_layout = QHBoxLayout()
        hash_layout.addWidget(QLabel("Hash Path:"))
        self.hash_dir = QLineEdit()
        self.hash_dir.setText(os.path.join(self.dir_path, "Hashing.pickle"))
        hash_layout.addWidget(self.hash_dir)
        settings_layout.addLayout(hash_layout)

        # Save settings button
        self.save_settings_button = QPushButton("Save Settings")
        settings_layout.addWidget(self.save_settings_button)

        # Theme selector
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel("Theme:"))
        self.theme_selector = QComboBox()
        self.theme_selector.addItems(["Light", "Dark"])
        theme_layout.addWidget(self.theme_selector)
        theme_layout.addStretch()
        settings_layout.addLayout(theme_layout)

        # Add missing UI elements for compatibility
        self.image_clear_button = QPushButton("Clear Image")
        self.image_clear_button.setEnabled(False)
        settings_layout.addWidget(self.image_clear_button)

        self.metadata_button = QPushButton("View Metadata")
        self.metadata_button.setEnabled(False)
        settings_layout.addWidget(self.metadata_button)

        # Indexing settings
        indexing_group = QGroupBox("Database Indexing")
        indexing_layout = QVBoxLayout(indexing_group)

        # Directory selection for indexing
        index_dir_layout = QHBoxLayout()
        index_dir_layout.addWidget(QLabel("Index Directory:"))
        self.index_directory = QLineEdit()
        self.index_directory.setText(os.path.expanduser("~"))  # Default to home directory
        self.index_directory.setPlaceholderText("Select directory to index...")
        index_dir_layout.addWidget(self.index_directory)

        self.browse_index_button = QPushButton("Browse...")
        self.browse_index_button.clicked.connect(self.browse_index_directory)
        index_dir_layout.addWidget(self.browse_index_button)

        indexing_layout.addLayout(index_dir_layout)

        # Add cleanup checkbox
        self.cleanup_non_existing_check = QCheckBox("Clean up non-existing files in this path")
        self.cleanup_non_existing_check.setToolTip(
            "Remove database entries for files that no longer exist in the indexed directory and its subdirectories"
        )
        indexing_layout.addWidget(self.cleanup_non_existing_check)

        self.index_button = QPushButton("Start Indexing")
        self.index_button.setToolTip("Loading database...")
        indexing_layout.addWidget(self.index_button)

        self.stop_index_button = QPushButton("Stop Indexing")
        self.stop_index_button.setEnabled(False)
        indexing_layout.addWidget(self.stop_index_button)

        settings_layout.addWidget(indexing_group)

        # Directory removal section
        removal_group = QGroupBox("Remove Directory from Database")
        removal_layout = QVBoxLayout(removal_group)

        # Directory selection for removal
        remove_dir_layout = QHBoxLayout()
        remove_dir_layout.addWidget(QLabel("Directory to Remove:"))
        self.remove_directory = QLineEdit()
        self.remove_directory.setPlaceholderText("Enter directory path to remove from database...")
        remove_dir_layout.addWidget(self.remove_directory)

        self.browse_remove_button = QPushButton("Browse...")
        self.browse_remove_button.clicked.connect(self.browse_remove_directory)
        remove_dir_layout.addWidget(self.browse_remove_button)

        removal_layout.addLayout(remove_dir_layout)

        # Add information label
        info_label = QLabel(
            "⚠️ This will remove all image entries from this directory and its subdirectories from the database."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #ff6b6b; font-size: 10pt; padding: 5px;")
        removal_layout.addWidget(info_label)

        # Remove button
        self.remove_dir_button = QPushButton("Remove Directory from Database")
        self.remove_dir_button.setStyleSheet(
            """
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """
        )
        self.remove_dir_button.clicked.connect(self.remove_directory_from_database)
        removal_layout.addWidget(self.remove_dir_button)

        settings_layout.addWidget(removal_group)

        # Migration section
        migration_group = QGroupBox("Database Migration")
        migration_layout = QVBoxLayout(migration_group)

        # Migration status
        migration_status_layout = QHBoxLayout()
        self.migration_status_label = QLabel("Database Status:")
        migration_status_layout.addWidget(self.migration_status_label)

        # Check migration status (database might not be initialized yet)
        if self.database_manager and self.database_manager.is_migrated():
            status_text = "✓ Using SQLite (optimized)"
            status_color = "green"
        elif self.database_manager:
            status_text = "Using Pickle (legacy)"
            status_color = "orange"
        else:
            status_text = "Loading..."
            status_color = "gray"

        self.migration_status_value = QLabel(status_text)
        self.migration_status_value.setStyleSheet(f"color: {status_color}; font-weight: bold;")
        migration_status_layout.addWidget(self.migration_status_value)

        # Help button with tooltip
        self.migration_help_button = QPushButton("?")
        self.migration_help_button.setMaximumWidth(30)
        self.migration_help_button.setStyleSheet(
            """
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                border-radius: 15px;
                padding: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """
        )
        self.migration_help_button.setToolTip(
            "<html><body style='font-size: 11pt;'>"
            "<h3>Database Migration Information</h3>"
            "<p><b>Current System:</b></p>"
            "<ul>"
            "<li><b>Pickle:</b> Legacy format, loads entire database into memory</li>"
            "<li><b>SQLite:</b> Modern database, better performance for large datasets</li>"
            "</ul>"
            "<p><b>Benefits of Migration:</b></p>"
            "<ul>"
            "<li>50-70% faster cleanup operations</li>"
            "<li>40-60% less memory usage</li>"
            "<li>20-30% faster incremental indexing</li>"
            "<li>Better handling of duplicates</li>"
            "<li>Concurrent read access</li>"
            "</ul>"
            "<p><b>Hybrid Approach:</b></p>"
            "<ul>"
            "<li>VP-Tree remains in pickle format (optimal for similarity search)</li>"
            "<li>Hash database migrates to SQLite (better for lookups)</li>"
            "</ul>"
            "<p><b>Migration Process:</b></p>"
            "<ol>"
            "<li>Creates backup of current pickle file</li>"
            "<li>Converts hash data to SQLite format</li>"
            "<li>Verifies data integrity</li>"
            "<li>Application automatically uses new format</li>"
            "</ol>"
            "<p><i>Migration is one-time and reversible via backup.</i></p>"
            "</body></html>"
        )
        migration_status_layout.addWidget(self.migration_help_button)
        migration_status_layout.addStretch()

        migration_layout.addLayout(migration_status_layout)

        # Migration button
        self.migrate_button = QPushButton("Migrate to SQLite Database")
        if self.database_manager and self.database_manager.is_migrated():
            self.migrate_button.setEnabled(False)
            self.migrate_button.setText("Already Migrated")
            self.migrate_button.setStyleSheet("QPushButton { color: gray; }")
        elif self.database_manager:
            self.migrate_button.setEnabled(True)
            self.migrate_button.setStyleSheet(
                """
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    font-weight: bold;
                    padding: 8px;
                    border-radius: 4px;
                }
                QPushButton:hover:enabled {
                    background-color: #1976D2;
                }
                QPushButton:disabled {
                    background-color: #cccccc;
                    color: #666666;
                }
            """
            )
        self.migrate_button.clicked.connect(self.perform_migration)
        migration_layout.addWidget(self.migrate_button)

        # Database statistics
        self.db_stats_label = QLabel("Loading statistics...")
        self.db_stats_label.setStyleSheet("font-size: 10pt; color: #666;")
        migration_layout.addWidget(self.db_stats_label)

        # Update database statistics
        self.update_db_statistics()

        settings_layout.addWidget(migration_group)

        settings_layout.addStretch()

        self.tab_widget.addTab(settings_widget, "Settings")

        # Logging tab
        logging_widget = QWidget()
        logging_layout = QVBoxLayout(logging_widget)

        # Add log box to the logging tab
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        logging_layout.addWidget(self.log_box)

        # Add clear log button
        clear_log_button = QPushButton("Clear Log")
        clear_log_button.clicked.connect(self.clear_log)
        logging_layout.addWidget(clear_log_button)

        self.tab_widget.addTab(logging_widget, "Logging")

        # History tab - will be set up after manager is initialized
        history_placeholder = QWidget()
        self.tab_widget.addTab(history_placeholder, "History")
        self.history_tab_index = self.tab_widget.indexOf(history_placeholder)

        # Duplicates tab - for managing duplicate images
        try:
            from src.ui.duplicates_tab import DuplicatesTab

            duplicates_widget = DuplicatesTab(self)
            self.tab_widget.addTab(duplicates_widget, "Duplicates")
            self.duplicates_tab = duplicates_widget
        except ImportError as e:
            self.log_message(f"Could not load Duplicates tab: {e}")

        main_layout.addWidget(self.tab_widget)

        # Navigation buttons
        nav_layout = QHBoxLayout()
        self.previous_button = QPushButton("Previous")
        self.previous_button.setEnabled(False)
        self.next_button = QPushButton("Next")
        self.next_button.setEnabled(False)
        self.open_image_button = QPushButton("Open Folder")
        self.open_image_button.setEnabled(False)

        nav_layout.addWidget(self.previous_button)
        nav_layout.addWidget(self.next_button)
        nav_layout.addWidget(self.open_image_button)

        main_layout.addLayout(nav_layout)

        # Status labels
        status_layout = QHBoxLayout()
        self.label_result = QLabel("Results: 0")
        self.label_current = QLabel("Current: 0/0")
        self.label_total_images = QLabel("Total Images in Database: 0")
        status_layout.addWidget(self.label_result)
        status_layout.addWidget(self.label_current)
        status_layout.addWidget(self.label_total_images)
        status_layout.addStretch()

        main_layout.addLayout(status_layout)

        # Store some required attributes
        self.images_found = []
        self.display_queue = []
        self.images_lock = QtCore.QMutex()
        self.queue_lock = QtCore.QMutex()
        self.current_lock = QtCore.QMutex()
        self.thread = None
        self.worker = None

        # Additional UI attributes for compatibility
        self.parallel_workers = QSpinBox()
        self.parallel_workers.setValue(4)
        self.similarity_threshold = QSpinBox()
        self.similarity_threshold.setValue(90)
        self.file_type_check = QCheckBox()
        self.file_type_filter = QLineEdit()
        self.file_size_check = QCheckBox()
        self.min_size_spin = QSpinBox()
        self.max_size_spin = QSpinBox()
        self.dimensions_check = QCheckBox()
        self.min_width_spin = QSpinBox()
        self.min_height_spin = QSpinBox()

        # Additional attributes for HistoryManager compatibility
        self.current_image_index = 0
        self.found_label = QLabel("0")
        self.curr_img = QLabel("0")

        # Set up status bar (fast)
        self.setup_status_bar()

        # Add Help menu for keyboard shortcuts
        self.setup_help_menu()

        # Initially disable database-dependent controls
        self.set_database_dependent_controls(False)

    def setup_status_bar(self):
        """Set up the status bar."""
        self.status_bar = self.statusBar()
        self.status_bar.setStyleSheet("QStatusBar { background-color: #f0f0f0; }")
        self.status_label = QLabel("Ready")
        self.status_bar.addPermanentWidget(self.status_label)

        # Add keyboard shortcuts hint to status bar
        self.shortcuts_hint = QLabel("Press F1 for keyboard shortcuts")
        self.shortcuts_hint.setStyleSheet("color: #666; font-style: italic;")
        self.status_bar.addWidget(self.shortcuts_hint)

        self.update_status_bar("Ready")

    def setup_help_menu(self):
        """Set up the Help menu in the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        open_action = QAction("&Open Image", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_image_file)
        file_menu.addAction(open_action)

        save_action = QAction("&Save Results", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_search_results)
        file_menu.addAction(save_action)

        export_html_action = QAction("Export to &HTML", self)
        export_html_action.setShortcut("Ctrl+E")
        export_html_action.triggered.connect(self.export_results_to_html)
        file_menu.addAction(export_html_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        clear_action = QAction("&Clear Results", self)
        clear_action.setShortcut("Ctrl+Shift+C")
        clear_action.triggered.connect(self.clear_search_results)
        edit_menu.addAction(clear_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        toggle_search_action = QAction("Toggle &Search Image", self)
        toggle_search_action.setShortcut("Alt+S")
        toggle_search_action.triggered.connect(self.toggle_search_image)
        view_menu.addAction(toggle_search_action)

        toggle_list_action = QAction("Toggle File &List", self)
        toggle_list_action.setShortcut("Alt+L")
        toggle_list_action.triggered.connect(self.toggle_file_list)
        view_menu.addAction(toggle_list_action)

        toggle_thumbnails_action = QAction("Toggle &Thumbnails", self)
        toggle_thumbnails_action.setShortcut("Alt+T")
        toggle_thumbnails_action.triggered.connect(self.toggle_thumbnails)
        view_menu.addAction(toggle_thumbnails_action)

        toggle_filters_action = QAction("Toggle F&ilters", self)
        toggle_filters_action.setShortcut("Alt+I")
        toggle_filters_action.triggered.connect(self.toggle_filters)
        view_menu.addAction(toggle_filters_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        shortcuts_action = QAction("&Keyboard Shortcuts", self)
        shortcuts_action.setShortcut("F1")
        shortcuts_action.triggered.connect(self.show_shortcuts_dialog)
        help_menu.addAction(shortcuts_action)

        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def setup_keyboard_shortcuts(self):
        """Set up keyboard shortcuts for the application."""
        # Navigation shortcuts (not in menu, so keep as QShortcut)
        QShortcut(QKeySequence("Left"), self, self.navigate_previous)
        QShortcut(QKeySequence("Right"), self, self.navigate_next)
        QShortcut(QKeySequence("Up"), self, self.navigate_previous)
        QShortcut(QKeySequence("Down"), self, self.navigate_next)
        QShortcut(QKeySequence("PgUp"), self, self.prev_thumbnail_page)
        QShortcut(QKeySequence("PgDown"), self, self.next_thumbnail_page)

        # Tab navigation (not in menu, so keep as QShortcut)
        QShortcut(
            QKeySequence("Ctrl+1"), self, lambda: self.tab_widget.setCurrentIndex(0)
        )  # Search Results
        QShortcut(
            QKeySequence("Ctrl+2"), self, lambda: self.tab_widget.setCurrentIndex(1)
        )  # Settings
        QShortcut(
            QKeySequence("Ctrl+3"), self, lambda: self.tab_widget.setCurrentIndex(2)
        )  # Logging
        QShortcut(
            QKeySequence("Ctrl+4"), self, lambda: self.tab_widget.setCurrentIndex(3)
        )  # History
        if hasattr(self, "duplicates_tab"):
            QShortcut(
                QKeySequence("Ctrl+5"), self, lambda: self.tab_widget.setCurrentIndex(4)
            )  # Duplicates

        # Quick actions (some are duplicated in menu, so only add non-menu ones)
        QShortcut(QKeySequence("Ctrl+D"), self, self.start_indexing)
        QShortcut(QKeySequence("Ctrl+Return"), self, self.start_search)
        QShortcut(QKeySequence("Ctrl+Shift+Return"), self, self.open_current_image)
        QShortcut(QKeySequence("Escape"), self, self.clear_search_results)

        # View toggles (duplicated in menu, so we'll just use the menu actions)
        # Removed to avoid ambiguous shortcut warnings

        # Filter shortcuts (unique, not in menu)
        QShortcut(
            QKeySequence("Ctrl+Shift+F"), self, lambda: self.filters_container.setVisible(True)
        )
        QShortcut(QKeySequence("Ctrl+Shift+A"), self, self.apply_filters)
        # Ctrl+Shift+C is already in Edit menu for Clear Results

        # Help (F1 is already in menu, so we don't need it here)

    def show_shortcuts_dialog(self):
        """Show a dialog with all keyboard shortcuts."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Keyboard Shortcuts")
        dialog.setModal(True)
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(500)

        layout = QVBoxLayout(dialog)

        # Create a text widget to display shortcuts
        shortcuts_text = QTextEdit()
        shortcuts_text.setReadOnly(True)
        shortcuts_text.setHtml(
            """
        <style>
            body { font-family: Arial, sans-serif; }
            h2 { color: #0d7377; margin-top: 15px; }
            table { width: 100%; border-collapse: collapse; }
            td { padding: 5px; border-bottom: 1px solid #ddd; }
            td:first-child { font-weight: bold; width: 40%; background-color: #f5f5f5; }
            .category { background-color: #e0e0e0; font-weight: bold; text-align: center; }
        </style>
        
        <h1>Keyboard Shortcuts</h1>
        
        <table>
        <tr><td colspan="2" class="category">Navigation</td></tr>
        <tr><td>← / ↑</td><td>Previous image</td></tr>
        <tr><td>→ / ↓</td><td>Next image</td></tr>
        <tr><td>Page Up</td><td>Previous thumbnail page</td></tr>
        <tr><td>Page Down</td><td>Next thumbnail page</td></tr>
        
        <tr><td colspan="2" class="category">Tab Navigation</td></tr>
        <tr><td>Ctrl+1</td><td>Search Results tab</td></tr>
        <tr><td>Ctrl+2</td><td>Settings tab</td></tr>
        <tr><td>Ctrl+3</td><td>Logging tab</td></tr>
        <tr><td>Ctrl+4</td><td>History tab</td></tr>
        <tr><td>Ctrl+5</td><td>Duplicates tab</td></tr>
        
        <tr><td colspan="2" class="category">File Operations</td></tr>
        <tr><td>Ctrl+O</td><td>Open image file</td></tr>
        <tr><td>Ctrl+S</td><td>Save search results</td></tr>
        <tr><td>Ctrl+E</td><td>Export to HTML with thumbnails</td></tr>
        <tr><td>Ctrl+Q</td><td>Exit application</td></tr>
        
        <tr><td colspan="2" class="category">Search Operations</td></tr>
        <tr><td>Ctrl+Enter</td><td>Start search</td></tr>
        <tr><td>Ctrl+D</td><td>Start database indexing</td></tr>
        <tr><td>Ctrl+Shift+Enter</td><td>Open current image folder</td></tr>
        <tr><td>Escape</td><td>Clear search results</td></tr>
        
        <tr><td colspan="2" class="category">View Toggles</td></tr>
        <tr><td>Alt+S</td><td>Toggle search image panel</td></tr>
        <tr><td>Alt+L</td><td>Toggle file list panel</td></tr>
        <tr><td>Alt+T</td><td>Toggle thumbnails</td></tr>
        <tr><td>Alt+I</td><td>Toggle filters</td></tr>
        
        <tr><td colspan="2" class="category">Filter Operations</td></tr>
        <tr><td>Ctrl+Shift+F</td><td>Show filters</td></tr>
        <tr><td>Ctrl+Shift+A</td><td>Apply filters</td></tr>
        <tr><td>Ctrl+Shift+C</td><td>Clear filters</td></tr>
        
        <tr><td colspan="2" class="category">Help</td></tr>
        <tr><td>F1</td><td>Show this help</td></tr>
        </table>
        
        <p style="margin-top: 20px; color: #666;">
        <i>Tip: You can also drag and drop images directly into the application!</i>
        </p>
        """
        )

        layout.addWidget(shortcuts_text)

        # Add close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        dialog.exec()

    def show_about_dialog(self):
        """Show about dialog."""
        from PyQt6.QtWidgets import QMessageBox

        QMessageBox.about(
            self,
            "About Offline Reverse Image Search",
            "<h2>Offline Reverse Image Search</h2>"
            "<p>A powerful tool for finding similar images in your local collection.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Fast image similarity search using VP-Tree algorithm</li>"
            "<li>Duplicate detection with dHash</li>"
            "<li>SQLite database for efficient storage</li>"
            "<li>Thumbnail preview with pagination</li>"
            "<li>Advanced filtering options</li>"
            "</ul>"
            "<p><b>Version:</b> 1.0.0</p>",
        )

    def open_image_file(self):
        """Open an image file using file dialog."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Image File",
            self.dir_path,
            "Image Files (*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp);;All Files (*.*)",
        )
        if file_path:
            self.display_image(file_path)

    def save_search_results(self):
        """Save current search results to a file."""
        if not hasattr(self, "images_found") or not self.images_found:
            self.log_message("No search results to save")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Search Results",
            os.path.join(self.dir_path, "search_results.txt"),
            "Text Files (*.txt);;CSV Files (*.csv);;All Files (*.*)",
        )

        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"Search Results - {len(self.images_found)} images found\n")
                    f.write(f"Search Image: {self.current_image_path}\n")
                    f.write(f"Search Range: {self.search_range.value()}\n")
                    f.write("-" * 80 + "\n\n")

                    for i, image_path in enumerate(self.images_found, 1):
                        f.write(f"{i}. {image_path}\n")

                        # Add duplicate info if available
                        if hasattr(self, "image_hashes") and image_path in self.image_hashes:
                            img_hash = self.image_hashes[image_path]
                            if hasattr(self, "hash_to_paths") and img_hash in self.hash_to_paths:
                                dup_count = len(self.hash_to_paths[img_hash])
                                if dup_count > 1:
                                    f.write(f"   Duplicates ({dup_count} total):\n")
                                    for dup_path in self.hash_to_paths[img_hash]:
                                        if dup_path != image_path:
                                            f.write(f"   - {dup_path}\n")

                self.log_message(f"Search results saved to: {file_path}")
            except Exception as e:
                self.log_message(f"Error saving search results: {str(e)}")

    def export_results_to_html(self):
        """Export current search results to an interactive HTML file with pagination."""
        if not hasattr(self, "images_found") or not self.images_found:
            self.log_message("No search results to export")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Search Results to HTML",
            os.path.join(self.dir_path, "search_results.html"),
            "HTML Files (*.html);;All Files (*.*)",
        )

        if file_path:
            try:
                from PyQt6.QtCore import Qt
                from PyQt6.QtWidgets import QProgressDialog

                # Prepare duplicate info if available
                duplicates_info = {}
                if hasattr(self, "image_hashes") and hasattr(self, "hash_to_paths"):
                    for image_path in self.images_found:
                        if image_path in self.image_hashes:
                            img_hash = self.image_hashes[image_path]
                            if img_hash in self.hash_to_paths:
                                duplicates_info[image_path] = len(self.hash_to_paths[img_hash])

                # Create progress dialog
                progress_dialog = QProgressDialog(
                    "Preparing export with pagination...", "Cancel", 0, 100, self
                )
                progress_dialog.setWindowTitle("Exporting to HTML (Advanced)")
                progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
                progress_dialog.setMinimumDuration(0)
                progress_dialog.show()

                # Create worker thread with pagination
                self.export_worker = PaginatedHTMLExportWorker(
                    self.current_image_path,
                    self.images_found,
                    file_path,
                    self.search_range.value() if hasattr(self, "search_range") else 6,
                    duplicates_info,
                    items_per_page=50,  # Configurable items per page
                )

                # Connect signals
                self.export_worker.progress.connect(
                    lambda pct, msg: self.on_export_progress(progress_dialog, pct, msg)
                )
                self.export_worker.finished.connect(
                    lambda success, msg: self.on_export_finished(
                        progress_dialog, success, msg, file_path
                    )
                )

                # Handle cancellation
                progress_dialog.canceled.connect(self.export_worker.cancel)

                # Start the worker
                self.export_worker.start()

            except Exception as e:
                self.log_message(f"Error starting HTML export: {str(e)}")

    def on_export_progress(self, dialog, percentage, message):
        """Handle export progress updates."""
        if dialog and not dialog.wasCanceled():
            dialog.setValue(percentage)
            dialog.setLabelText(message)

    def on_export_finished(self, dialog, success, message, file_path):
        """Handle export completion."""
        if dialog:
            dialog.close()

        if success:
            self.log_message(message)
            # Try to open in browser
            try:
                import webbrowser

                webbrowser.open(f"file:///{file_path}")
            except:
                pass
        else:
            self.log_message(f"Export failed: {message}")

        # Clean up worker
        if hasattr(self, "export_worker"):
            self.export_worker.quit()
            self.export_worker.wait()
            self.export_worker.deleteLater()
            self.export_worker = None

    def update_status_bar(self, message: str):
        """Update the status bar with a new message."""
        if hasattr(self, "status_label"):
            self.status_label.setText(message)

    def connect_signals(self):
        """Connect all signals and slots."""
        # Connect basic UI signals
        self.search_button.clicked.connect(self.start_search)
        self.index_button.clicked.connect(self.start_indexing)
        self.stop_index_button.clicked.connect(self.stop_indexing)
        self.save_settings_button.clicked.connect(self.save_settings)

        # Connect theme selector only after theme manager exists
        if hasattr(self, "theme_manager"):
            self.theme_selector.currentTextChanged.connect(self.theme_manager.apply_theme)

        # Connect navigation buttons
        self.previous_button.clicked.connect(self.navigate_previous)
        self.next_button.clicked.connect(self.navigate_next)
        self.open_image_button.clicked.connect(self.open_current_image)

        # Connect file handler signals (if file handler exists)
        if hasattr(self, "file_handler"):
            self.file_handler.file_ready.connect(self.display_image)

        # Connect list widget selection
        self.list_widget.itemClicked.connect(self.on_result_selected)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_list_context_menu)

        # Track current thumbnail column count (default to 4 as expected)
        self.current_thumbnail_columns = 4

        # Setup resize timer to debounce resize events
        self.resize_timer = QTimer()
        self.resize_timer.timeout.connect(self.on_resize_finished)
        self.resize_timer.setSingleShot(True)

        # Pagination for thumbnails
        self.thumbnails_per_page = 50
        self.current_thumbnail_page = 0
        self.total_thumbnail_pages = 0

        # Initialize thumbnail loader
        self.thumbnail_loader = ThumbnailLoaderManager(self)

        # Set up history tab if manager exists
        if hasattr(self, "history_manager") and hasattr(self, "history_tab_index"):
            self.tab_widget.removeTab(self.history_tab_index)
            self.history_manager.setup_search_history_tab(self.tab_widget)

    def on_file_ready(self, file_path: str):
        """Handle when a file is ready from drag/drop or other sources."""
        self.file_path = file_path
        self.main_image_path = file_path
        self.display_image(file_path)

    def append_colored_text(self, text: str, color: QtGui.QColor):
        """Append colored text to the log box."""
        if hasattr(self, "log_box"):
            cursor = self.log_box.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)

            format = cursor.charFormat()
            format.setForeground(color)
            cursor.setCharFormat(format)

            cursor.insertText(
                f"[{QtCore.QDateTime.currentDateTime().toString('hh:mm:ss')}] {text}\n"
            )
            self.log_box.setTextCursor(cursor)
            self.log_box.ensureCursorVisible()

    def log_box_append(self, text: str):
        """Append text to the log box."""
        self.log_message(text)

    def log_message(self, message: str):
        """Log a message to the application log."""
        if hasattr(self, "log_box"):
            self.log_box.append(
                f"[{QtCore.QDateTime.currentDateTime().toString('hh:mm:ss')}] {message}"
            )
            # Auto-scroll to bottom
            self.log_box.ensureCursorVisible()

    def clear_log(self):
        """Clear the log box."""
        if hasattr(self, "log_box"):
            self.log_box.clear()
            self.log_message("Log cleared")

    def closeEvent(self, event: QtGui.QCloseEvent):
        """Handle window close event."""
        # Clean up any running export workers
        if hasattr(self, "export_worker") and self.export_worker:
            self.export_worker.cancel()
            self.export_worker.quit()
            self.export_worker.wait()

        # Save settings
        # self.settings.save_window_geometry(self.saveGeometry(), self.saveState())

        # Cleanup
        # self.search_manager.cleanup_threads()
        # self.index_manager.cleanup_threads()
        # self.file_handler.cleanup_test_file()

        event.accept()

    def resizeEvent(self, event):
        """Handle window resize events."""
        super().resizeEvent(event)

        # Start/restart the timer - this debounces resize events
        if hasattr(self, "resize_timer"):
            self.resize_timer.stop()
            self.resize_timer.start(300)  # Wait 300ms after resize stops

    def calculate_thumbnail_columns(self):
        """Calculate the optimal number of thumbnail columns based on available width."""
        if hasattr(self, "thumbnails_scroll") and self.thumbnails_scroll.isVisible():
            # Get available width (subtract some margin for scrollbar)
            available_width = self.thumbnails_scroll.viewport().width()
            if available_width <= 0:
                # If viewport width not available, try multiple fallbacks
                if self.thumbnails_container.isVisible():
                    available_width = self.thumbnails_container.width() - 40
                if available_width <= 0:
                    # Use main window width as last resort
                    available_width = self.width() - 100  # Account for margins

            # Thumbnail size (from ThumbnailWidget)
            thumbnail_width = 120  # Base thumbnail width
            spacing = 10  # Spacing between thumbnails

            # Calculate how many columns can fit
            if available_width > 0:
                columns = max(1, (available_width - spacing) // (thumbnail_width + spacing))
            else:
                # Default to a reasonable number if all else fails
                columns = max(
                    1, (1200 - 100) // (thumbnail_width + spacing)
                )  # Based on default window width

            # Update the column count if it changed
            if hasattr(self, "current_thumbnail_columns"):
                old_columns = self.current_thumbnail_columns
                self.current_thumbnail_columns = columns
                return old_columns != columns  # Return True if columns changed
        return False

    def on_resize_finished(self):
        """Called when resize timer expires - window resize has finished."""
        # Update thumbnail layout if thumbnails are visible
        if hasattr(self, "thumbnails_container") and self.thumbnails_container.isVisible():
            # Check if columns changed
            if self.calculate_thumbnail_columns():
                self.rearrange_thumbnails()

    def rearrange_thumbnails(self):
        """Rearrange existing thumbnails without recreating them."""
        if not hasattr(self, "thumbnails_layout"):
            return

        # Get all thumbnail widgets
        thumbnails = []
        for i in range(self.thumbnails_layout.count()):
            item = self.thumbnails_layout.itemAt(i)
            if item and item.widget():
                thumbnails.append(item.widget())

        # Remove all widgets from layout (but don't delete them)
        while self.thumbnails_layout.count():
            self.thumbnails_layout.takeAt(0)

        # Re-add widgets in new grid arrangement
        row = 0
        col = 0
        for thumbnail in thumbnails:
            self.thumbnails_layout.addWidget(thumbnail, row, col)
            col += 1
            if col >= self.current_thumbnail_columns:
                col = 0
                row += 1

    def get_test_file_ext(self) -> str:
        """Get the test file extension."""
        return self.file_handler.test_file_ext

    def save_settings(self):
        """Save application settings."""
        # Update settings with current UI values
        self.settings.vp_tree_path = self.vp_tree_dir.text()
        self.settings.hash_path = self.hash_dir.text()

        # Save index directory if it exists
        if hasattr(self, "index_directory"):
            self.settings.settings.setValue("index_directory", self.index_directory.text())

        # Save cleanup preference
        if hasattr(self, "cleanup_non_existing_check"):
            self.settings.settings.setValue(
                "cleanup_non_existing", self.cleanup_non_existing_check.isChecked()
            )

        # No longer need to save logging settings - always log full paths

        self.settings.save_settings()
        self.log_message("Settings saved successfully")

    def start_search(self):
        """Start the search process."""
        # Check if database is initialized
        if not self.database_manager:
            self.log_message("Database is still loading, please wait...")
            return

        if (
            hasattr(self, "current_image_path")
            and self.current_image_path
            and os.path.isfile(self.current_image_path)
        ):
            # Update file_path to match current_image_path for consistency
            self.file_path = self.current_image_path

            # Show progress indicator
            self.search_progress.setVisible(True)
            self.search_button.setEnabled(False)
            self.search_button.setText("Searching...")
            self.update_status_bar("Search in progress...")

            self.search_manager.worker_thread()
        else:
            self.log_message("Please select a valid image file to search")
            if hasattr(self, "current_image_path"):
                self.log_message(f"Current image path: '{self.current_image_path}'")

    def browse_index_directory(self):
        """Browse for directory to index."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory to Index",
            self.index_directory.text() if self.index_directory.text() else os.path.expanduser("~"),
            QFileDialog.Option.ShowDirsOnly,
        )
        if directory:
            self.index_directory.setText(directory)
            self.log_message(f"Selected index directory: {directory}")

    def browse_remove_directory(self):
        """Browse for directory to remove from database."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Directory to Remove from Database",
            (
                self.remove_directory.text()
                if self.remove_directory.text()
                else os.path.expanduser("~")
            ),
            QFileDialog.Option.ShowDirsOnly,
        )
        if directory:
            self.remove_directory.setText(directory)
            self.log_message(f"Selected directory for removal: {directory}")

    def remove_directory_from_database(self):
        """Remove all entries from a specific directory from the database."""
        # Check if database is initialized
        if not self.database_manager:
            self.log_message("Database is still loading, please wait...")
            return

        if not hasattr(self, "remove_directory"):
            self.log_message("Remove directory field not found")
            return

        remove_dir = self.remove_directory.text()
        if not remove_dir:
            self.log_message("Please enter a directory path to remove")
            return

        # Confirm with user
        from PyQt6.QtWidgets import QMessageBox

        reply = QMessageBox.question(
            self,
            "Confirm Directory Removal",
            f"This will remove all database entries for images in:\n\n{remove_dir}\n\n"
            "and all its subdirectories.\n\n"
            "This operation cannot be undone.\n\n"
            "Do you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Create progress dialog
            from PyQt6.QtCore import Qt
            from PyQt6.QtWidgets import QProgressDialog

            progress_dialog = QProgressDialog(
                f"Removing entries from:\n{remove_dir}",
                None,  # No cancel button for this operation
                0,
                0,  # Indeterminate progress
                self,
            )
            progress_dialog.setWindowTitle("Removing Directory from Database")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.setMinimumWidth(400)
            progress_dialog.show()
            QApplication.processEvents()

            # Perform the removal
            removed_count, orphaned_hashes = self.perform_directory_removal(remove_dir)

            # Close progress dialog
            progress_dialog.close()

            # Show results
            if removed_count > 0 or orphaned_hashes > 0:
                self.log_message(
                    f"Successfully removed {removed_count} image entries and "
                    f"{orphaned_hashes} orphaned hashes from {remove_dir}"
                )
                QMessageBox.information(
                    self,
                    "Removal Complete",
                    f"Successfully removed:\n"
                    f"• {removed_count} image entries\n"
                    f"• {orphaned_hashes} orphaned hashes\n\n"
                    f"From: {remove_dir}",
                )
                # Update the total images count
                self.update_total_images_count()
            else:
                self.log_message(f"No entries found for directory: {remove_dir}")
                QMessageBox.information(
                    self, "No Entries Found", f"No database entries were found for:\n{remove_dir}"
                )

            # Clear the input field
            self.remove_directory.clear()

    def perform_directory_removal(self, directory: str) -> tuple:
        """
        Remove all entries from a specific directory from the database.
        Returns: (removed_count, orphaned_hashes_removed)
        """
        import pickle

        removed_count = 0
        orphaned_hashes = 0

        # Normalize the directory path for comparison
        remove_dir = os.path.normpath(directory)

        # Get hash database path
        hash_path = (
            self.hash_dir.text()
            if hasattr(self, "hash_dir")
            else os.path.join(self.dir_path, "Hashing.pickle")
        )

        if not os.path.exists(hash_path):
            self.log_message("Hash database not found")
            return 0, 0

        try:
            # Load existing hashes
            with open(hash_path, "rb") as f:
                hashes = pickle.load(f)

            if not hashes:
                return 0, 0

            # Track hashes to remove if they become empty
            hashes_to_remove = []

            # Process each hash entry
            for hash_value, paths in hashes.items():
                # Ensure paths is a list
                if not isinstance(paths, list):
                    paths = [paths]

                # Filter out paths that are in the directory to remove
                remaining_paths = []
                for path in paths:
                    norm_path = os.path.normpath(path)
                    # Check if this path is under the directory to remove
                    if not (norm_path.startswith(remove_dir + os.sep) or norm_path == remove_dir):
                        # Keep this path
                        remaining_paths.append(path)
                    else:
                        # This path will be removed
                        removed_count += 1
                        self.log_message(f"Removing: {path}")

                # Update the hash entry
                if remaining_paths:
                    # Still have some paths for this hash
                    hashes[hash_value] = (
                        remaining_paths if len(remaining_paths) > 1 else remaining_paths[0]
                    )
                else:
                    # No paths left for this hash, mark for removal
                    hashes_to_remove.append(hash_value)
                    orphaned_hashes += 1

            # Remove orphaned hashes
            for hash_value in hashes_to_remove:
                del hashes[hash_value]
                self.log_message(f"Removed orphaned hash: {hash_value}")

            # Save updated hashes back to disk
            with open(hash_path, "wb") as f:
                pickle.dump(hashes, f)

            self.log_message(
                f"Database updated: removed {removed_count} entries and {orphaned_hashes} orphaned hashes"
            )

            # Also update VP-Tree if needed (rebuild without the removed hashes)
            if orphaned_hashes > 0:
                vp_tree_path = (
                    self.vp_tree_dir.text()
                    if hasattr(self, "vp_tree_dir")
                    else os.path.join(self.dir_path, "VPtree.pickle")
                )
                if os.path.exists(vp_tree_path):
                    try:
                        from vptree import VPTree

                        # Rebuild VP-Tree with remaining hashes
                        points = list(hashes.keys())
                        tree = VPTree(points, self.hamming)
                        with open(vp_tree_path, "wb") as f:
                            pickle.dump(tree, f)
                        self.log_message("VP-Tree index updated")
                    except ImportError:
                        self.log_message("VPTree module not available for update")

        except Exception as e:
            self.log_message(f"Error removing directory from database: {str(e)}")
            return 0, 0

        return removed_count, orphaned_hashes

    def start_indexing(self):
        """Start the indexing process."""
        # Check if database is initialized
        if not self.database_manager:
            self.log_message("Database is still loading, please wait...")
            return

        if not hasattr(self, "index_directory"):
            self.log_message("Index directory field not found")
            return

        index_dir = self.index_directory.text()
        if not index_dir or not os.path.isdir(index_dir):
            self.log_message("Please select a valid directory to index")
            return

        # Get cleanup option
        cleanup_non_existing = (
            self.cleanup_non_existing_check.isChecked()
            if hasattr(self, "cleanup_non_existing_check")
            else False
        )

        # Create progress dialog
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QProgressDialog

        self.indexing_progress_dialog = QProgressDialog(
            "Initializing indexing process...\nScanning for images in selected directory...",
            "Cancel",
            0,
            100,
            self,
        )
        self.indexing_progress_dialog.setWindowTitle("Indexing Images")
        self.indexing_progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.indexing_progress_dialog.setMinimumDuration(0)
        self.indexing_progress_dialog.setMinimumWidth(500)
        self.indexing_progress_dialog.show()

        # Pass the directory and cleanup option to the index manager
        self.index_manager.index_directory = index_dir
        self.index_manager.cleanup_non_existing = cleanup_non_existing

        # Connect progress signals to the dialog
        if self.index_manager.worker is None:
            # We need to connect after the worker is created
            # Store the dialog reference for later connection
            self.pending_indexing_dialog = self.indexing_progress_dialog

        self.index_manager.start_indexing()
        self.index_button.setEnabled(False)
        self.stop_index_button.setEnabled(True)

        # Connect cancel button to stop indexing
        self.indexing_progress_dialog.canceled.connect(self.stop_indexing)

        if cleanup_non_existing:
            self.log_message(f"Started indexing directory with cleanup: {index_dir}")
        else:
            self.log_message(f"Started indexing directory: {index_dir}")

    def stop_indexing(self):
        """Stop the indexing process."""
        self.index_manager.stop_indexing()
        self.index_button.setEnabled(True)
        self.stop_index_button.setEnabled(False)

    def display_image(self, image_path: str):
        """Display the selected image."""
        try:
            self.photo_main.set_image(image_path)
            self.label_image.setText(os.path.basename(image_path))
            self.current_image_path = image_path

            # Enable search button only if database is ready
            if self.database_manager:
                self.search_button.setEnabled(True)
                self.search_button.setToolTip("")
            else:
                self.search_button.setEnabled(False)
                self.search_button.setToolTip("Database is still loading...")

            self.log_message(f"Loaded image: {os.path.basename(image_path)}")

            # Clear all old search results when new image is loaded
            self.clear_search_results()

            # Reset pagination
            self.current_thumbnail_page = 0
            self.total_thumbnail_pages = 0
        except Exception as e:
            self.log_message(f"Error loading image: {str(e)}")

    def navigate_previous(self):
        """Navigate to the previous result."""
        if hasattr(self, "current_index") and self.images_found:
            self.current_index = max(0, self.current_index - 1)
            self.display_current_result()

    def navigate_next(self):
        """Navigate to the next result."""
        if hasattr(self, "current_index") and self.images_found:
            self.current_index = min(len(self.images_found) - 1, self.current_index + 1)
            self.display_current_result()

    def open_current_image(self):
        """Open the folder containing the current image."""
        if hasattr(self, "current_result_path") and self.current_result_path:
            # Check if this image has duplicates
            if (
                hasattr(self, "image_hashes")
                and self.current_result_path in self.image_hashes
                and hasattr(self, "hash_to_paths")
            ):

                img_hash = self.image_hashes[self.current_result_path]
                if img_hash in self.hash_to_paths:
                    all_paths = self.hash_to_paths[img_hash]

                    if len(all_paths) > 1:
                        # Multiple duplicates exist - show menu to choose
                        menu = QMenu(self)

                        # Apply theme-aware styling
                        if hasattr(self, "theme_manager") and self.theme_manager.is_dark_theme():
                            menu.setStyleSheet(
                                """
                                QMenu {
                                    background-color: #3c3c3c;
                                    color: #ffffff;
                                    border: 1px solid #555555;
                                    padding: 5px;
                                }
                                QMenu::item {
                                    padding: 5px 20px;
                                    color: #ffffff;
                                }
                                QMenu::item:selected {
                                    background-color: #0d7377;
                                    color: white;
                                }
                                QMenu::item:disabled {
                                    color: #888888;
                                }
                            """
                            )
                        else:
                            menu.setStyleSheet(
                                """
                                QMenu {
                                    background-color: white;
                                    color: #000000;
                                    border: 1px solid #ccc;
                                    padding: 5px;
                                }
                                QMenu::item {
                                    padding: 5px 20px;
                                    color: #000000;
                                }
                                QMenu::item:selected {
                                    background-color: #0d7377;
                                    color: white;
                                }
                                QMenu::item:disabled {
                                    color: #888888;
                                }
                            """
                            )

                        # Add header
                        header_action = menu.addAction(
                            f"Select which location to open ({len(all_paths)} duplicates):"
                        )
                        header_action.setEnabled(False)
                        font = header_action.font()
                        font.setBold(True)
                        header_action.setFont(font)
                        menu.addSeparator()

                        # Add each path option
                        for i, path in enumerate(all_paths):
                            folder = os.path.dirname(path)
                            action = menu.addAction(f"{i+1}. {os.path.basename(path)}")
                            action.setToolTip(f"Open folder: {folder}")

                            if path == self.current_result_path:
                                # Mark current image with bold font only
                                font = action.font()
                                font.setBold(True)
                                action.setFont(font)

                            # Connect to open the specific folder
                            action.triggered.connect(
                                lambda checked, p=path: self.open_specific_image_folder(p)
                            )

                        # Show menu at button position
                        menu.exec(
                            self.open_image_button.mapToGlobal(
                                self.open_image_button.rect().bottomLeft()
                            )
                        )
                        return

            # No duplicates or hash info - open normally
            self.open_specific_image_folder(self.current_result_path)

    def open_specific_image_folder(self, image_path):
        """Open the folder containing a specific image path."""
        try:
            import subprocess

            folder_path = os.path.dirname(image_path)

            if sys.platform == "win32":
                # Windows: open folder and select file
                subprocess.Popen(["explorer", "/select,", image_path])
            elif sys.platform == "darwin":
                # macOS
                subprocess.Popen(["open", "-R", image_path])
            else:
                # Linux/Unix
                subprocess.Popen(["xdg-open", folder_path])

            self.log_message(f"Opened folder for: {os.path.basename(image_path)}")
        except Exception as e:
            self.log_message(f"Error opening folder: {str(e)}")

    def on_result_selected(self, item):
        """Handle when a result is selected from the list."""
        if hasattr(self, "images_found") and self.images_found:
            index = self.list_widget.row(item)

            if 0 <= index < len(self.images_found):
                self.current_index = index
                self.current_result_path = self.images_found[index]  # Set the current result path
                image_path = self.images_found[index]

                # Log the selection with full path
                self.log_message(f"Selected: {image_path}")

                # Check if this image has duplicates and log them
                if hasattr(self, "image_hashes") and image_path in self.image_hashes:
                    img_hash = self.image_hashes[image_path]
                    if hasattr(self, "hash_to_paths") and img_hash in self.hash_to_paths:
                        all_paths = self.hash_to_paths[img_hash]
                        if len(all_paths) > 1:
                            # Log all duplicate paths
                            self.log_message(f"Found {len(all_paths)} instances:")
                            for path in all_paths:
                                self.log_message(f"  - {path}")

                # Display the result without duplicate logging
                self.display_current_result()

                # Navigate to the page containing this thumbnail if thumbnails are visible
                if hasattr(self, "thumbnails_visible") and self.thumbnails_visible:
                    # Calculate which page this image is on
                    page_number = index // self.thumbnails_per_page
                    if page_number != self.current_thumbnail_page:
                        self.current_thumbnail_page = page_number
                        self.update_thumbnail_display()
            else:
                self.log_message(f"Invalid index {index} for results list")
        else:
            self.log_message("No search results available")

    def display_current_result(self):
        """Display the currently selected result."""
        if hasattr(self, "current_index") and self.images_found:
            if 0 <= self.current_index < len(self.images_found):
                result_path = self.images_found[self.current_index]
                self.current_result_path = result_path

                # Update image viewer
                try:
                    self.photo_viewer.set_image(result_path)

                    # Check for duplicates
                    duplicate_info = ""
                    if hasattr(self, "image_hashes") and result_path in self.image_hashes:
                        img_hash = self.image_hashes[result_path]
                        if hasattr(self, "hash_to_paths") and img_hash in self.hash_to_paths:
                            all_paths = self.hash_to_paths[img_hash]
                            if len(all_paths) > 1:
                                # This image has duplicates
                                duplicate_count = len(all_paths) - 1
                                duplicate_info = f" | {duplicate_count} duplicate{'s' if duplicate_count > 1 else ''} found"

                                # Don't log duplicate paths here - it's already logged in the click handlers

                    # Update status with duplicate info
                    self.label_current.setText(
                        f"Current: {self.current_index + 1}/{len(self.images_found)}{duplicate_info}"
                    )

                    # Enable navigation buttons
                    self.previous_button.setEnabled(self.current_index > 0)
                    self.next_button.setEnabled(self.current_index < len(self.images_found) - 1)
                    self.open_image_button.setEnabled(True)
                except Exception as e:
                    self.log_message(f"Error displaying result: {str(e)}")

    def set_image(self, path: str):
        """Set the image to the photo viewer (compatibility method for SearchManager)."""
        if path and os.path.isfile(path):
            self._current_image_path = path
            self.photo_viewer.set_image(path)
        else:
            self.append_colored_text("Image file not found", QtGui.QColor("red"))
            self.photo_viewer.clear_image()

    @pyqtSlot()
    def clear_result_filters(self):
        """Clear any applied result filters (compatibility method for Worker)."""
        # Placeholder for filter clearing functionality

    @pyqtSlot(str, list, int, str)
    def add_to_search_history(self, file_path: str, results: list, search_range: int, status: str):
        """Add a search to history (compatibility method for Worker)."""
        if hasattr(self, "history_manager"):
            # Add to history if history manager is available
            pass

    def toggle_search_image(self):
        """Toggle the visibility of the search image panel."""
        self.search_image_visible = not self.search_image_visible
        self.left_panel.setVisible(self.search_image_visible)

        # Update button text
        if self.search_image_visible:
            self.toggle_search_image_button.setText("Hide Search Image")
        else:
            self.toggle_search_image_button.setText("Show Search Image")

        # Update layout stretch factors
        self.update_layout_stretch()

    def toggle_file_list(self):
        """Toggle the visibility of the file list panel."""
        self.file_list_visible = not self.file_list_visible
        self.right_panel.setVisible(self.file_list_visible)

        # Update button text
        if self.file_list_visible:
            self.toggle_file_list_button.setText("Hide File List")
        else:
            self.toggle_file_list_button.setText("Show File List")

        # Update layout stretch factors
        self.update_layout_stretch()

    def update_layout_stretch(self):
        """Update the layout stretch factors based on visible panels."""
        # Remove all widgets first
        while self.content_layout.count():
            self.content_layout.takeAt(0)

        # Calculate new stretch factors
        if self.search_image_visible and self.file_list_visible:
            # All visible: 2:2:1 ratio
            self.content_layout.addWidget(self.left_panel, 2)
            self.content_layout.addWidget(self.middle_panel, 2)
            self.content_layout.addWidget(self.right_panel, 1)
        elif self.search_image_visible and not self.file_list_visible:
            # Search image + result: 2:3 ratio
            self.content_layout.addWidget(self.left_panel, 2)
            self.content_layout.addWidget(self.middle_panel, 3)
        elif not self.search_image_visible and self.file_list_visible:
            # Result + file list: 4:1 ratio
            self.content_layout.addWidget(self.middle_panel, 4)
            self.content_layout.addWidget(self.right_panel, 1)
        else:
            # Only result visible: full width
            self.content_layout.addWidget(self.middle_panel, 1)

    def toggle_thumbnails(self):
        """Toggle the visibility of the thumbnails container."""
        self.thumbnails_visible = not self.thumbnails_visible

        # Update button text
        if self.thumbnails_visible:
            self.toggle_thumbnails_button.setText("Hide Thumbnails")
            # Use show() instead of setVisible() for better reliability
            self.thumbnails_container.show()
            # Force the container to update its geometry
            self.thumbnails_container.updateGeometry()
            # Process events to ensure proper layout
            QApplication.processEvents()
            # Only populate if we have images to show
            if hasattr(self, "images_found") and self.images_found:
                # Use a small delay to ensure proper layout calculation
                QTimer.singleShot(100, self.update_thumbnail_display)
            else:
                self.log_message("No search results to display in thumbnails")
        else:
            self.toggle_thumbnails_button.setText("Show Thumbnails")
            self.thumbnails_container.hide()

    def toggle_filters(self):
        """Toggle the visibility of the filters container."""
        self.filters_visible = not self.filters_visible

        if self.filters_visible:
            self.toggle_filters_button.setText("Hide Filters")
            self.filters_container.setVisible(True)
            self.filters_container.setChecked(True)
        else:
            self.toggle_filters_button.setText("Show Filters")
            self.filters_container.setVisible(False)
            self.filters_container.setChecked(False)

    def apply_filters(self):
        """Apply filters to the current search results."""
        if not self.images_found:
            self.log_message("No results to filter")
            return

        # Store original results if not already filtered
        if not self.is_filtered:
            self.original_results = self.images_found.copy()

        # Start with all original results
        filtered = self.original_results.copy()
        initial_count = len(filtered)

        # Apply file name filter with regex
        if self.filter_name_check.isChecked() and self.filter_name_input.text():
            import re

            try:
                pattern = re.compile(self.filter_name_input.text())
                name_filtered = []
                for img in filtered:
                    basename = os.path.basename(img)
                    if pattern.search(basename):
                        name_filtered.append(img)
                filtered = name_filtered
                self.log_message(
                    f"Name filter applied (regex: {self.filter_name_input.text()}): {len(filtered)} images match"
                )
            except re.error as e:
                self.log_message(f"Invalid regex pattern: {e}")
                # Skip this filter if regex is invalid

        # Apply file size filter
        if self.filter_size_check.isChecked():
            min_size_mb = self.filter_size_min.value()
            max_size_mb = self.filter_size_max.value()
            size_filtered = []
            for img in filtered:
                try:
                    size_mb = os.path.getsize(img) / (1024 * 1024)
                    if min_size_mb <= size_mb <= max_size_mb:
                        size_filtered.append(img)
                except OSError:
                    pass  # Skip inaccessible files
            filtered = size_filtered
            self.log_message(
                f"Size filter applied: {len(filtered)} images in range {min_size_mb:.1f}-{max_size_mb:.1f} MB"
            )

        # Apply dimensions filter
        if self.filter_dim_check.isChecked():
            min_width = self.filter_width_min.value()
            min_height = self.filter_height_min.value()
            dim_filtered = []
            for img in filtered:
                try:
                    from PIL import Image

                    with Image.open(img) as image:
                        width, height = image.size
                        if width >= min_width and height >= min_height:
                            dim_filtered.append(img)
                except:
                    pass  # Skip files that can't be opened
            filtered = dim_filtered
            self.log_message(
                f"Dimension filter applied: {len(filtered)} images >= {min_width}x{min_height}px"
            )

        # Update the display with filtered results
        self.is_filtered = True
        self.images_found = filtered

        # Update list widget
        self.list_widget.clear()

        # Add filtered results to list with duplicate indicators
        for i, image_path in enumerate(self.images_found):
            file_name = os.path.basename(image_path)
            list_text = f"{i+1}. {file_name}"

            # Check if this image has duplicates
            if hasattr(self, "image_hashes") and image_path in self.image_hashes:
                img_hash = self.image_hashes[image_path]
                if hasattr(self, "hash_to_paths") and img_hash in self.hash_to_paths:
                    dup_count = len(self.hash_to_paths[img_hash])
                    if dup_count > 1:
                        list_text += f" ({dup_count} copies)"

            self.list_widget.addItem(list_text)

        # Update displays
        if self.images_found:
            self.current_index = 0
            self.display_current_result()
            self.label_result.setText(
                f"Results: {len(self.images_found)} (filtered from {initial_count})"
            )

            # Update thumbnails if visible
            if self.thumbnails_visible:
                self.update_thumbnail_display()
        else:
            self.photo_viewer.clear_image()
            self.label_result.setText(f"Results: 0 (filtered from {initial_count})")
            self.label_current.setText("Current: 0/0")
            self.previous_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.open_image_button.setEnabled(False)

        self.log_message(
            f"Filters applied: {len(self.images_found)} of {initial_count} results shown"
        )

    def clear_filters(self):
        """Clear all filters and restore original results."""
        if not self.is_filtered:
            self.log_message("No filters to clear")
            return

        # Clear filter checkboxes
        self.filter_name_check.setChecked(False)
        self.filter_size_check.setChecked(False)
        self.filter_dim_check.setChecked(False)

        # Clear filter values
        self.filter_name_input.clear()
        self.filter_size_min.setValue(0.0)
        self.filter_size_max.setValue(100.0)
        self.filter_width_min.setValue(0)
        self.filter_height_min.setValue(0)

        # Restore original results
        self.is_filtered = False
        self.images_found = self.original_results.copy()

        # Update list widget
        self.list_widget.clear()
        for i, image_path in enumerate(self.images_found):
            file_name = os.path.basename(image_path)
            list_text = f"{i+1}. {file_name}"

            # Check if this image has duplicates
            if hasattr(self, "image_hashes") and image_path in self.image_hashes:
                img_hash = self.image_hashes[image_path]
                if hasattr(self, "hash_to_paths") and img_hash in self.hash_to_paths:
                    dup_count = len(self.hash_to_paths[img_hash])
                    if dup_count > 1:
                        list_text += f" ({dup_count} copies)"

            self.list_widget.addItem(list_text)

        # Reset display
        if self.images_found:
            self.current_index = 0
            self.display_current_result()
            self.label_result.setText(f"Results: {len(self.images_found)}")

            # Update thumbnails if visible
            if self.thumbnails_visible:
                self.update_thumbnail_display()

        self.log_message(f"Filters cleared. Showing all {len(self.images_found)} results")

    @pyqtSlot()
    def populate_thumbnail_list(self):
        """Populate thumbnail list with search results."""
        # Populate list widget if empty (new search results)
        if self.list_widget.count() == 0 and hasattr(self, "images_found") and self.images_found:
            # Add list items for ALL results
            for i, image_path in enumerate(self.images_found):
                # Add to list widget with duplicate indicator
                file_name = os.path.basename(image_path)
                list_text = f"{i+1}. {file_name}"

                # Check if this image has duplicates
                if hasattr(self, "image_hashes") and image_path in self.image_hashes:
                    img_hash = self.image_hashes[image_path]
                    if hasattr(self, "hash_to_paths") and img_hash in self.hash_to_paths:
                        dup_count = len(self.hash_to_paths[img_hash])
                        if dup_count > 1:
                            list_text += f" ({dup_count} copies)"

                self.list_widget.addItem(list_text)

        # Update thumbnail display
        if hasattr(self, "images_found") and self.images_found:
            self.update_thumbnail_display()

            # The thumbnail display is updated by update_thumbnail_display()
            # No need to duplicate the logic here

            # Enable the toggle button and navigation if we have results
            self.toggle_thumbnails_button.setEnabled(True)
            if len(self.images_found) > 0:
                self.previous_button.setEnabled(False)  # Start at first result
                self.next_button.setEnabled(len(self.images_found) > 1)
                self.open_image_button.setEnabled(True)

                # Update labels
                self.label_result.setText(f"Results: {len(self.images_found)}")
                self.label_current.setText(f"Current: 1/{len(self.images_found)}")

                # Display first result
                self.current_index = 0
                self.display_current_result()

                # Save to history
                if hasattr(self, "current_image_path") and self.current_image_path:
                    self.history_manager.add_to_search_history(
                        self.current_image_path,
                        self.images_found,
                        self.search_range.value() if hasattr(self, "search_range") else 6,
                        "Success",
                    )

    def on_thumbnail_clicked(self, image_path: str):
        """Handle thumbnail click - display the clicked image."""
        self.log_message(f"Clicked: {image_path}")

        # Always log full path and duplicates if any
        if hasattr(self, "image_hashes") and image_path in self.image_hashes:
            img_hash = self.image_hashes[image_path]
            if hasattr(self, "hash_to_paths") and img_hash in self.hash_to_paths:
                all_paths = self.hash_to_paths[img_hash]
                if len(all_paths) > 1:
                    # Log all duplicate paths
                    self.log_message(f"Found {len(all_paths)} instances:")
                    for path in all_paths:
                        self.log_message(f"  - {path}")

        try:
            # Find the index of this image in the results
            if hasattr(self, "images_found") and image_path in self.images_found:
                self.current_index = self.images_found.index(image_path)
                self.current_result_path = image_path  # Set the current result path
                # Don't log duplicates in display_current_result since we already logged them
                self.display_current_result()

                # Also update the list widget selection
                self.list_widget.setCurrentRow(self.current_index)
            else:
                self.log_message(f"Image path not found in results: {image_path}")
        except Exception as e:
            self.log_message(f"Error handling thumbnail click: {str(e)}")

    def load_ui_settings(self):
        """Load UI settings from saved configuration."""
        # Load index directory if saved
        if hasattr(self, "index_directory") and hasattr(self.settings, "settings"):
            saved_dir = self.settings.settings.value("index_directory", os.path.expanduser("~"))
            self.index_directory.setText(saved_dir)

        # Load cleanup preference
        if hasattr(self, "cleanup_non_existing_check") and hasattr(self.settings, "settings"):
            cleanup_enabled = self.settings.settings.value("cleanup_non_existing", False, type=bool)
            self.cleanup_non_existing_check.setChecked(cleanup_enabled)

        # No longer need to load logging settings - always log full paths

    def on_duplicate_indicator_clicked(self, image_path: str):
        """Handle duplicate indicator click - show all duplicate paths."""
        self.log_message(f"Duplicate indicator clicked for: {os.path.basename(image_path)}")

        if hasattr(self, "image_hashes") and image_path in self.image_hashes:
            img_hash = self.image_hashes[image_path]
            if hasattr(self, "hash_to_paths") and img_hash in self.hash_to_paths:
                all_paths = self.hash_to_paths[img_hash]

                # Always log all duplicate paths
                self.log_message(
                    f"All {len(all_paths)} instances of {os.path.basename(image_path)}:"
                )
                for path in all_paths:
                    self.log_message(f"  - {path}")

                # Create a menu to show all duplicate paths
                menu = QMenu(self)

                # Apply theme-aware styling
                if hasattr(self, "theme_manager") and self.theme_manager.is_dark_theme():
                    menu.setStyleSheet(
                        """
                        QMenu {
                            background-color: #3c3c3c;
                            color: #ffffff;
                            border: 1px solid #555555;
                            padding: 5px;
                        }
                        QMenu::item {
                            padding: 5px 20px;
                            color: #ffffff;
                        }
                        QMenu::item:selected {
                            background-color: #0d7377;
                            color: white;
                        }
                        QMenu::item:disabled {
                            color: #888888;
                        }
                    """
                    )
                else:
                    menu.setStyleSheet(
                        """
                        QMenu {
                            background-color: white;
                            color: #000000;
                            border: 1px solid #ccc;
                            padding: 5px;
                        }
                        QMenu::item {
                            padding: 5px 20px;
                            color: #000000;
                        }
                        QMenu::item:selected {
                            background-color: #0d7377;
                            color: white;
                        }
                        QMenu::item:disabled {
                            color: #888888;
                        }
                    """
                    )

                # Add header
                header_action = menu.addAction(f"All {len(all_paths)} instances of this image:")
                header_action.setEnabled(False)
                font = header_action.font()
                font.setBold(True)
                header_action.setFont(font)
                menu.addSeparator()

                # Add each path
                for i, dup_path in enumerate(all_paths):
                    action = menu.addAction(f"{i+1}. {os.path.basename(dup_path)}")
                    action.setToolTip(dup_path)

                    if dup_path == image_path:
                        # Mark current image
                        font = action.font()
                        font.setBold(True)
                        action.setFont(font)
                        action.setText(f"{i+1}. {os.path.basename(dup_path)} (current)")

                    # Connect to display the duplicate
                    action.triggered.connect(
                        lambda checked, p=dup_path: self.display_duplicate_image(p)
                    )

                menu.addSeparator()

                # Add action to copy all paths
                copy_action = menu.addAction("Copy all paths to clipboard")
                copy_action.triggered.connect(lambda: self.copy_duplicate_paths(all_paths))

                # Show menu at cursor position
                menu.exec(QtGui.QCursor.pos())

    def display_duplicate_image(self, image_path):
        """Display a specific duplicate image."""
        try:
            # Find index of this image in results
            if image_path in self.images_found:
                self.current_index = self.images_found.index(image_path)
                self.current_result_path = image_path
                self.display_current_result()
                self.list_widget.setCurrentRow(self.current_index)
                self.log_message(f"Displayed duplicate: {os.path.basename(image_path)}")
            else:
                # If not in results, just display it
                self.photo_viewer.set_image(image_path)
                self.log_message(
                    f"Displayed image (not in results): {os.path.basename(image_path)}"
                )
        except Exception as e:
            self.log_message(f"Error displaying duplicate image: {str(e)}")

    def copy_duplicate_paths(self, paths):
        """Copy all duplicate paths to clipboard."""
        try:
            clipboard = QApplication.clipboard()
            paths_text = "\n".join(paths)
            clipboard.setText(paths_text)
            self.log_message(f"Copied {len(paths)} paths to clipboard")
        except Exception as e:
            self.log_message(f"Error copying paths to clipboard: {str(e)}")

    def init_database_async(self):
        """Initialize the database manager asynchronously."""

        class DatabaseInitThread(QThread):
            finished_init = pyqtSignal(object)  # Pass the database manager
            error_occurred = pyqtSignal(str)
            progress_update = pyqtSignal(str)

            def run(self):
                try:
                    # Sleep briefly to allow GUI to render
                    self.msleep(50)
                    self.progress_update.emit("Loading database...")
                    # Initialize database manager IN THE THREAD
                    from src.managers.database_manager import DatabaseManager

                    db_manager = DatabaseManager()
                    self.finished_init.emit(db_manager)
                except Exception as e:
                    self.error_occurred.emit(str(e))

        # Show loading status
        self.log_message("Initializing database in background...")
        self.update_status_bar("Loading database...")

        # Create and start initialization thread
        self.db_init_thread = DatabaseInitThread()
        self.db_init_thread.finished_init.connect(self.on_database_initialized)
        self.db_init_thread.error_occurred.connect(self.on_database_error)
        self.db_init_thread.progress_update.connect(lambda msg: self.log_message(msg))
        self.db_init_thread.start()

    def on_database_initialized(self, db_manager):
        """Called when database is initialized."""
        # Store the database manager created in the thread
        self.database_manager = db_manager

        # Update total images count
        self.update_total_images_count()

        # Update database statistics if migration UI exists
        if hasattr(self, "db_stats_label"):
            self.update_db_statistics()

        # Update migration status
        if hasattr(self, "migration_status_value"):
            if self.database_manager.is_migrated():
                self.migration_status_value.setText("✓ Using SQLite (optimized)")
                self.migration_status_value.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.migration_status_value.setText("Using Pickle (legacy)")
                self.migration_status_value.setStyleSheet("color: orange; font-weight: bold;")

        # Update migration button
        if hasattr(self, "migrate_button"):
            if self.database_manager.is_migrated():
                self.migrate_button.setEnabled(False)
                self.migrate_button.setText("Already Migrated")
                self.migrate_button.setStyleSheet("QPushButton { color: gray; }")
            else:
                self.migrate_button.setEnabled(True)

        # Enable database-dependent controls
        self.set_database_dependent_controls(True)

        # Hide loading indicator
        if hasattr(self, "db_loading_label"):
            self.db_loading_label.setText("✓ Database ready")
            self.db_loading_label.setStyleSheet("color: green; font-weight: bold;")
            # Hide it after a moment
            QTimer.singleShot(2000, lambda: self.db_loading_label.setVisible(False))

        # Clean up thread
        if hasattr(self, "db_init_thread"):
            self.db_init_thread.deleteLater()
            self.db_init_thread = None

        self.log_message("Database initialized successfully")
        self.update_status_bar("Ready")

    def on_database_error(self, error_msg):
        """Called when database initialization fails."""
        self.log_message(f"Database initialization error: {error_msg}")
        # Create a fallback database manager anyway
        self.database_manager = DatabaseManager()

        # Update loading indicator
        if hasattr(self, "db_loading_label"):
            self.db_loading_label.setText("⚠ Database error")
            self.db_loading_label.setStyleSheet("color: red; font-weight: bold;")

        # Enable controls anyway (with fallback database)
        self.set_database_dependent_controls(True)

        # Clean up thread
        if hasattr(self, "db_init_thread"):
            self.db_init_thread.deleteLater()
            self.db_init_thread = None

        self.update_status_bar("Ready (with errors)")

    def init_managers_async(self):
        """Initialize managers after UI is shown."""
        # Use QTimer to defer the actual initialization
        # This allows the UI to become fully responsive first
        QTimer.singleShot(0, self._do_manager_init)

    def _do_manager_init(self):
        """Actually initialize the managers."""
        try:
            # Initialize managers (these should be relatively fast)
            self.search_manager = SearchManager(self)
            self.index_manager = IndexManager(self)
            self.history_manager = HistoryManager(self)
            self.metadata_manager = MetadataManager(self)
            self.filter_manager = FilterManager(self)
            self.theme_manager = ThemeManager(self.settings.settings, self)

            # File handler already created in __init__, just connect signals
            self.file_handler.file_ready.connect(self.on_file_ready)
            self.file_handler.error_occurred.connect(self.append_colored_text)
            self.file_handler.status_update.connect(self.update_status_bar)

            # Connect UI signals
            self.connect_signals()

            # Load saved settings
            self.load_ui_settings()

            # Defer history loading to avoid file I/O in main thread
            QTimer.singleShot(100, self._load_history_async)

            # Initialize database asynchronously
            self.init_database_async()
        except Exception as e:
            self.log_message(f"Error initializing managers: {str(e)}")

    def _load_history_async(self):
        """Load search history asynchronously."""
        try:
            self.history_manager.load_search_history()
        except Exception as e:
            self.log_message(f"Error loading search history: {str(e)}")

    def set_database_dependent_controls(self, enabled: bool):
        """Enable or disable controls that depend on the database."""
        # Search button - only enable if image is loaded
        if hasattr(self, "search_button"):
            if enabled and hasattr(self, "current_image_path") and self.current_image_path:
                self.search_button.setEnabled(True)
                self.search_button.setToolTip("")
            else:
                self.search_button.setEnabled(False)
                if not enabled:
                    self.search_button.setToolTip("Database is loading...")
                else:
                    self.search_button.setToolTip("Please select an image first")

        # Indexing button
        if hasattr(self, "index_button"):
            self.index_button.setEnabled(enabled)
            self.index_button.setToolTip("" if enabled else "Database is loading...")

        # Migration button - only if not already migrated
        if hasattr(self, "migrate_button") and self.database_manager:
            if not self.database_manager.is_migrated():
                self.migrate_button.setEnabled(enabled)

        # Duplicates tab refresh
        if hasattr(self, "duplicates_tab"):
            try:
                self.duplicates_tab.refresh_button.setEnabled(enabled)
                self.duplicates_tab.refresh_button.setToolTip(
                    "" if enabled else "Database is loading..."
                )
            except:
                pass

    def update_total_images_count(self):
        """Update the total images count from the database."""
        try:
            # Check if database manager is initialized
            if not self.database_manager:
                self.label_total_images.setText("Total Images in Database: Loading...")
                return

            # Check if we have VP-tree and hash files
            (
                self.vp_tree_dir.text()
                if hasattr(self, "vp_tree_dir")
                else os.path.join(self.dir_path, "VPtree.pickle")
            )
            hash_path = (
                self.hash_dir.text()
                if hasattr(self, "hash_dir")
                else os.path.join(self.dir_path, "Hashing.pickle")
            )

            # Use database manager for SQLite or fallback to pickle
            if self.database_manager.is_migrated():
                # Get statistics from SQLite
                stats = self.database_manager.get_statistics()
                count = stats.get("unique_images", 0)
                total_paths = stats.get("total_paths", 0)
                self.label_total_images.setText(
                    f"Total Images in Database: {count} (Unique), {total_paths} (Total Paths)"
                )
            elif os.path.exists(hash_path):
                # Load the hash file to count images
                import pickle

                with open(hash_path, "rb") as f:
                    hash_data = pickle.load(f)
                    if isinstance(hash_data, dict):
                        # Count unique images (not duplicate paths)
                        unique_images = set()
                        total_paths = 0
                        for hash_value, paths in hash_data.items():
                            if isinstance(paths, list):
                                unique_images.add(hash_value)
                                total_paths += len(paths)
                            else:
                                unique_images.add(hash_value)
                                total_paths += 1

                        count = len(unique_images)
                        self.label_total_images.setText(
                            f"Total Images in Database: {count} (Unique), {total_paths} (Total Paths)"
                        )
                    else:
                        # Old format - count entries
                        count = len(hash_data) if hash_data else 0
                        self.label_total_images.setText(f"Total Images in Database: {count}")
            else:
                self.label_total_images.setText("Total Images in Database: 0 (No database found)")
        except Exception as e:
            self.label_total_images.setText("Total Images in Database: Error reading database")
            self.log_message(f"Error updating total images count: {str(e)}")

    def show_list_context_menu(self, position):
        """Show context menu for list items."""
        item = self.list_widget.itemAt(position)
        if item:
            index = self.list_widget.row(item)
            if 0 <= index < len(self.images_found) and hasattr(self, "image_hashes"):
                image_path = self.images_found[index]

                # Check if this image has duplicates
                if image_path in self.image_hashes:
                    img_hash = self.image_hashes[image_path]
                    if hasattr(self, "hash_to_paths") and img_hash in self.hash_to_paths:
                        all_paths = self.hash_to_paths[img_hash]
                        if len(all_paths) > 1:
                            # Create context menu
                            menu = QMenu(self)

                            # Add header
                            header_action = menu.addAction(
                                f"Duplicate Images ({len(all_paths)} total):"
                            )
                            header_action.setEnabled(False)
                            menu.addSeparator()

                            # Add each duplicate path
                            for dup_path in all_paths:
                                action = menu.addAction(os.path.basename(dup_path))
                                action.setToolTip(dup_path)
                                if dup_path == image_path:
                                    # Mark current image
                                    font = action.font()
                                    font.setBold(True)
                                    action.setFont(font)

                                # Connect to open the duplicate
                                action.triggered.connect(
                                    lambda checked, p=dup_path: self.open_duplicate_image(p)
                                )

                            # Show menu
                            menu.exec(self.list_widget.mapToGlobal(position))

    def open_duplicate_image(self, image_path):
        """Open a specific duplicate image."""
        try:
            # Find index of this image in results
            if image_path in self.images_found:
                self.current_index = self.images_found.index(image_path)
                self.display_current_result()
                self.list_widget.setCurrentRow(self.current_index)
            else:
                # If not in results, try to open it directly
                os.startfile(image_path)
        except Exception as e:
            self.log_message(f"Error opening duplicate image: {str(e)}")

    def update_pagination_controls(self):
        """Update pagination button states and label."""
        if hasattr(self, "prev_page_button"):
            self.prev_page_button.setEnabled(self.current_thumbnail_page > 0)
            self.next_page_button.setEnabled(
                self.current_thumbnail_page < self.total_thumbnail_pages - 1
            )

            # Calculate unique images count for pagination display
            unique_count = 0
            if hasattr(self, "image_hashes") and hasattr(self, "hash_to_paths"):
                seen_hashes = set()
                for image_path in self.images_found:
                    if image_path in self.image_hashes:
                        img_hash = self.image_hashes[image_path]
                        if img_hash not in seen_hashes:
                            seen_hashes.add(img_hash)
                            unique_count += 1
                    else:
                        unique_count += 1
            else:
                unique_count = len(self.images_found)

            start_idx = self.current_thumbnail_page * self.thumbnails_per_page + 1
            end_idx = min(
                (self.current_thumbnail_page + 1) * self.thumbnails_per_page, unique_count
            )
            self.page_label.setText(
                f"Page {self.current_thumbnail_page + 1} of {self.total_thumbnail_pages} (Images {start_idx}-{end_idx})"
            )

    def prev_thumbnail_page(self):
        """Go to previous thumbnail page."""
        if self.current_thumbnail_page > 0:
            self.current_thumbnail_page -= 1
            self.update_thumbnail_display()

    def next_thumbnail_page(self):
        """Go to next thumbnail page."""
        if self.current_thumbnail_page < self.total_thumbnail_pages - 1:
            self.current_thumbnail_page += 1
            self.update_thumbnail_display()

    def clear_search_results(self):
        """Clear all search results and reset UI."""
        self.list_widget.clear()
        self.images_found.clear()

        # Clear hash data
        if hasattr(self, "image_hashes"):
            self.image_hashes.clear()
        if hasattr(self, "hash_to_paths"):
            self.hash_to_paths.clear()

        # Clear thumbnails
        if hasattr(self, "thumbnails_layout"):
            while self.thumbnails_layout.count():
                item = self.thumbnails_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

        # Hide thumbnails container
        if hasattr(self, "thumbnails_container"):
            self.thumbnails_container.hide()
            self.thumbnails_visible = False

        # Reset current result path
        self.current_result_path = None

        # Disable buttons
        self.toggle_thumbnails_button.setEnabled(False)
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.open_image_button.setEnabled(False)

        # Reset labels
        self.label_result.setText("Results: 0")
        self.label_current.setText("Current: 0/0")

        # Clear viewers
        self.photo_viewer.clear_image()

    def perform_migration(self):
        """Perform the database migration from pickle to SQLite."""
        # Check if database is initialized
        if not self.database_manager:
            self.log_message("Database is still loading, please wait...")
            return

        import subprocess

        from PyQt6.QtCore import QThread, pyqtSignal
        from PyQt6.QtWidgets import QMessageBox

        class MigrationThread(QThread):
            """Thread to run migration without blocking UI."""

            output_ready = pyqtSignal(str)
            error_occurred = pyqtSignal(str)
            finished_migration = pyqtSignal(bool, str)

            def run(self):
                """Run the migration process."""
                try:
                    # Run without timeout - let it complete naturally
                    process = subprocess.Popen(
                        [sys.executable, "migrate_to_sqlite.py"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        bufsize=1,
                    )

                    # Read output line by line for real-time feedback
                    for line in iter(process.stdout.readline, ""):
                        if line:
                            self.output_ready.emit(line.strip())

                    # Wait for process to complete
                    process.wait()

                    if process.returncode == 0:
                        self.finished_migration.emit(True, "Migration completed successfully!")
                    else:
                        stderr = process.stderr.read()
                        self.finished_migration.emit(False, stderr)

                except Exception as e:
                    self.error_occurred.emit(str(e))
                    self.finished_migration.emit(False, str(e))

        reply = QMessageBox.question(
            self,
            "Confirm Migration",
            "This will migrate your hash database from pickle to SQLite format.\n\n"
            "Benefits:\n"
            "• 50-70% faster cleanup operations\n"
            "• 40-60% less memory usage\n"
            "• Better duplicate handling\n\n"
            "The migration will run in the background.\n"
            "Progress will be shown in the log.\n"
            "A backup will be created automatically.\n\n"
            "Do you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.log_message("Starting database migration...")
            self.log_message("This may take several minutes for large databases.")
            self.log_message("The application will remain responsive.")
            self.log_message("-" * 60)

            self.migrate_button.setEnabled(False)
            self.migrate_button.setText("Migration in Progress...")

            # Create and start migration thread
            self.migration_thread = MigrationThread()

            # Connect signals
            self.migration_thread.output_ready.connect(lambda msg: self.log_message(f"  {msg}"))
            self.migration_thread.error_occurred.connect(
                lambda err: self.log_message(f"ERROR: {err}")
            )
            self.migration_thread.finished_migration.connect(self.on_migration_finished)

            # Start the migration
            self.migration_thread.start()

    def on_migration_finished(self, success, message):
        """Handle migration completion."""
        from PyQt6.QtWidgets import QMessageBox

        if success:
            self.log_message("-" * 60)
            self.log_message("[SUCCESS] Migration completed successfully!")

            # Update UI (re-initialize database manager)
            if self.database_manager:
                self.database_manager = DatabaseManager()
            self.migration_status_value.setText("✓ Using SQLite (optimized)")
            self.migration_status_value.setStyleSheet("color: green; font-weight: bold;")
            self.migrate_button.setText("Already Migrated")
            self.migrate_button.setStyleSheet("QPushButton { color: gray; }")

            # Update statistics
            self.update_db_statistics()

            QMessageBox.information(
                self,
                "Migration Complete",
                "Database migration completed successfully!\n\n"
                "The application is now using SQLite for improved performance.",
            )
        else:
            self.log_message("-" * 60)
            self.log_message(f"[ERROR] Migration failed: {message}")

            QMessageBox.warning(
                self,
                "Migration Failed",
                f"Migration failed. Please check the log for details.\n\n{message[:200]}",
            )

            self.migrate_button.setEnabled(True)
            self.migrate_button.setText("Migrate to SQLite Database")

        # Clean up thread
        if hasattr(self, "migration_thread"):
            self.migration_thread.deleteLater()

    def update_db_statistics(self):
        """Update database statistics display."""
        try:
            if not self.database_manager:
                self.db_stats_label.setText("Database loading...")
                return

            stats = self.database_manager.get_statistics()
            stats_text = (
                f"Database Statistics:\n"
                f"  • Unique images: {stats['unique_images']:,}\n"
                f"  • Total paths: {stats['total_paths']:,}\n"
                f"  • Duplicates: {stats['duplicates']:,}"
            )
            self.db_stats_label.setText(stats_text)
        except Exception as e:
            self.db_stats_label.setText(f"Unable to load statistics: {str(e)}")

    def update_thumbnail_display(self):
        """Update only the thumbnail display without touching the list widget."""
        if not hasattr(self, "images_found") or not self.images_found:
            self.log_message("No images found to display in thumbnails")
            return

        # Filter out duplicates - only keep one representative per hash
        unique_images = []
        seen_hashes = set()

        for image_path in self.images_found:
            if hasattr(self, "image_hashes") and image_path in self.image_hashes:
                img_hash = self.image_hashes[image_path]
                if img_hash not in seen_hashes:
                    seen_hashes.add(img_hash)
                    unique_images.append(image_path)
            else:
                # If no hash info, include the image
                unique_images.append(image_path)

        total_unique_images = len(unique_images)

        self.log_message(
            f"Updating thumbnail display: {total_unique_images} unique images from {len(self.images_found)} total"
        )

        # Ensure the container is visible
        if hasattr(self, "thumbnails_container") and self.thumbnails_visible:
            self.thumbnails_container.show()

        # Calculate columns
        self.calculate_thumbnail_columns()

        # Clear any pending thumbnail loads
        self.thumbnail_loader.clear()

        # Clear existing thumbnails instantly
        while self.thumbnails_layout.count():
            item = self.thumbnails_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Calculate pages based on unique images
        self.total_thumbnail_pages = (
            total_unique_images + self.thumbnails_per_page - 1
        ) // self.thumbnails_per_page
        start_idx = self.current_thumbnail_page * self.thumbnails_per_page
        end_idx = min(start_idx + self.thumbnails_per_page, total_unique_images)

        # Update pagination controls immediately
        self.update_pagination_controls()

        self.log_message(
            f"Displaying thumbnails {start_idx + 1} to {end_idx} of {total_unique_images}, page {self.current_thumbnail_page + 1}"
        )

        # Create all thumbnail widgets as placeholders first
        thumbnail_widgets = []

        row = 0
        col = 0
        for i in range(start_idx, end_idx):
            # Extra bounds check to prevent IndexError
            if i >= len(unique_images):
                self.log_message(
                    f"Warning: Tried to access index {i} but only {len(unique_images)} unique images available"
                )
                break

            image_path = unique_images[i]
            try:
                # Check duplicate count for thumbnail
                dup_count = 0
                if hasattr(self, "image_hashes") and image_path in self.image_hashes:
                    img_hash = self.image_hashes[image_path]
                    if hasattr(self, "hash_to_paths") and img_hash in self.hash_to_paths:
                        dup_count = len(self.hash_to_paths[img_hash]) - 1

                # Create thumbnail widget (will show loading placeholder)
                thumbnail = ThumbnailWidget(image_path, parent=self, duplicate_count=dup_count)
                # Use lambda with default argument to capture current image_path
                thumbnail.clicked.connect(lambda path=image_path: self.on_thumbnail_clicked(path))
                thumbnail.duplicate_clicked.connect(
                    lambda path=image_path: self.on_duplicate_indicator_clicked(path)
                )

                # Set duplicate paths if available
                if (
                    dup_count > 0
                    and hasattr(self, "hash_to_paths")
                    and img_hash in self.hash_to_paths
                ):
                    thumbnail.set_duplicate_paths(self.hash_to_paths[img_hash])

                # Add to layout immediately
                self.thumbnails_layout.addWidget(thumbnail, row, col)

                # Add to list for async loading
                thumbnail_widgets.append(thumbnail)

                col += 1
                if col >= self.current_thumbnail_columns:  # Dynamic columns per row
                    col = 0
                    row += 1
            except Exception as e:
                self.log_message(f"Error creating thumbnail for {image_path}: {str(e)}")

        # Update scroll area and ensure visibility
        self.thumbnails_widget.adjustSize()
        self.thumbnails_scroll.show()
        # Force a repaint
        self.thumbnails_scroll.update()

        # Start loading thumbnails asynchronously
        if thumbnail_widgets:
            self.thumbnail_loader.add_thumbnails(thumbnail_widgets)


def main():
    """Main application entry point."""
    app = QApplication(sys.argv)

    # Preload the logo first (fast)
    from src.utils.utils import get_app_logo

    logo_path = get_app_logo()
    logo_pixmap = QtGui.QPixmap(logo_path)

    # Create and show splash screen immediately
    splash = QSplashScreen(logo_pixmap)
    splash.setWindowFlags(
        QtCore.Qt.WindowType.FramelessWindowHint
        | QtCore.Qt.WindowType.WindowStaysOnTopHint
        | QtCore.Qt.WindowType.SplashScreen
    )

    # Center and show splash screen first
    screen = app.primaryScreen()
    screen_geometry = screen.geometry()
    splash_size = logo_pixmap.size()
    x = (screen_geometry.width() - splash_size.width()) // 2
    y = (screen_geometry.height() - splash_size.height()) // 2
    splash.move(x, y)
    splash.show()
    splash.raise_()
    splash.activateWindow()
    app.processEvents()  # Ensure splash is visible

    # Now create main window while splash is visible
    window = MyWindow()

    # Center main window on screen
    window_geometry = window.frameGeometry()
    center_point = screen_geometry.center()
    window_geometry.moveCenter(center_point)
    window.move(window_geometry.topLeft())

    # Show main window behind splash
    window.show()
    window.lower()  # Put it behind splash initially
    app.processEvents()

    # Close splash after 1.5 seconds and bring main window to front
    def close_splash():
        splash.close()
        window.raise_()  # Bring main window to front
        window.activateWindow()  # Make it active

    QTimer.singleShot(1500, close_splash)  # 1.5 seconds

    # Start the application
    exit_code = app.exec()

    # Cleanup test file if it exists
    if window.get_test_file_ext():
        test_file_path = os.path.join(window.dir_path, f"testfile.{window.get_test_file_ext()}")
        try:
            os.remove(test_file_path)
        except FileNotFoundError:
            logging.error("File not found: %s", test_file_path, exc_info=True)
        except PermissionError:
            logging.error("Permission denied: %s", test_file_path, exc_info=True)
        except Exception as e:
            logging.error("Error deleting file: %s", test_file_path, exc_info=True)
            logging.error("Error: %s", str(e))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
