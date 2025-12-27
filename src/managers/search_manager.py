"""
Search functionality manager for the Offline Reverse Image Search application.

This module manages search operations, including worker thread management,
result processing, and UI updates for image similarity searches.
"""

import logging
import os

from PyQt6 import QtCore
from PyQt6.QtGui import QColor, QPixmap

from ..core.constants import THREAD_WAIT_TIMEOUT_MS, ErrorMessages
from ..core.workers import Worker


class SearchManager:
    """Manages search operations and results."""

    def __init__(self, parent):
        self.parent = parent
        self.is_processing = False

    def worker_thread(self) -> None:
        """
        Create a worker thread to run the image search.
        """
        # Ensure we have a valid file path before starting
        if hasattr(self.parent, "current_image_path") and self.parent.current_image_path:
            # Update the file_path to ensure consistency
            self.parent.file_path = self.parent.current_image_path

        if not self.parent.file_path or not os.path.isfile(self.parent.file_path):
            logging.error(f"Invalid file path for search: '{self.parent.file_path}'")
            self.parent.append_colored_text(
                "[ERROR] Cannot start search: Invalid or empty file path", QColor("red")
            )
            # Reset UI state
            if hasattr(self.parent, "search_progress"):
                self.parent.search_progress.setVisible(False)
            if hasattr(self.parent, "search_button"):
                self.parent.search_button.setEnabled(True)
                self.parent.search_button.setText("Start Search")
            if hasattr(self.parent, "update_status_bar"):
                self.parent.update_status_bar("Search failed - no valid image selected")
            return

        # Clear existing search results before starting new search
        if hasattr(self.parent, "clear_search_results"):
            self.parent.clear_search_results()

        # If a thread is already running, stop it properly
        if hasattr(self.parent, "thread") and self.parent.thread is not None:
            try:
                # Ensure self.thread is actually a QThread object before calling isRunning()
                if (
                    isinstance(self.parent.thread, QtCore.QThread)
                    and self.parent.thread.isRunning()
                ):
                    # Request the thread to stop and wait for it
                    self.parent.thread.requestInterruption()
                    self.parent.thread.quit()
                    if not self.parent.thread.wait(THREAD_WAIT_TIMEOUT_MS):  # Wait up to 5 seconds
                        self.parent.thread.terminate()  # Force terminate if it doesn't stop
                        self.parent.thread.wait()
            except RuntimeError:
                # The thread was already deleted, so we can ignore this error
                pass
            finally:
                # Clean up old worker and thread references
                if hasattr(self.parent, "worker"):
                    self.parent.worker = None
                self.parent.thread = None

        # Create a QThread object
        self.parent.thread = QtCore.QThread()
        # Create a worker object
        self.parent.worker = Worker(
            self.parent.images_found,
            self.parent.file_path,
            self.parent.photo_main,
            self.parent.photo_viewer,
            self.parent.next_button,
            self.parent.previous_button,
            self.parent.open_image_button,
            self.parent.label_result,
            self.parent.label_current,
            self.parent.set_image,
            self.parent.append_colored_text,
            self.parent.display_queue,
            self.parent.current,
            self.parent.settings.settings,
            self.parent.images_lock,
            self.parent.queue_lock,
            self.parent.current_lock,
            self.parent,
        )

        # Pass the new settings to the worker
        self.parent.worker.similarity_threshold = self.parent.similarity_threshold.value()
        self.parent.worker.file_type_filter_enabled = self.parent.file_type_check.isChecked()
        self.parent.worker.file_type_filter = self.parent.file_type_filter.text()
        self.parent.worker.file_size_filter_enabled = self.parent.file_size_check.isChecked()
        self.parent.worker.min_file_size = self.parent.min_size_spin.value()
        self.parent.worker.max_file_size = self.parent.max_size_spin.value()
        self.parent.worker.dimensions_filter_enabled = self.parent.dimensions_check.isChecked()
        self.parent.worker.min_width = self.parent.min_width_spin.value()
        self.parent.worker.min_height = self.parent.min_height_spin.value()

        # Pass the search range from UI
        self.parent.worker.search_range_value = self.parent.search_range.value()
        # Move worker to the thread
        self.parent.worker.moveToThread(self.parent.thread)
        # Connect signals and slots
        self.parent.thread.started.connect(self.parent.worker.run)
        self.parent.worker.status_update.connect(self.parent.update_status_bar)
        self.parent.worker.main_image_update.connect(self.update_main_image)

        # Connect all the new signals for thread-safe UI updates
        self.parent.worker.append_text.connect(self.handle_append_text)
        self.parent.worker.set_photo_main_text.connect(self.handle_set_photo_main_text)
        self.parent.worker.clear_photo_main.connect(self.handle_clear_photo_main)
        self.parent.worker.clear_photo_viewer.connect(self.handle_clear_photo_viewer)
        self.parent.worker.set_photo_viewer_text.connect(self.handle_set_photo_viewer_text)
        self.parent.worker.enable_buttons.connect(self.handle_enable_buttons)
        self.parent.worker.set_label_text.connect(self.handle_set_label_text)
        self.parent.worker.set_image_signal.connect(self.handle_set_image)
        self.parent.worker.set_window_title.connect(self.handle_set_window_title)
        self.parent.worker.enable_parent_buttons.connect(self.handle_enable_parent_buttons)
        self.parent.worker.add_to_history.connect(self.handle_add_to_history)

        self.parent.worker.finished.connect(self.parent.thread.quit)
        self.parent.worker.finished.connect(self.parent.worker.deleteLater)
        self.parent.worker.finished.connect(self.on_search_complete)
        self.parent.thread.finished.connect(self.parent.thread.deleteLater)
        # Clean up references when thread is done
        self.parent.thread.finished.connect(lambda: setattr(self.parent, "thread", None))
        self.parent.worker.finished.connect(lambda: setattr(self.parent, "worker", None))
        # Reset processing flag when worker finishes
        self.parent.worker.finished.connect(lambda: setattr(self, "is_processing", False))
        # Start the thread
        self.parent.thread.start()

    def next(self) -> None:
        """
        Display the next image in the queue.
        """
        with self.parent.queue_lock:
            self.parent.display_queue.rotate(-1)
            with self.parent.current_lock:
                self.parent.current = self.parent.display_queue[0]

            with self.parent.images_lock:
                current_index = self.parent.images_found.index(self.parent.current)
                total_images = len(self.parent.images_found)

            self.parent.label_current.setText(f"Current {current_index + 1}/{total_images}")
            self.parent.set_image(self.parent.current)

            if current_index + 1 == total_images:
                self.parent.next_button.setEnabled(False)
            elif not self.parent.previous_button.isEnabled() and current_index != 0:
                self.parent.previous_button.setEnabled(True)

    def previous(self) -> None:
        """
        Display the previous image in the queue.
        """
        with self.parent.queue_lock:
            self.parent.display_queue.rotate(1)
            with self.parent.current_lock:
                self.parent.current = self.parent.display_queue[0]

            with self.parent.images_lock:
                current_index = self.parent.images_found.index(self.parent.current)
                total_images = len(self.parent.images_found)

            self.parent.label_current.setText(f"Current {current_index + 1}/{total_images}")
            self.parent.set_image(self.parent.current)

            if current_index == 0:
                self.parent.previous_button.setEnabled(False)
            elif not self.parent.next_button.isEnabled() and current_index != total_images:
                self.parent.next_button.setEnabled(True)

    def set_image(self, path: str) -> None:
        """
        Set the image to the photo viewer.

        Parameters
        ----------
        path : str
            The path to the image file.
        """
        if path and os.path.isfile(path):
            self.parent._current_image_path = path
            pixmap = QPixmap(path).scaled(
                self.parent.photo_viewer.width(),
                self.parent.photo_viewer.height(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            self.parent.photo_viewer.setPixmap(pixmap)
        else:
            self.parent.append_colored_text(ErrorMessages.IMAGE_FILE_NOT_FOUND, QColor("red"))
            self.parent.photo_viewer.setText(ErrorMessages.IMAGE_FILE_NOT_FOUND_TEXT)
            self._error_sound()

    def update_main_image(self, file_path: str):
        """Update the main image viewer (called from worker thread via signal)."""
        if hasattr(self.parent.photo_main, "set_image"):
            self.parent.photo_main.set_image(file_path)
        else:
            # Fallback for QLabel
            pixmap = QPixmap(file_path).scaled(
                self.parent.photo_main.width(),
                self.parent.photo_main.height(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            self.parent.photo_main.setPixmap(pixmap)

        # Enable buttons
        if hasattr(self.parent, "image_clear_button"):
            self.parent.image_clear_button.setEnabled(True)
        if hasattr(self.parent, "metadata_button"):
            self.parent.metadata_button.setEnabled(True)
        # Set the main image path for metadata functionality
        self.parent.main_image_path = file_path

    def _error_sound(self):
        """Play error sound if available."""
        try:
            from chime import info as ErrorSound

            ErrorSound()
        except ImportError:
            pass

    # Handler methods for worker signals
    def handle_append_text(self, text: str, color: QColor):
        """Handle append text signal from worker thread."""
        self.parent.append_colored_text(text, color)

    def handle_set_photo_main_text(self, text: str):
        """Handle set photo main text signal from worker thread."""
        if hasattr(self.parent.photo_main, "setText"):
            self.parent.photo_main.setText(text)

    def handle_clear_photo_main(self):
        """Handle clear photo main signal from worker thread."""
        if hasattr(self.parent.photo_main, "clear_image"):
            self.parent.photo_main.clear_image()
        elif hasattr(self.parent.photo_main, "setText"):
            self.parent.photo_main.setText(ErrorMessages.ERROR_TEXT)

    def handle_clear_photo_viewer(self):
        """Handle clear photo viewer signal from worker thread."""
        if hasattr(self.parent.photo_viewer, "clear_image"):
            self.parent.photo_viewer.clear_image()
        elif hasattr(self.parent.photo_viewer, "setText"):
            self.parent.photo_viewer.setText(ErrorMessages.IMAGE_FILE_NOT_FOUND_TEXT)

    def handle_set_photo_viewer_text(self, text: str):
        """Handle set photo viewer text signal from worker thread."""
        if hasattr(self.parent.photo_viewer, "setText"):
            self.parent.photo_viewer.setText(text)

    def handle_enable_buttons(self, buttons_dict: dict):
        """Handle enable buttons signal from worker thread."""
        for button_name, enabled in buttons_dict.items():
            if hasattr(self.parent, button_name):
                button = getattr(self.parent, button_name)
                if hasattr(button, "setEnabled"):
                    button.setEnabled(enabled)

    def handle_set_label_text(self, label_name: str, text: str):
        """Handle set label text signal from worker thread."""
        if hasattr(self.parent, label_name):
            label = getattr(self.parent, label_name)
            if hasattr(label, "setText"):
                label.setText(text)

    def handle_set_image(self, path: str):
        """Handle set image signal from worker thread."""
        self.parent.set_image(path)

    def handle_set_window_title(self, title: str):
        """Handle set window title signal from worker thread."""
        self.parent.setWindowTitle(title)

    def handle_enable_parent_buttons(self, buttons_dict: dict):
        """Handle enable parent buttons signal from worker thread."""
        for button_name, enabled in buttons_dict.items():
            if hasattr(self.parent, button_name):
                button = getattr(self.parent, button_name)
                if hasattr(button, "setEnabled"):
                    button.setEnabled(enabled)

    def handle_add_to_history(self, file_path: str, results: list, search_range: int, status: str):
        """Handle add to history signal from worker thread."""
        if hasattr(self.parent, "add_to_search_history"):
            self.parent.add_to_search_history(file_path, results, search_range, status)

    def on_search_complete(self):
        """Handle search completion - hide progress and reset button."""
        if hasattr(self.parent, "search_progress"):
            self.parent.search_progress.setVisible(False)
        if hasattr(self.parent, "search_button"):
            self.parent.search_button.setEnabled(True)
            self.parent.search_button.setText("Start Search")
        if hasattr(self.parent, "update_status_bar"):
            self.parent.update_status_bar("Search complete")
