"""
Worker for HTML export with pagination and duplicate grouping.
"""

import os
from datetime import datetime

from PyQt6 import QtCore

from ..utils.html_exporter_paginated import HTMLExporter


class HTMLExportWorker(QtCore.QThread):
    """
    Worker thread for HTML export with pagination and duplicate grouping.
    Handles the export process in a separate thread to keep UI responsive.
    """

    # Signals for progress and completion
    progress = QtCore.pyqtSignal(int, str)  # progress percentage, current file
    finished = QtCore.pyqtSignal(bool, str)  # success, message/error

    def __init__(
        self,
        search_image: str,
        results: list[str],
        output_path: str,
        search_range: int = 6,
        duplicates_info: dict | None = None,
        items_per_page: int = 50,
    ):
        """
        Initialize the HTML export worker.

        Args:
            search_image: Path to the search image
            results: List of result image paths
            output_path: Output path for the HTML file
            search_range: Search range used
            duplicates_info: Dictionary with duplicate information
            items_per_page: Number of items per page in pagination
        """
        super().__init__()
        self.search_image = search_image
        self.results = results
        self.output_path = output_path
        self.search_range = search_range
        self.duplicates_info = duplicates_info
        self.items_per_page = items_per_page
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
        try:
            # Initialize the exporter
            exporter = HTMLExporter(items_per_page=self.items_per_page)

            # Check for cancellation
            if self.is_cancelled():
                self.finished.emit(False, "Export cancelled")
                return

            # Group duplicates first (5%)
            self.progress.emit(5, "Analyzing duplicates...")
            grouped_results, duplicate_groups = exporter.group_duplicates(
                self.results, self.duplicates_info
            )

            # Prepare search data (10%)
            if self.is_cancelled():
                self.finished.emit(False, "Export cancelled")
                return

            self.progress.emit(10, "Processing search image...")
            search_data = {
                "image": self.search_image,
                "thumbnail": exporter.create_thumbnail_base64(self.search_image),
                "info": exporter.get_file_info(self.search_image),
            }

            # Process grouped results with progress updates
            results_data = []
            total_groups = len(grouped_results)

            for i, group in enumerate(grouped_results):
                if self.is_cancelled():
                    self.finished.emit(False, "Export cancelled")
                    return

                # Calculate progress (10% to 85% for processing)
                progress_pct = 10 + int((i / total_groups) * 75)

                if group["type"] == "unique":
                    # Process unique result
                    self.progress.emit(
                        progress_pct, f"Processing {os.path.basename(group['path'])}..."
                    )

                    result_info = {
                        "index": i + 1,
                        "type": "unique",
                        "path": group["path"],
                        "filename": os.path.basename(group["path"]),
                        "directory": os.path.dirname(group["path"]),
                        "thumbnail": exporter.create_thumbnail_base64(group["path"]),
                        "info": exporter.get_file_info(group["path"]),
                    }
                else:
                    # Process duplicate group
                    self.progress.emit(
                        progress_pct, f"Processing duplicate group {group['group_id']}..."
                    )

                    result_info = {
                        "index": i + 1,
                        "type": "duplicate_group",
                        "group_id": group["group_id"],
                        "path": group["path"],
                        "filename": os.path.basename(group["path"]),
                        "directory": os.path.dirname(group["path"]),
                        "thumbnail": exporter.create_thumbnail_base64(group["path"]),
                        "info": exporter.get_file_info(group["path"]),
                        "duplicates": group["duplicates"],
                        "duplicate_count": len(group["duplicates"]),
                    }

                results_data.append(result_info)

            if self.is_cancelled():
                self.finished.emit(False, "Export cancelled")
                return

            # Generate paginated HTML (90%)
            self.progress.emit(90, "Generating paginated HTML...")
            html_content = exporter._generate_paginated_html(
                search_data,
                results_data,
                duplicate_groups,
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

            # Provide summary in the success message
            unique_count = len([r for r in results_data if r["type"] == "unique"])
            duplicate_groups_count = len(duplicate_groups)

            summary = (
                f"Search results exported to: {self.output_path}\n"
                f"Total results: {len(results_data)}, "
                f"Unique: {unique_count}, "
                f"Duplicate groups: {duplicate_groups_count}"
            )

            self.finished.emit(True, summary)

        except Exception as e:
            self.finished.emit(False, f"Error during export: {str(e)}")
