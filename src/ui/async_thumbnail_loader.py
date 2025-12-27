"""
Asynchronous thumbnail loader for non-blocking image loading.
"""

import os
import weakref

from PyQt6.QtCore import QMutex, QMutexLocker, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap


class ThumbnailLoadWorker(QThread):
    """
    Worker thread that loads thumbnail images in the background.
    """

    thumbnail_loaded = pyqtSignal(str, QPixmap, int)  # image_path, pixmap, size

    def __init__(self):
        super().__init__()
        self.queue = []
        self.mutex = QMutex()
        self.is_running = False

    def add_thumbnail(self, image_path, size):
        """Add a thumbnail to the loading queue."""
        with QMutexLocker(self.mutex):
            # Check if already in queue
            for item in self.queue:
                if item[0] == image_path and item[1] == size:
                    return
            self.queue.append((image_path, size))

    def clear_queue(self):
        """Clear the loading queue."""
        with QMutexLocker(self.mutex):
            self.queue.clear()

    def stop(self):
        """Stop the worker thread."""
        self.is_running = False
        self.wait()

    def run(self):
        """Run the worker thread."""
        self.is_running = True

        while self.is_running:
            # Get next item from queue
            item = None
            with QMutexLocker(self.mutex):
                if self.queue:
                    item = self.queue.pop(0)

            if item:
                image_path, size = item
                try:
                    # Load the image in this worker thread
                    if os.path.exists(image_path):
                        pixmap = QPixmap(image_path)
                        if not pixmap.isNull():
                            # Calculate dimensions - account for border
                            box_size = size - 4

                            # Get original dimensions
                            orig_width = pixmap.width()
                            orig_height = pixmap.height()

                            # Calculate scale factor to fill width
                            scale_factor = box_size / orig_width

                            # Calculate new height
                            new_height = int(orig_height * scale_factor)

                            # If height exceeds box size, scale by height instead
                            if new_height > box_size:
                                scale_factor = box_size / orig_height
                                new_width = int(orig_width * scale_factor)
                                new_height = box_size
                            else:
                                new_width = box_size

                            # Scale the pixmap
                            scaled_pixmap = pixmap.scaled(
                                new_width,
                                new_height,
                                Qt.AspectRatioMode.IgnoreAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )

                            # If the image is taller than wide, crop to fit
                            if scaled_pixmap.height() > box_size:
                                # Crop from center
                                y_offset = (scaled_pixmap.height() - box_size) // 2
                                scaled_pixmap = scaled_pixmap.copy(0, y_offset, box_size, box_size)

                            # Emit the loaded pixmap
                            self.thumbnail_loaded.emit(image_path, scaled_pixmap, size)
                except Exception as e:
                    print(f"Error loading thumbnail {image_path}: {e}")
            else:
                # No items in queue, sleep briefly
                self.msleep(10)


class ThumbnailLoaderManager:
    """
    Manager for handling asynchronous thumbnail loading using worker thread.
    """

    def __init__(self, parent=None):
        self.parent = parent
        self.worker = ThumbnailLoadWorker()
        self.worker.thumbnail_loaded.connect(self._on_thumbnail_loaded)
        self.worker.start()

        # Keep track of widgets waiting for thumbnails
        self.pending_widgets = {}  # image_path -> list of weak references to widgets

    def add_thumbnails(self, thumbnails):
        """Add thumbnails to be loaded."""
        for thumbnail in thumbnails:
            if hasattr(thumbnail, "image_path") and hasattr(thumbnail, "current_size"):
                # Store weak reference to widget
                if thumbnail.image_path not in self.pending_widgets:
                    self.pending_widgets[thumbnail.image_path] = []
                self.pending_widgets[thumbnail.image_path].append(weakref.ref(thumbnail))

                # Add to worker queue
                self.worker.add_thumbnail(thumbnail.image_path, thumbnail.current_size)

    def _on_thumbnail_loaded(self, image_path, pixmap, size):
        """Handle loaded thumbnail from worker thread."""
        # Find widgets waiting for this thumbnail
        if image_path in self.pending_widgets:
            widgets = self.pending_widgets[image_path]
            # Remove dead references and update live ones
            live_widgets = []
            for widget_ref in widgets:
                widget = widget_ref()
                if widget is not None:
                    try:
                        # Check if widget still exists and has the expected size
                        if widget.current_size == size:
                            widget.set_loaded_pixmap(pixmap)
                        else:
                            # Size mismatch, keep in pending for correct size
                            live_widgets.append(widget_ref)
                    except RuntimeError:
                        # Widget was deleted
                        pass

            # Update or remove the entry
            if live_widgets:
                self.pending_widgets[image_path] = live_widgets
            else:
                del self.pending_widgets[image_path]

    def clear(self):
        """Clear all pending thumbnails."""
        self.worker.clear_queue()
        self.pending_widgets.clear()

    def stop(self):
        """Stop the loader."""
        self.worker.stop()
