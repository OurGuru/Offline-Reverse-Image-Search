"""
File handler module for managing drag/drop operations and file processing.
"""

import logging
import os
from io import BytesIO
from re import findall

from PIL import Image
from PyQt6 import QtGui
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget
from requests import exceptions as RequestExceptions
from requests import get as requestsGet

from ..core.constants import (
    REQUEST_TIMEOUT_SECONDS,
    SUPPORTED_IMAGE_EXTENSIONS,
    ErrorMessages,
)


class FileHandler(QObject):
    """
    Manages file operations including drag/drop handling and URL downloads.

    Signals
    -------
    file_ready : pyqtSignal(str)
        Emitted when a file is ready to be processed, with the file path.
    error_occurred : pyqtSignal(str, str)
        Emitted when an error occurs, with error message and color.
    status_update : pyqtSignal(str)
        Emitted to update status messages.
    """

    file_ready = pyqtSignal(str)  # Emits file path when ready
    error_occurred = pyqtSignal(str, str)  # Emits error message and color
    status_update = pyqtSignal(str)  # Emits status messages

    def __init__(self, parent=None):
        """
        Initialize the FileHandler.

        Parameters
        ----------
        parent : QObject, optional
            Parent object.
        """
        super().__init__(parent)
        self.is_processing = False
        self.test_file_ext = ""
        self.dir_path = os.getcwd()

    def can_accept_drag(self, mime_data) -> bool:
        """
        Check if the drag event should be accepted.

        Parameters
        ----------
        mime_data : QMimeData
            The mime data from the drag event.

        Returns
        -------
        bool
            True if the drag should be accepted.
        """
        return mime_data.hasImage or mime_data.hasUrls()

    def handle_drag_enter(self, event: QtGui.QDragEnterEvent) -> None:
        """
        Handle drag enter events.

        Parameters
        ----------
        event : QtGui.QDragEnterEvent
            The drag enter event.
        """
        if self.can_accept_drag(event.mimeData()):
            event.accept()
        else:
            event.ignore()

    def handle_drag_move(self, event: QtGui.QDragMoveEvent) -> None:
        """
        Handle drag move events.

        Parameters
        ----------
        event : QtGui.QDragMoveEvent
            The drag move event.
        """
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def handle_drop(self, event: QtGui.QDropEvent) -> None:
        """
        Handle drop events.

        Parameters
        ----------
        event : QtGui.QDropEvent
            The drop event.
        """
        # Check if already processing
        if self.is_processing:
            self.error_occurred.emit(ErrorMessages.ALREADY_PROCESSING, "orange")
            event.ignore()
            return

        # Set processing flag
        self.is_processing = True

        logging.info("Processing dropped item")

        # Handle HTML drops (images from web)
        if event.mimeData().html():
            self._handle_html_drop(event)
        # Handle file drops
        elif event.mimeData().hasUrls():
            self._handle_file_drop(event)
        else:
            self.error_occurred.emit(ErrorMessages.NO_FILE_OR_IMAGE_FOUND, "red")
            event.ignore()
            self.is_processing = False

    def _handle_html_drop(self, event: QtGui.QDropEvent) -> None:
        """
        Handle HTML drops (typically images dragged from web browsers).

        Parameters
        ----------
        event : QtGui.QDropEvent
            The drop event.
        """
        try:
            # Extract URL from HTML
            url_match = findall(r'src="(http.*?\..+?)"', event.mimeData().html())
            if not url_match:
                raise ValueError("No URL found in HTML")

            url = url_match[0]
            logging.info(f"Downloading image from URL: {url}")

            # Download the image
            file_path = self._download_image_from_url(url)
            if file_path:
                event.accept()
                self.file_ready.emit(file_path)
            else:
                event.ignore()

        except Exception as e:
            logging.error(f"Failed to handle HTML drop: {e}")
            self.error_occurred.emit(f"Failed to process dropped image: {str(e)}", "red")
            event.ignore()
        finally:
            self.is_processing = False

    def _handle_file_drop(self, event: QtGui.QDropEvent) -> None:
        """
        Handle file drops from the file system.

        Parameters
        ----------
        event : QtGui.QDropEvent
            The drop event.
        """
        try:
            urls = event.mimeData().urls()
            if not urls:
                raise ValueError("No URLs in drop event")

            # Get the first file path
            file_path = urls[0].toLocalFile()

            if not file_path:
                raise ValueError("No local file path")

            # Validate file type
            if self._is_supported_image(file_path):
                event.accept()
                self.file_ready.emit(file_path)
            else:
                self.error_occurred.emit(ErrorMessages.FILE_FORMAT_NOT_SUPPORTED, "red")
                event.ignore()

        except Exception as e:
            logging.error(f"Failed to handle file drop: {e}")
            self.error_occurred.emit(ErrorMessages.NO_FILE_OR_IMAGE_FOUND, "red")
            event.ignore()
        finally:
            self.is_processing = False

    def _download_image_from_url(self, url: str) -> str | None:
        """
        Download an image from a URL.

        Parameters
        ----------
        url : str
            The URL to download from.

        Returns
        -------
        Optional[str]
            The path to the downloaded file, or None if failed.
        """
        try:
            self.status_update.emit("Downloading image from URL...")

            # Download the image
            response = requestsGet(url, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()

            # Open the image to get format
            image_data = BytesIO(response.content)
            image = Image.open(image_data)
            self.test_file_ext = image.format.lower()

            # Save the image
            file_path = os.path.join(self.dir_path, f"testfile.{self.test_file_ext}")
            image.save(file_path)

            logging.info(f"Image downloaded and saved to: {file_path}")
            return file_path

        except RequestExceptions.Timeout:
            self.error_occurred.emit(ErrorMessages.DOWNLOAD_TIMEOUT, "red")
            self.status_update.emit(ErrorMessages.DOWNLOAD_TIMEOUT_TEXT)
        except RequestExceptions.ConnectionError:
            self.error_occurred.emit(ErrorMessages.CONNECTION_ERROR, "red")
            self.status_update.emit(ErrorMessages.CONNECTION_ERROR_TEXT)
        except RequestExceptions.HTTPError as e:
            self.error_occurred.emit(ErrorMessages.HTTP_ERROR.format(e), "red")
            self.status_update.emit(f"HTTP error: {e}")
        except Exception as e:
            self.error_occurred.emit(ErrorMessages.DOWNLOAD_FAILED.format(str(e)), "red")
            self.status_update.emit(ErrorMessages.DOWNLOAD_FAILED_TEXT)

        return None

    def _is_supported_image(self, file_path: str) -> bool:
        """
        Check if a file is a supported image type.

        Parameters
        ----------
        file_path : str
            Path to the file.

        Returns
        -------
        bool
            True if the file is a supported image type.
        """
        return file_path.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS)

    def cleanup_test_file(self) -> None:
        """
        Clean up any temporary test files created during downloads.
        """
        if self.test_file_ext:
            test_file_path = os.path.join(self.dir_path, f"testfile.{self.test_file_ext}")
            if os.path.isfile(test_file_path):
                try:
                    os.remove(test_file_path)
                    logging.info(f"Cleaned up test file: {test_file_path}")
                except Exception as e:
                    logging.error(f"Failed to clean up test file: {e}")

    def set_processing_flag(self, is_processing: bool) -> None:
        """
        Set the processing flag.

        Parameters
        ----------
        is_processing : bool
            Whether file processing is in progress.
        """
        self.is_processing = is_processing


class DragDropWidget(QWidget):
    """
    A widget that accepts drag and drop operations.
    """

    def __init__(self, file_handler: FileHandler, parent=None):
        """
        Initialize the drag/drop widget.

        Parameters
        ----------
        file_handler : FileHandler
            The file handler to use for processing drops.
        parent : QWidget, optional
            Parent widget.
        """
        super().__init__(parent)
        self.file_handler = file_handler
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        """
        Handle drag enter events.

        Parameters
        ----------
        event : QtGui.QDragEnterEvent
            The drag enter event.
        """
        self.file_handler.handle_drag_enter(event)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        """
        Handle drag move events.

        Parameters
        ----------
        event : QtGui.QDragMoveEvent
            The drag move event.
        """
        self.file_handler.handle_drag_move(event)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        """
        Handle drop events.

        Parameters
        ----------
        event : QtGui.QDropEvent
            The drop event.
        """
        self.file_handler.handle_drop(event)
