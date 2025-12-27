"""
Image metadata extraction and display functionality for the Offline Reverse Image Search application.
"""

import os
from datetime import datetime
from typing import Any

from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS
from PyQt6.QtWidgets import (
    QDialog,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


class MetadataManager:
    """Manages image metadata extraction and display."""

    def __init__(self, parent):
        self.parent = parent
        self.metadata_button = None

    def setup_metadata_button(self) -> QPushButton:
        """
        Create and configure the metadata button.

        Returns
        -------
        QPushButton
            The configured metadata button.
        """
        self.metadata_button = QPushButton("View Metadata", self.parent.tab1)
        self.metadata_button.setEnabled(False)
        self.metadata_button.setObjectName("metadata_button")
        self.metadata_button.clicked.connect(lambda: self.show_image_metadata())
        return self.metadata_button

    def extract_image_metadata(self, image_path: str) -> dict[str, Any]:
        """
        Extract metadata from an image file including EXIF data.

        Parameters
        ----------
        image_path : str
            Path to the image file.

        Returns
        -------
        Dict[str, Any]
            Dictionary containing extracted metadata.
        """
        metadata = {}

        try:
            # File system metadata
            file_info = os.stat(image_path)
            metadata["File"] = {
                "Name": os.path.basename(image_path),
                "Path": image_path,
                "Size": f"{file_info.st_size:,} bytes",
                "Modified": datetime.fromtimestamp(file_info.st_mtime).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "Created": datetime.fromtimestamp(file_info.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Open image with PIL to extract image metadata
            with Image.open(image_path) as img:
                # Basic image info
                metadata["Image"] = {
                    "Format": img.format,
                    "Mode": img.mode,
                    "Size": f"{img.size[0]} x {img.size[1]} pixels",
                    "Width": img.size[0],
                    "Height": img.size[1],
                }

                # Extract EXIF data
                exifdata = img._getexif()
                if exifdata:
                    exif_dict = {}
                    gps_dict = {}

                    for tag_id, value in exifdata.items():
                        tag = TAGS.get(tag_id, tag_id)

                        # Special handling for GPS data
                        if tag == "GPSInfo":
                            if isinstance(value, dict):
                                for gps_tag_id, gps_value in value.items():
                                    gps_tag = GPSTAGS.get(gps_tag_id, gps_tag_id)
                                    # Convert GPS values to readable format
                                    if isinstance(gps_value, bytes):
                                        try:
                                            gps_dict[gps_tag] = gps_value.decode("utf-8", "ignore")
                                        except:
                                            gps_dict[gps_tag] = str(gps_value)
                                    else:
                                        gps_dict[gps_tag] = str(gps_value)
                            continue

                        # Convert bytes to string
                        if isinstance(value, bytes):
                            try:
                                value = value.decode("utf-8", "ignore")
                            except:
                                value = str(value)

                        exif_dict[tag] = value

                    if exif_dict:
                        metadata["EXIF"] = exif_dict

                    if gps_dict:
                        # Try to convert GPS coordinates to decimal degrees
                        try:
                            if "GPSLatitude" in gps_dict and "GPSLongitude" in gps_dict:
                                lat_ref = gps_dict.get("GPSLatitudeRef", "N")
                                lon_ref = gps_dict.get("GPSLongitudeRef", "E")

                                # Parse latitude
                                lat_str = str(gps_dict["GPSLatitude"])
                                lat_parts = lat_str.strip("()").split(", ")
                                if len(lat_parts) == 3:
                                    lat_deg = float(lat_parts[0])
                                    lat_min = float(lat_parts[1])
                                    lat_sec = float(lat_parts[2])
                                    latitude = lat_deg + lat_min / 60 + lat_sec / 3600
                                    if lat_ref == "S":
                                        latitude = -latitude
                                    gps_dict["Latitude (Decimal)"] = f"{latitude:.6f}"

                                # Parse longitude
                                lon_str = str(gps_dict["GPSLongitude"])
                                lon_parts = lon_str.strip("()").split(", ")
                                if len(lon_parts) == 3:
                                    lon_deg = float(lon_parts[0])
                                    lon_min = float(lon_parts[1])
                                    lon_sec = float(lon_parts[2])
                                    longitude = lon_deg + lon_min / 60 + lon_sec / 3600
                                    if lon_ref == "W":
                                        longitude = -longitude
                                    gps_dict["Longitude (Decimal)"] = f"{longitude:.6f}"
                        except:
                            pass

                        metadata["GPS"] = gps_dict

        except Exception as e:
            metadata["Error"] = str(e)

        return metadata

    def format_exif_value(self, value: Any) -> str:
        """
        Format EXIF values for display.

        Parameters
        ----------
        value : Any
            The EXIF value to format.

        Returns
        -------
        str
            Formatted string representation of the value.
        """
        if isinstance(value, (list, tuple)):
            return ", ".join(str(v) for v in value)
        return str(value)

    def show_image_metadata(self, image_path: str = None) -> None:
        """
        Show metadata for the current or specified image.

        Parameters
        ----------
        image_path : str, optional
            Path to the image file. If None, uses the current main image.
        """
        if image_path is None:
            # Try to get the current image path
            if hasattr(self.parent, "main_image_path") and self.parent.main_image_path:
                image_path = self.parent.main_image_path
            elif hasattr(self.parent, "file_path") and self.parent.file_path:
                image_path = self.parent.file_path
            else:
                QMessageBox.warning(self.parent, "No Image", "No image is currently loaded.")
                return

        if not os.path.exists(image_path):
            QMessageBox.warning(
                self.parent, "File Not Found", f"Image file not found: {image_path}"
            )
            return

        # Extract metadata
        self.parent.update_status_bar("Extracting image metadata...")
        metadata = self.extract_image_metadata(image_path)

        # Create dialog
        dialog = QDialog(self.parent)
        dialog.setWindowTitle(f"Image Metadata - {os.path.basename(image_path)}")
        dialog.resize(800, 600)

        # Create layout
        layout = QVBoxLayout(dialog)

        # Create tab widget for different metadata categories
        tab_widget = QTabWidget()

        # Add tabs for each metadata category
        for category, data in metadata.items():
            if category == "Error":
                QMessageBox.warning(
                    self.parent, "Metadata Error", f"Error reading metadata: {data}"
                )
                continue

            # Create tree widget for this category
            tree = QTreeWidget()
            tree.setHeaderLabels(["Property", "Value"])
            tree.setAlternatingRowColors(True)

            # Add data to tree
            if isinstance(data, dict):
                for key, value in data.items():
                    item = QTreeWidgetItem(tree)
                    item.setText(0, str(key))

                    # Format the value
                    if isinstance(value, dict):
                        item.setText(1, "[Complex Data]")
                        # Add sub-items for nested dict
                        for sub_key, sub_value in value.items():
                            sub_item = QTreeWidgetItem(item)
                            sub_item.setText(0, str(sub_key))
                            sub_item.setText(1, self.format_exif_value(sub_value))
                    else:
                        item.setText(1, self.format_exif_value(value))

            # Add tree to tab
            tab_widget.addTab(tree, category)

        # Expand all items in the first tab
        if tab_widget.count() > 0:
            first_tree = tab_widget.widget(0)
            if isinstance(first_tree, QTreeWidget):
                first_tree.expandAll()

        layout.addWidget(tab_widget)

        # Add close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        # Show dialog
        self.parent.update_status_bar("Metadata extracted successfully")
        dialog.exec()
