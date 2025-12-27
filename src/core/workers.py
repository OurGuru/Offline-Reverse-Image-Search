"""
Worker classes for background processing in the Offline Reverse Image Search application.

This module provides worker classes that handle background tasks such as
image searching, indexing, and HTML export operations using Qt's threading system.
"""

import logging
import os
import threading
from collections import deque
from pickle import loads as pickleloads
from typing import Any

from PIL import Image
from PyQt6 import QtCore, QtGui
from PyQt6.QtWidgets import QLabel, QPushButton

from ..utils.utils import convert_hash, dhash
from .constants import (
    DEFAULT_SEARCH_RANGE,
    DEFAULT_SIMILARITY_THRESHOLD,
    MAX_SEARCH_RANGE,
    MIN_SEARCH_RANGE,
    ErrorMessages,
)


class Worker(QtCore.QObject):
    """
    A worker object for running a reverse image search engine.

    Attributes
    ----------
    progress : QtCore.pyqtSignal
        A signal that emits an integer value indicating the progress of the search.
    finished : QtCore.pyqtSignal
        A signal that emits when the search is finished.
    current_updated : QtCore.pyqtSignal
        A signal that emits when the current image is updated.
    """

    def __init__(
        self,
        images_found: list[str],
        file_path: str,
        photo_main: Any,
        photo_viewer: Any,
        next_button: QPushButton,
        previous_button: QPushButton,
        open_image_button: QPushButton,
        label_result: QLabel,
        label_current: QLabel,
        set_image: Any,
        append_colored_text: Any,
        display_queue: deque,
        current: str,
        settings: QtCore.QSettings,
        images_lock: threading.Lock,
        queue_lock: threading.Lock,
        current_lock: threading.Lock,
        parent_window=None,
    ) -> None:
        super().__init__()
        self.images_found = images_found
        self.file_path = file_path
        self.photo_main = photo_main
        self.photo_viewer = photo_viewer
        self.next_button = next_button
        self.previous_button = previous_button
        self.open_image_button = open_image_button
        self.label_result = label_result
        self.label_current = label_current
        self.set_image = set_image
        self.append_colored_text = append_colored_text
        self.display_queue = display_queue
        self.current = current
        self.settings = settings
        self.parent_window = parent_window
        # Thread safety locks
        self.images_lock = images_lock
        self.queue_lock = queue_lock
        self.current_lock = current_lock

    # Signals for thread-safe UI updates
    progress = QtCore.pyqtSignal(int)
    finished = QtCore.pyqtSignal()
    current_updated = QtCore.pyqtSignal(str)
    status_update = QtCore.pyqtSignal(str)  # Signal for status bar updates
    main_image_update = QtCore.pyqtSignal(str)  # Signal for updating main image

    # Additional signals for all UI operations
    append_text = QtCore.pyqtSignal(str, object)  # text, color
    set_photo_main_text = QtCore.pyqtSignal(str)
    clear_photo_main = QtCore.pyqtSignal()
    clear_photo_viewer = QtCore.pyqtSignal()
    set_photo_viewer_text = QtCore.pyqtSignal(str)
    enable_buttons = QtCore.pyqtSignal(dict)  # dict of button_name: enabled
    set_label_text = QtCore.pyqtSignal(str, str)  # label_name, text
    set_image_signal = QtCore.pyqtSignal(str)  # image path
    set_window_title = QtCore.pyqtSignal(str)
    enable_parent_buttons = QtCore.pyqtSignal(dict)  # dict of button_name: enabled
    add_to_history = QtCore.pyqtSignal(str, list, int, str)  # file_path, results, range, status

    def run(self) -> None:
        """
        Run the reverse image search engine and emit the finished signal when complete.
        """
        # Use lock to safely clear images_found
        self.images_lock.lock()
        try:
            self.images_found.clear()
        finally:
            self.images_lock.unlock()

        # Clear any existing result filters if they are applied
        if (
            self.parent_window
            and hasattr(self.parent_window, "is_filtered")
            and self.parent_window.is_filtered
        ):
            # Clear the filtered state
            self.parent_window.is_filtered = False
            self.parent_window.original_results.clear()
            self.parent_window.filtered_results.clear()

            # Reset filter UI elements
            QtCore.QMetaObject.invokeMethod(
                self.parent_window,
                "clear_result_filters",
                QtCore.Qt.ConnectionType.QueuedConnection,
            )

        # Emit status update
        self.status_update.emit("Initializing search...")

        # check if the VP-Tree and Hashing files exist
        if not self.settings.value("VPTree") or not self.settings.value("Hashing"):
            self.append_text.emit(ErrorMessages.INDEX_NOT_FOUND, QtGui.QColor("red"))
            self._error_sound()
            self.set_photo_main_text.emit(ErrorMessages.ERROR_TEXT)
            return

        vptree_path = self.settings.value("VPTree")
        hashing_path = self.settings.value("Hashing")

        # Emit status update
        self.status_update.emit("Loading index files...")

        # check if the VP-Tree and Hashing files exist
        if not os.path.exists(vptree_path) or not os.path.exists(hashing_path):
            self.append_text.emit(ErrorMessages.INDEX_NOT_FOUND, QtGui.QColor("red"))
            self._error_sound()
            self.set_photo_main_text.emit(ErrorMessages.ERROR_TEXT)
            return

        # check search_range if it is a valid integer
        try:
            # Use the search_range_value from UI if passed, otherwise fall back to settings
            if hasattr(self, "search_range_value"):
                search_range = self.search_range_value
            else:
                search_range_str = str(
                    self.settings.value("search_range", str(DEFAULT_SEARCH_RANGE))
                )
                search_range = int(search_range_str)

            if search_range < MIN_SEARCH_RANGE or search_range > MAX_SEARCH_RANGE:
                raise ValueError("Search range out of bounds")
        except (ValueError, TypeError):
            self.append_text.emit(
                ErrorMessages.SEARCH_RANGE_INVALID.format(MIN_SEARCH_RANGE, MAX_SEARCH_RANGE),
                QtGui.QColor("red"),
            )
            self._error_sound()
            self.set_photo_main_text.emit(ErrorMessages.ERROR_TEXT)
            return

        try:
            # Add security warning for pickle files
            self.append_text.emit(ErrorMessages.PICKLE_SECURITY_WARNING, QtGui.QColor("orange"))

            with open(vptree_path, "rb") as vptree_file:
                vptree = pickleloads(vptree_file.read())
            with open(hashing_path, "rb") as hashing_file:
                hashes = pickleloads(hashing_file.read())
        except Exception as e:
            self.append_text.emit(
                ErrorMessages.INDEX_LOAD_FAILED.format(str(e)), QtGui.QColor("red")
            )
            self._error_sound()
            self.set_photo_main_text.emit(ErrorMessages.ERROR_TEXT)
            return

        # Validate file path first
        if not self.file_path or not os.path.isfile(self.file_path):
            error_msg = f"Invalid or empty file path: '{self.file_path}'"
            self.append_text.emit(f"[ERROR] {error_msg}", QtGui.QColor("red"))
            self._error_sound()
            self.set_photo_main_text.emit(ErrorMessages.ERROR_TEXT)
            logging.error(error_msg)
            return

        # Check file size before processing
        try:
            file_size = os.path.getsize(self.file_path)

            if file_size > self._get_max_file_size_bytes():
                size_mb = file_size / (1024 * 1024)
                self.append_text.emit(
                    ErrorMessages.SEARCH_IMAGE_TOO_LARGE.format(
                        size_mb, self._get_max_file_size_mb()
                    ),
                    QtGui.QColor("red"),
                )
                self._error_sound()
                self.set_photo_main_text.emit(ErrorMessages.FILE_TOO_LARGE_TEXT)
                return
        except Exception as e:
            self.append_text.emit(
                f"[ERROR] Failed to check file size: {str(e)}", QtGui.QColor("red")
            )
            logging.error(f"Failed to check file size for '{self.file_path}': {str(e)}")
            self._error_sound()
            self.set_photo_main_text.emit(ErrorMessages.ERROR_TEXT)
            return

        # Emit status update
        self.status_update.emit("Computing image hash...")

        query_hash = dhash(self.file_path)
        query_hash = convert_hash(query_hash)

        # Emit status update
        self.status_update.emit("Searching for similar images...")

        try:
            # Use the validated search_range from above
            results = vptree.get_all_in_range(query_hash, search_range)
        except Exception as e:
            self.append_text.emit(ErrorMessages.SEARCH_FAILED.format(str(e)), QtGui.QColor("red"))
            self._error_sound()
            self.clear_photo_main.emit()
            return

        results = sorted(results)

        # Emit status update
        self.status_update.emit("Processing search results...")

        # Get similarity threshold from parent window settings
        similarity_threshold = DEFAULT_SIMILARITY_THRESHOLD
        if hasattr(self, "similarity_threshold"):
            similarity_threshold = self.similarity_threshold
        else:
            # Try to get from settings if not set as attribute
            try:
                similarity_threshold = int(
                    self.settings.value("similarity_threshold", str(DEFAULT_SIMILARITY_THRESHOLD))
                )
            except:
                similarity_threshold = DEFAULT_SIMILARITY_THRESHOLD

        # Clear hash tracking in parent window
        if self.parent_window:
            self.parent_window.image_hashes.clear()
            self.parent_window.hash_to_paths.clear()

        # Process results with filtering
        filtered_count = 0
        for dist, hsh in results:
            # Apply similarity threshold filter
            if dist > similarity_threshold:
                filtered_count += 1
                continue

            result_paths = hashes.get(hsh, [])

            # Store all paths for this hash
            if self.parent_window and result_paths:
                if isinstance(result_paths, list):
                    self.parent_window.hash_to_paths[hsh] = result_paths[:]
                else:
                    # Old format - single path as string
                    self.parent_window.hash_to_paths[hsh] = [result_paths]

            # Process each path
            paths_to_process = result_paths if isinstance(result_paths, list) else [result_paths]
            for result_path in paths_to_process:
                # Apply file type filter if enabled
                if hasattr(self, "file_type_filter_enabled") and self.file_type_filter_enabled:
                    if hasattr(self, "file_type_filter") and self.file_type_filter:
                        allowed_extensions = [
                            ext.strip().lower() for ext in self.file_type_filter.split(",")
                        ]
                        file_ext = os.path.splitext(result_path)[1].lower()
                        if file_ext not in allowed_extensions:
                            filtered_count += 1
                            continue

                # Apply file size filter if enabled
                if hasattr(self, "file_size_filter_enabled") and self.file_size_filter_enabled:
                    try:
                        file_size_mb = os.path.getsize(result_path) / (1024 * 1024)
                        min_size = getattr(self, "min_file_size", 0.0)
                        max_size = getattr(self, "max_file_size", 100.0)
                        if file_size_mb < min_size or file_size_mb > max_size:
                            filtered_count += 1
                            continue
                    except OSError:
                        # Skip files that can't be accessed
                        filtered_count += 1
                        continue

                # Apply dimensions filter if enabled
                if hasattr(self, "dimensions_filter_enabled") and self.dimensions_filter_enabled:
                    try:
                        with Image.open(result_path) as img:
                            width, height = img.size
                            min_width = getattr(self, "min_width", 0)
                            min_height = getattr(self, "min_height", 0)
                            if width < min_width or height < min_height:
                                filtered_count += 1
                                continue
                    except:
                        # Skip files that can't be opened as images
                        filtered_count += 1
                        continue

                # If all filters pass, add to results
                self.images_lock.lock()
                try:
                    self.images_found.append(result_path)
                    # Store hash for this image
                    if self.parent_window:
                        self.parent_window.image_hashes[result_path] = hsh
                finally:
                    self.images_lock.unlock()

        # Log filtered results info
        if filtered_count > 0:
            self.append_text.emit(
                f"[INFO] Filtered out {filtered_count} results based on search criteria",
                QtGui.QColor("blue"),
            )
        try:
            if os.path.isfile(self.file_path):
                # Emit signal to update main image on main thread
                self.main_image_update.emit(self.file_path)
                # Enable clear button when image is loaded
                if self.parent_window:
                    self.enable_parent_buttons.emit(
                        {"image_clear_button": True, "metadata_button": True}
                    )
                    # Set the main image path for metadata functionality
                    self.parent_window.main_image_path = self.file_path
            else:
                self.clear_photo_main.emit()
                self.clear_photo_viewer.emit()
                self.enable_buttons.emit(
                    {"next_button": False, "previous_button": False, "open_image_button": False}
                )
                self._error_sound()
                return
        except Exception as e:
            self.append_text.emit(
                ErrorMessages.IMAGE_SET_FAILED.format(str(e)), QtGui.QColor("red")
            )
            self.clear_photo_viewer.emit()
            self.enable_buttons.emit(
                {"next_button": False, "previous_button": False, "open_image_button": False}
            )
            # Reset window title
            self.set_window_title.emit("Offline Reverse Image Search")
            return

        self.images_lock.lock()
        try:
            buttons_to_enable = {"open_image_button": True}
            if len(self.images_found) > 1:
                buttons_to_enable["next_button"] = True
            self.enable_buttons.emit(buttons_to_enable)

            # Enable thumbnail toggle button
            if self.parent_window and hasattr(self.parent_window, "toggle_thumbnails_button"):
                self.enable_parent_buttons.emit({"toggle_thumbnails_button": True})

            self.queue_lock.lock()
            try:
                self.display_queue.clear()
                self.display_queue.extend(self.images_found)

                if self.display_queue:
                    self.current_lock.lock()
                    try:
                        self.current = self.display_queue[0]
                    finally:
                        self.current_lock.unlock()
                    self.set_label_text.emit(
                        "label_current",
                        f"Current {self.images_found.index(self.current) + 1}/{len(self.images_found)}",
                    )
                    self.set_image_signal.emit(self.current)
            finally:
                self.queue_lock.unlock()

            self.set_label_text.emit("label_result", f"Total results : {len(self.images_found)}")
            # Update window title with results count
            self.set_window_title.emit(
                f"Offline Reverse Image Search - {len(self.images_found)} results found"
            )

            # Add search to history
            # Use the actual search_range value that was used for the search
            if self.parent_window and hasattr(self.parent_window, "add_to_search_history"):
                self.add_to_history.emit(
                    self.file_path, self.images_found.copy(), search_range, "Success"
                )

            # Populate thumbnails if parent window has the method
            if self.parent_window and hasattr(self.parent_window, "populate_thumbnail_list"):
                # Use Qt's thread-safe signal mechanism to update UI
                QtCore.QMetaObject.invokeMethod(
                    self.parent_window,
                    "populate_thumbnail_list",
                    QtCore.Qt.ConnectionType.QueuedConnection,
                )

            logging.info("Links of found images:")
            for image_link in self.images_found:
                logging.info(image_link)

            # Emit final status update
            result_count = len(self.images_found)
        finally:
            self.images_lock.unlock()
        self.status_update.emit(f"Search complete. Found {result_count} similar images.")

        logging.info("done0")
        self.finished.emit()

    def _error_sound(self):
        """Play error sound if available."""
        try:
            from chime import info as ErrorSound

            ErrorSound()
        except ImportError:
            pass

    def _get_max_file_size_bytes(self):
        """Get max file size in bytes from constants."""
        from .constants import MAX_FILE_SIZE_BYTES

        return MAX_FILE_SIZE_BYTES

    def _get_max_file_size_mb(self):
        """Get max file size in MB from constants."""
        from .constants import MAX_FILE_SIZE_MB

        return MAX_FILE_SIZE_MB


