"""
Custom UI components for the Offline Reverse Image Search application.
"""

import os

from PyQt6 import QtCore
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QScrollArea,
    QSplashScreen,
    QVBoxLayout,
    QWidget,
)

from ..utils.utils import get_app_logo


class ImagePopupWidget(QWidget):
    """
    Popup widget that displays an image taking 80% of the screen with zoom functionality.
    """

    closed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(
            """
            ImagePopupWidget {
                background-color: rgba(0, 0, 0, 180);
            }
        """
        )

        # Zoom parameters
        self.zoom_factor = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 5.0
        self.zoom_step = 0.1
        self.original_pixmap = None

        # Create scroll area for zoom functionality
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet(
            """
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical, QScrollBar:horizontal {
                background-color: rgba(255, 255, 255, 100);
                width: 12px;
                height: 12px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background-color: rgba(255, 255, 255, 200);
                border-radius: 6px;
            }
        """
        )

        # Install event filter to intercept wheel events
        self.scroll_area.installEventFilter(self)

        # Create image label without border
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)
        self.image_label.setStyleSheet(
            """
            QLabel {
                background-color: transparent;
                border: none;
            }
        """
        )

        # Set up layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll_area)

        self.scroll_area.setWidget(self.image_label)

        # Enable mouse wheel events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Hide initially
        self.hide()

    def show_image(self, image_path: str):
        """Show the popup with the specified image."""
        try:
            # Get screen geometry
            screen = QApplication.primaryScreen()
            screen_rect = screen.geometry()

            # Set popup to full screen
            self.setGeometry(screen_rect)

            # Load original image
            self.original_pixmap = QPixmap(image_path)
            if not self.original_pixmap.isNull():
                # Reset zoom to 1.0 (will be 80% of screen)
                self.zoom_factor = 1.0

                # Calculate 80% of screen size for initial display
                target_width = int(screen_rect.width() * 0.8)
                target_height = int(screen_rect.height() * 0.8)

                # Scale image to fit within 80% of screen while maintaining aspect ratio
                scaled_pixmap = self.original_pixmap.scaled(
                    target_width,
                    target_height,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

                # Set image
                self.image_label.setPixmap(scaled_pixmap)
                self.image_label.resize(scaled_pixmap.size())

                # Calculate scroll area size (slightly larger than image to avoid unnecessary scrollbars)
                scroll_width = min(scaled_pixmap.width() + 20, screen_rect.width())
                scroll_height = min(scaled_pixmap.height() + 20, screen_rect.height())

                # Center the scroll area on screen
                scroll_x = (screen_rect.width() - scroll_width) // 2
                scroll_y = (screen_rect.height() - scroll_height) // 2

                self.scroll_area.setGeometry(scroll_x, scroll_y, scroll_width, scroll_height)

            self.show()
            self.raise_()
            self.setFocus()  # Ensure widget can receive wheel events

        except Exception as e:
            print(f"Error showing popup: {e}")

    def update_image_zoom(self):
        """Update the image based on current zoom factor."""
        if self.original_pixmap and not self.original_pixmap.isNull():
            # Get screen geometry for base sizing
            screen = QApplication.primaryScreen()
            screen_rect = screen.geometry()

            # Calculate base size (80% of screen) - this is our zoom level 1.0
            base_width = int(screen_rect.width() * 0.8)
            base_height = int(screen_rect.height() * 0.8)

            # Scale original to 80% of screen size first
            base_pixmap = self.original_pixmap.scaled(
                base_width,
                base_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            # Apply zoom factor to the base size
            final_width = int(base_pixmap.width() * self.zoom_factor)
            final_height = int(base_pixmap.height() * self.zoom_factor)

            # Create final scaled pixmap
            final_pixmap = self.original_pixmap.scaled(
                final_width,
                final_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            # Update image label
            self.image_label.setPixmap(final_pixmap)
            self.image_label.resize(final_pixmap.size())

            # Update scroll area size if needed (only if image is smaller than current scroll area)
            current_scroll_width = self.scroll_area.width()
            current_scroll_height = self.scroll_area.height()

            # Calculate new scroll area size
            new_scroll_width = min(final_width + 20, screen_rect.width())
            new_scroll_height = min(final_height + 20, screen_rect.height())

            # Update scroll area size and position if significantly different
            if (
                abs(new_scroll_width - current_scroll_width) > 50
                or abs(new_scroll_height - current_scroll_height) > 50
            ):
                # Recenter the scroll area
                scroll_x = (screen_rect.width() - new_scroll_width) // 2
                scroll_y = (screen_rect.height() - new_scroll_height) // 2
                self.scroll_area.setGeometry(
                    scroll_x, scroll_y, new_scroll_width, new_scroll_height
                )

    def eventFilter(self, obj, event):
        """Event filter to intercept wheel events for zooming."""
        if obj == self.scroll_area and event.type() == QtCore.QEvent.Type.Wheel:
            # Handle wheel events for zooming instead of scrolling
            self.wheelEvent(event)
            return True  # Event handled, don't pass to scroll area
        return super().eventFilter(obj, event)

    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming."""
        if self.original_pixmap and not self.original_pixmap.isNull():
            # Get the scroll delta
            delta = event.angleDelta().y()

            # Calculate zoom change
            if delta > 0:
                # Zoom in
                new_zoom = min(self.max_zoom, self.zoom_factor + self.zoom_step)
            else:
                # Zoom out
                new_zoom = max(self.min_zoom, self.zoom_factor - self.zoom_step)

            # Apply zoom if it changed
            if new_zoom != self.zoom_factor:
                # Store current scroll position as percentage
                h_scroll = self.scroll_area.horizontalScrollBar()
                v_scroll = self.scroll_area.verticalScrollBar()

                h_percent = (
                    h_scroll.value() / max(h_scroll.maximum(), 1) if h_scroll.maximum() > 0 else 0.5
                )
                v_percent = (
                    v_scroll.value() / max(v_scroll.maximum(), 1) if v_scroll.maximum() > 0 else 0.5
                )

                # Update zoom
                self.zoom_factor
                self.zoom_factor = new_zoom
                self.update_image_zoom()

                # Restore scroll position (approximately) - delay to allow UI update
                QtCore.QTimer.singleShot(
                    10, lambda: self.restore_scroll_position(h_percent, v_percent)
                )

        # Accept the event to prevent it from propagating
        event.accept()

    def restore_scroll_position(self, h_percent, v_percent):
        """Restore scroll position after zoom."""
        h_scroll = self.scroll_area.horizontalScrollBar()
        v_scroll = self.scroll_area.verticalScrollBar()

        if h_scroll.maximum() > 0:
            h_scroll.setValue(int(h_scroll.maximum() * h_percent))
        if v_scroll.maximum() > 0:
            v_scroll.setValue(int(v_scroll.maximum() * v_percent))

    def mousePressEvent(self, event):
        """Close popup on click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.hide()
            self.closed.emit()

    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.closed.emit()
        elif event.key() == Qt.Key.Key_Plus or event.key() == Qt.Key.Key_Equal:
            # Zoom in with + key
            if self.original_pixmap and not self.original_pixmap.isNull():
                new_zoom = min(self.max_zoom, self.zoom_factor + self.zoom_step)
                if new_zoom != self.zoom_factor:
                    self.zoom_factor = new_zoom
                    self.update_image_zoom()
        elif event.key() == Qt.Key.Key_Minus:
            # Zoom out with - key
            if self.original_pixmap and not self.original_pixmap.isNull():
                new_zoom = max(self.min_zoom, self.zoom_factor - self.zoom_step)
                if new_zoom != self.zoom_factor:
                    self.zoom_factor = new_zoom
                    self.update_image_zoom()
        elif event.key() == Qt.Key.Key_0:
            # Reset zoom with 0 key (back to 80% of screen)
            if self.original_pixmap and not self.original_pixmap.isNull():
                self.zoom_factor = 1.0
                self.update_image_zoom()
                # Re-center the scroll area for zoom level 1.0
                screen = QApplication.primaryScreen()
                screen_rect = screen.geometry()
                scroll_width = self.scroll_area.width()
                scroll_height = self.scroll_area.height()
                scroll_x = (screen_rect.width() - scroll_width) // 2
                scroll_y = (screen_rect.height() - scroll_height) // 2
                self.scroll_area.move(scroll_x, scroll_y)
        else:
            super().keyPressEvent(event)


class DraggableImageLabel(QLabel):
    """
    Custom QLabel that supports dragging for panning when zoomed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_scroll_area = None
        self.drag_start_position = None
        self.is_dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_scroll_area(self, scroll_area):
        """Set the parent scroll area for drag calculations."""
        self.parent_scroll_area = scroll_area

    def mousePressEvent(self, event):
        """Handle mouse press for starting drag."""
        if event.button() == Qt.MouseButton.LeftButton and self.parent_scroll_area:
            # Only allow dragging if image is larger than scroll area (i.e., scrollbars are present)
            h_scroll = self.parent_scroll_area.horizontalScrollBar()
            v_scroll = self.parent_scroll_area.verticalScrollBar()

            if h_scroll.maximum() > 0 or v_scroll.maximum() > 0:
                self.drag_start_position = event.position().toPoint()
                self.is_dragging = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
            else:
                super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging."""
        if (
            self.is_dragging
            and self.drag_start_position is not None
            and self.parent_scroll_area
            and event.buttons() == Qt.MouseButton.LeftButton
        ):

            # Calculate drag delta
            delta = event.position().toPoint() - self.drag_start_position

            # Get scroll bars
            h_scroll = self.parent_scroll_area.horizontalScrollBar()
            v_scroll = self.parent_scroll_area.verticalScrollBar()

            # Apply drag to scroll position (negative because we want opposite direction)
            if h_scroll.maximum() > 0:
                new_h_value = h_scroll.value() - delta.x()
                h_scroll.setValue(max(0, min(h_scroll.maximum(), new_h_value)))

            if v_scroll.maximum() > 0:
                new_v_value = v_scroll.value() - delta.y()
                v_scroll.setValue(max(0, min(v_scroll.maximum(), new_v_value)))

            # Update drag start position for next move
            self.drag_start_position = event.position().toPoint()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release for ending drag."""
        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging:
            self.is_dragging = False
            self.drag_start_position = None
            # Change cursor back based on whether scrollbars are present
            if self.parent_scroll_area:
                h_scroll = self.parent_scroll_area.horizontalScrollBar()
                v_scroll = self.parent_scroll_area.verticalScrollBar()
                if h_scroll.maximum() > 0 or v_scroll.maximum() > 0:
                    self.setCursor(Qt.CursorShape.OpenHandCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class ThumbnailWidget(QWidget):
    """
    Custom widget for thumbnails with dynamic resizing capability and duplicate indicator.
    """

    clicked = QtCore.pyqtSignal(str)  # Signal emitted with image path when clicked
    duplicate_clicked = QtCore.pyqtSignal(str)  # Signal emitted when duplicate indicator is clicked
    context_menu_requested = QtCore.pyqtSignal(str, object)  # Signal for context menu

    def __init__(self, image_path: str, parent=None, duplicate_count=0):
        super().__init__(parent)
        self.image_path = image_path
        self.duplicate_count = duplicate_count
        self.base_size = 120  # Base thumbnail size
        self.current_size = self.base_size
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._loaded = False
        self.duplicate_paths = []  # Will be populated by parent

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Container widget for image and overlay
        self.image_container = QWidget()
        self.image_container.setFixedSize(self.current_size, self.current_size)

        # Image label
        self.image_label = QLabel(self.image_container)
        self.image_label.setScaledContents(False)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setFixedSize(self.current_size, self.current_size)

        # Style with duplicate indicator color
        border_color = "#ff9800" if duplicate_count > 0 else "#666"
        hover_color = "#ff5722" if duplicate_count > 0 else "#0d7377"
        self.image_label.setStyleSheet(
            f"""
            QLabel {{
                background-color: transparent;
                border: 2px solid {border_color};
                border-radius: 4px;
            }}
            QLabel:hover {{
                border: 2px solid {hover_color};
            }}
        """
        )

        # Duplicate count label (overlay)
        self.duplicate_label = QLabel(self.image_container)
        self.duplicate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if duplicate_count > 0:
            self.duplicate_label.setText(f"{duplicate_count + 1}")  # +1 to include the original
            self.duplicate_label.setStyleSheet(
                """
                QLabel {
                    background-color: #ff5722;
                    color: white;
                    border-radius: 12px;
                    font-weight: bold;
                    font-size: 12px;
                    padding: 2px 6px;
                }
            """
            )
            self.duplicate_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self.duplicate_label.setToolTip(
                f"Click to see all {duplicate_count + 1} instances of this image"
            )
            # Position in top-right corner
            self.duplicate_label.setFixedSize(24, 24)
            self.duplicate_label.move(self.current_size - 30, 5)
            self.duplicate_label.raise_()  # Ensure it's on top
        else:
            self.duplicate_label.hide()

        # Add container to main layout
        layout.addWidget(self.image_container)

        # Set widget size
        self.setFixedSize(self.current_size, self.current_size)

        # Show loading placeholder
        self.image_label.setText("Loading...")
        self.image_label.setStyleSheet(
            self.image_label.styleSheet()
            + """
            QLabel {
                color: #666;
                font-size: 10px;
            }
        """
        )

        # Schedule loading after widget is shown
        QTimer.singleShot(10, self.load_thumbnail)

        # Install event filter on duplicate label
        if duplicate_count > 0:
            self.duplicate_label.installEventFilter(self)

    def set_thumbnail_size(self, size: int):
        """Set the thumbnail size and reload the image."""
        self.current_size = size
        self.setFixedSize(size, size)
        self.image_container.setFixedSize(size, size)
        self.image_label.setFixedSize(size, size)

        # Reposition duplicate label
        if self.duplicate_count > 0:
            self.duplicate_label.move(size - 30, 5)

        self.load_thumbnail()

    def load_thumbnail(self):
        """Load the thumbnail image."""
        import logging

        if self._loaded:
            return

        try:
            # Check if file exists
            if not os.path.exists(self.image_path):
                logging.warning(f"Thumbnail file not found: {self.image_path}")
                self.image_label.setText("Not Found")
                self._loaded = True
                return

            # Load and scale the image
            pixmap = QPixmap(self.image_path)
            if pixmap.isNull():
                logging.error(f"Failed to load image: {self.image_path}")
                self.image_label.setText("Error")
                self._loaded = True
                return

            # Scale the pixmap to fit the thumbnail size
            scaled_pixmap = pixmap.scaled(
                self.current_size - 4,  # Account for border
                self.current_size - 4,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            self.image_label.setPixmap(scaled_pixmap)
            self._loaded = True

            # Clear the loading text
            self.image_label.setText("")

            # Update tooltip
            if self.duplicate_count > 0:
                self.setToolTip(
                    f"This image has {self.duplicate_count} duplicate{'s' if self.duplicate_count > 1 else ''}"
                )

            logging.debug(f"Thumbnail loaded successfully: {self.image_path}")

        except Exception as e:
            logging.error(f"Error loading thumbnail for {self.image_path}: {e}")
            self.image_label.setText("Error")
            self._loaded = True

    def set_loaded_pixmap(self, pixmap):
        """Set the loaded pixmap from the worker thread."""
        if self._loaded:
            return

        try:
            # The pixmap is already scaled by the worker thread
            self.image_label.setPixmap(pixmap)
            self._loaded = True

            # Clear the loading text
            self.image_label.setText("")

            # Update tooltip
            if self.duplicate_count > 0:
                self.setToolTip(
                    f"This image has {self.duplicate_count} duplicate{'s' if self.duplicate_count > 1 else ''}"
                )
        except Exception as e:
            print(f"Error setting thumbnail pixmap: {e}")
            self.image_label.setText("Error")
            self._loaded = True

    def set_duplicate_paths(self, paths):
        """Set the list of all duplicate paths for this image."""
        self.duplicate_paths = paths

    def mousePressEvent(self, event):
        """Handle mouse press events."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if click is on the duplicate label
            if self.duplicate_count > 0 and self.duplicate_label.geometry().contains(event.pos()):
                self.duplicate_clicked.emit(self.image_path)
            else:
                self.clicked.emit(self.image_path)
        elif event.button() == Qt.MouseButton.RightButton:
            # Emit signal for context menu
            self.context_menu_requested.emit(self.image_path, event.globalPosition().toPoint())

    def eventFilter(self, obj, event):
        """Event filter to handle clicks on duplicate label."""
        if obj == self.duplicate_label and event.type() == QtCore.QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self.duplicate_clicked.emit(self.image_path)
                return True
        return super().eventFilter(obj, event)


class SplashScreen(QSplashScreen):
    """
    Splash Screen Class that displays the logo centered on screen.
    """

    def __init__(self) -> None:
        super().__init__()
        # Set window flags to ensure splash is always on top
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.SplashScreen
        )

        # Get logo path from updated function
        logo_path = get_app_logo()

        # Load the logo as QPixmap (full size 351x351)
        logo_pixmap = QPixmap(logo_path)

        # Set window icon
        self.setWindowIcon(QIcon(logo_path))

        # Display the full logo (351x351) as splash screen
        self.setPixmap(logo_pixmap)

        # Center the splash screen on screen
        screen = QApplication.primaryScreen()
        screen_rect = screen.geometry()
        splash_size = logo_pixmap.size()
        x = (screen_rect.width() - splash_size.width()) // 2
        y = (screen_rect.height() - splash_size.height()) // 2
        self.move(x, y)
