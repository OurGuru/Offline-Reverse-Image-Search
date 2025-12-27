"""
Zoomable and pannable image viewer widget for the main application.
"""

from PyQt6 import QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget


class ZoomableImageViewer(QWidget):
    """
    A custom widget that displays an image with zoom and pan capabilities.
    """

    def __init__(self, placeholder_text: str = "No image", parent=None):
        super().__init__(parent)
        self.placeholder_text = placeholder_text
        self.original_pixmap = None
        self.zoom_factor = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 5.0
        self.zoom_step = 0.1
        self.fit_to_window = True

        # Set up UI
        self.setup_ui()

        # Mouse tracking for panning
        self.drag_start_position = None
        self.is_dragging = False

    def setup_ui(self):
        """Set up the user interface."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area for the image
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Remove background and border
        self.scroll_area.setStyleSheet(
            """
            QScrollArea {
                background-color: transparent;
                border: 2px solid #999;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background-color: rgba(100, 100, 100, 100);
                width: 10px;
                height: 10px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background-color: rgba(150, 150, 150, 200);
                border-radius: 5px;
                min-height: 20px;
                min-width: 20px;
            }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background-color: rgba(180, 180, 180, 200);
            }
        """
        )

        # Image label
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)
        self.image_label.setText(self.placeholder_text)
        self.image_label.setStyleSheet(
            """
            QLabel {
                background-color: transparent;
                color: #666;
                font-size: 14px;
            }
        """
        )

        # Set minimum size for the label
        self.image_label.setMinimumSize(100, 100)

        # Add image label to scroll area
        self.scroll_area.setWidget(self.image_label)

        # Add scroll area to layout
        layout.addWidget(self.scroll_area)

        # Install event filter on image label for mouse events
        self.image_label.installEventFilter(self)

        # Install event filter on scroll area for wheel events
        self.scroll_area.installEventFilter(self)

        # Enable mouse tracking
        self.setMouseTracking(True)
        self.image_label.setMouseTracking(True)
        self.scroll_area.setMouseTracking(True)

    def set_image(self, image_path: str):
        """Set the image to display."""
        try:
            self.original_pixmap = QPixmap(image_path)
            if not self.original_pixmap.isNull():
                self.fit_to_window = True
                self.zoom_factor = 1.0
                self.update_image_display()

                # Enable interaction
                self.image_label.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.clear_image()
        except Exception as e:
            print(f"Error loading image: {e}")
            self.clear_image()

    def set_pixmap(self, pixmap: QPixmap):
        """Set the image from a QPixmap."""
        if not pixmap.isNull():
            self.original_pixmap = pixmap
            self.fit_to_window = True
            self.zoom_factor = 1.0
            self.update_image_display()

            # Enable interaction
            self.image_label.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.clear_image()

    def clear_image(self):
        """Clear the displayed image."""
        self.original_pixmap = None
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText(self.placeholder_text)
        self.image_label.setCursor(Qt.CursorShape.ArrowCursor)

    def update_image_display(self):
        """Update the image display based on current zoom and size."""
        if self.original_pixmap and not self.original_pixmap.isNull():
            if self.fit_to_window:
                # Fit image to scroll area size
                target_size = self.scroll_area.size()
                # Account for potential scrollbars
                target_size.setWidth(target_size.width() - 20)
                target_size.setHeight(target_size.height() - 20)

                scaled_pixmap = self.original_pixmap.scaled(
                    target_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.image_label.setPixmap(scaled_pixmap)
                self.image_label.resize(scaled_pixmap.size())
            else:
                # Apply zoom factor
                new_size = self.original_pixmap.size() * self.zoom_factor
                scaled_pixmap = self.original_pixmap.scaled(
                    new_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.image_label.setPixmap(scaled_pixmap)
                self.image_label.resize(scaled_pixmap.size())

    def resizeEvent(self, event):
        """Handle resize events."""
        super().resizeEvent(event)
        if self.fit_to_window and self.original_pixmap:
            self.update_image_display()

    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming."""
        # Always consume wheel events to prevent propagation
        event.accept()

        if self.original_pixmap and not self.original_pixmap.isNull():
            # Get the scroll delta
            delta = event.angleDelta().y()

            # Store current scroll position
            h_scroll = self.scroll_area.horizontalScrollBar()
            v_scroll = self.scroll_area.verticalScrollBar()

            h_percent = (
                h_scroll.value() / max(h_scroll.maximum(), 1) if h_scroll.maximum() > 0 else 0.5
            )
            v_percent = (
                v_scroll.value() / max(v_scroll.maximum(), 1) if v_scroll.maximum() > 0 else 0.5
            )

            # Calculate zoom change
            if delta > 0:
                # Zoom in
                new_zoom = min(self.max_zoom, self.zoom_factor + self.zoom_step)
            else:
                # Zoom out
                new_zoom = max(self.min_zoom, self.zoom_factor - self.zoom_step)

            # Apply zoom if it changed
            if new_zoom != self.zoom_factor:
                self.fit_to_window = False
                self.zoom_factor = new_zoom
                self.update_image_display()

                # Restore scroll position (approximately)
                QtCore.QTimer.singleShot(
                    10, lambda: self.restore_scroll_position(h_percent, v_percent)
                )

    def restore_scroll_position(self, h_percent, v_percent):
        """Restore scroll position after zoom."""
        h_scroll = self.scroll_area.horizontalScrollBar()
        v_scroll = self.scroll_area.verticalScrollBar()

        if h_scroll.maximum() > 0:
            h_scroll.setValue(int(h_scroll.maximum() * h_percent))
        if v_scroll.maximum() > 0:
            v_scroll.setValue(int(v_scroll.maximum() * v_percent))

    def eventFilter(self, obj, event):
        """Event filter to handle mouse events on the image label and scroll area."""
        # Handle wheel events on both scroll area and image label
        if event.type() == QtCore.QEvent.Type.Wheel:
            if self.original_pixmap and not self.original_pixmap.isNull():
                # Get the scroll delta
                delta = event.angleDelta().y()

                # Store current scroll position
                h_scroll = self.scroll_area.horizontalScrollBar()
                v_scroll = self.scroll_area.verticalScrollBar()

                h_percent = (
                    h_scroll.value() / max(h_scroll.maximum(), 1) if h_scroll.maximum() > 0 else 0.5
                )
                v_percent = (
                    v_scroll.value() / max(v_scroll.maximum(), 1) if v_scroll.maximum() > 0 else 0.5
                )

                # Calculate zoom change
                if delta > 0:
                    # Zoom in
                    new_zoom = min(self.max_zoom, self.zoom_factor + self.zoom_step)
                else:
                    # Zoom out
                    new_zoom = max(self.min_zoom, self.zoom_factor - self.zoom_step)

                # Apply zoom if it changed
                if new_zoom != self.zoom_factor:
                    self.fit_to_window = False
                    self.zoom_factor = new_zoom
                    self.update_image_display()

                    # Restore scroll position (approximately)
                    QtCore.QTimer.singleShot(
                        10, lambda: self.restore_scroll_position(h_percent, v_percent)
                    )

                # Always consume the event
                event.accept()
                return True

        # Handle other events on image label
        if obj == self.image_label and self.original_pixmap:
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    # Only allow dragging if image is larger than viewport
                    h_scroll = self.scroll_area.horizontalScrollBar()
                    v_scroll = self.scroll_area.verticalScrollBar()

                    if h_scroll.maximum() > 0 or v_scroll.maximum() > 0:
                        self.drag_start_position = event.position().toPoint()
                        self.is_dragging = True
                        self.image_label.setCursor(Qt.CursorShape.ClosedHandCursor)
                        return True

            elif event.type() == QtCore.QEvent.Type.MouseMove:
                if self.is_dragging and self.drag_start_position is not None:
                    # Calculate drag delta
                    delta = event.position().toPoint() - self.drag_start_position

                    # Apply to scroll bars (negative because we want opposite direction)
                    h_scroll = self.scroll_area.horizontalScrollBar()
                    v_scroll = self.scroll_area.verticalScrollBar()

                    h_scroll.setValue(h_scroll.value() - delta.x())
                    v_scroll.setValue(v_scroll.value() - delta.y())

                    self.drag_start_position = event.position().toPoint()
                    return True

            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton and self.is_dragging:
                    self.is_dragging = False
                    self.drag_start_position = None

                    # Update cursor based on scrollbar presence
                    h_scroll = self.scroll_area.horizontalScrollBar()
                    v_scroll = self.scroll_area.verticalScrollBar()

                    if h_scroll.maximum() > 0 or v_scroll.maximum() > 0:
                        self.image_label.setCursor(Qt.CursorShape.OpenHandCursor)
                    else:
                        self.image_label.setCursor(Qt.CursorShape.ArrowCursor)
                    return True

            elif event.type() == QtCore.QEvent.Type.MouseButtonDblClick:
                if event.button() == Qt.MouseButton.LeftButton:
                    # Double-click to reset zoom
                    self.fit_to_window = True
                    self.zoom_factor = 1.0
                    self.update_image_display()
                    return True

        return super().eventFilter(obj, event)

    def contextMenuEvent(self, event):
        """Handle context menu events."""
        # Prevent context menu
        event.accept()

    # Compatibility methods for existing code
    def setPixmap(self, pixmap: QPixmap):
        """Compatibility method for setPixmap calls."""
        # Store the original pixmap without scaling
        if pixmap and not pixmap.isNull():
            self.original_pixmap = pixmap
            self.image_label.setPixmap(pixmap)
            # Reset zoom to fit the pre-scaled image
            self.zoom_factor = 1.0
            self.scroll_area.setWidgetResizable(False)
            self.image_label.adjustSize()

    def setText(self, text: str):
        """Compatibility method for setText calls."""
        self.clear_image()
        self.image_label.setText(text)

    def width(self):
        """Get the width of the scroll area."""
        return self.scroll_area.width()

    def height(self):
        """Get the height of the scroll area."""
        return self.scroll_area.height()