class HTMLExportWorker(QtCore.QThread):
    """
    Worker thread for HTML export with progress reporting.
    Handles the export process in a separate thread to keep UI responsive.
    """

    # Signals for progress and completion
    progress = QtCore.pyqtSignal(int, str)  # progress percentage, current file
    finished = QtCore.pyqtSignal(bool, str)  # success, message/error

    def __init__(
        self, html_exporter, search_image, results, output_path, search_range, duplicates_info
    ):
        super().__init__()
        self.html_exporter = html_exporter
        self.search_image = search_image
        self.results = results
        self.output_path = output_path
        self.search_range = search_range
        self.duplicates_info = duplicates_info
        self._is_cancelled = False
        self._cancel_mutex = QtCore.QMutex()

    def cancel(self):
        """Cancel the export operation."""
        self._cancel_mutex.lock()
        self._is_cancelled = True
        self._cancel_mutex.unlock()

    def is_cancelled(self):
        """Check if the operation was cancelled."""
        self._cancel_mutex.lock()
        cancelled = self._is_cancelled
        self._cancel_mutex.unlock()
        return cancelled

    def run(self):
        """Run the export process in this thread."""
        import os

        try:
            # Prepare search data (10%)
            if self.is_cancelled():
                self.finished.emit(False, "Export cancelled")
                return

            self.progress.emit(10, "Processing search image...")
            search_data = {
                "image": self.search_image,
                "thumbnail": self.html_exporter.create_thumbnail_base64(self.search_image),
                "info": self.html_exporter.get_file_info(self.search_image),
            }

            # Process results with progress updates
            results_data = []
            total_results = len(self.results)

            for i, result_path in enumerate(self.results):
                if self.is_cancelled():
                    self.finished.emit(False, "Export cancelled")
                    return

                # Calculate progress (10% to 90% for processing images)
                progress_pct = 10 + int((i / total_results) * 80)
                self.progress.emit(progress_pct, f"Processing {os.path.basename(result_path)}...")

                result_info = {
                    "index": i + 1,
                    "path": result_path,
                    "filename": os.path.basename(result_path),
                    "directory": os.path.dirname(result_path),
                    "thumbnail": self.html_exporter.create_thumbnail_base64(result_path),
                    "info": self.html_exporter.get_file_info(result_path),
                }

                # Add duplicate info if available
                if self.duplicates_info and result_path in self.duplicates_info:
                    result_info["duplicates"] = self.duplicates_info[result_path]

                results_data.append(result_info)

            if self.is_cancelled():
                self.finished.emit(False, "Export cancelled")
                return

            # Generate HTML (90%)
            self.progress.emit(90, "Generating HTML...")
            from datetime import datetime

            html_content = self.html_exporter._generate_search_html(
                search_data,
                results_data,
                self.search_range,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )

            if self.is_cancelled():
                self.finished.emit(False, "Export cancelled")
                return

            # Write to file (95%)
            self.progress.emit(95, "Writing HTML file...")
            with open(self.output_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Complete (100%)
            self.progress.emit(100, "Export complete!")
            self.finished.emit(True, f"Search results exported to: {self.output_path}")

        except Exception as e:
            self.finished.emit(False, f"Error during export: {str(e)}")


class IndexWorker(QtCore.QObject):
    """
    A worker class that indexes images in the background.

    Attributes
    ----------
    progress : QtCore.pyqtSignal
        A signal that emits the progress of the indexing.
    finished : QtCore.pyqtSignal
        A signal that emits when the indexing is finished.
    status_update : QtCore.pyqtSignal
        A signal for status bar updates.
    """

    progress = QtCore.pyqtSignal(int)
    finished = QtCore.pyqtSignal()
    status_update = QtCore.pyqtSignal(str)  # Signal for status bar updates

    def __init__(self, parent_window=None):
        super().__init__()
        self.parent_window = parent_window

    def run(self) -> None:
        """
        Run the indexing process in the background.
        """
        if self.parent_window:
            self.parent_window.image_indexer()
        self.finished.emit()
