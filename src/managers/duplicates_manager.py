"""
Duplicates manager for handling duplicate image detection and management.
Provides functionality to find, display, and manage duplicate images in the database.
"""

import logging
import os
from datetime import datetime

import send2trash  # For safe deletion to recycle bin
from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot


class DuplicateGroup:
    """Represents a group of duplicate images with the same hash."""

    def __init__(
        self,
        hash_value: str,
        file_paths: list,
        metadata_list: list[dict] = None,
        files_data: list[tuple] = None,
    ):
        self.hash_value = hash_value

        # Ensure file_paths is a clean list of strings
        if file_paths and isinstance(file_paths[0], tuple):
            # Extract just the file paths from tuples
            self.file_paths = []
            for item in file_paths:
                if isinstance(item, tuple):
                    path = item[1] if len(item) > 1 else item[0]
                else:
                    path = item
                self.file_paths.append(path)
        else:
            self.file_paths = file_paths if isinstance(file_paths, list) else [file_paths]

        self.selected_for_deletion = set()  # Paths marked for deletion
        self.metadata = {}  # Cache for file metadata

        # If files_data provided (from database as tuples), handle that first
        if files_data:
            self._load_metadata_from_tuples(files_data)
        elif metadata_list:
            self._load_metadata_from_list(metadata_list)
        else:
            self._load_metadata()

    def _load_metadata_from_tuples(self, files_data: list[tuple]):
        """Load metadata from database tuples.

        Each tuple is: (hash_value, file_path, file_size, last_modified)
        """
        for item in files_data:
            if isinstance(item, tuple) and len(item) >= 2:
                # Extract from tuple
                path = item[1]
                size = item[2] if len(item) > 2 else None
                modified_timestamp = item[3] if len(item) > 3 else None

                # Ensure size is valid
                if size is None:
                    size = 0

                # Convert timestamp to datetime if available
                modified = None
                if modified_timestamp:
                    try:
                        # Unix timestamp
                        modified = datetime.fromtimestamp(modified_timestamp)
                    except:
                        modified = None

                # Store metadata
                self.metadata[path] = {
                    "size": size,
                    "modified": modified,
                    "exists": True,  # Assume exists for performance
                }

    def _load_metadata_from_list(self, metadata_list: list[dict]):
        """Load metadata from provided list (from database)."""
        for item in metadata_list:
            path = item.get("path", "")
            if path:
                # Don't check file existence during bulk loading - too slow for many files
                # Especially for network paths, this can cause major freezing
                # Trust the database and only check existence when actually needed

                # Use database metadata if available
                size = item.get("size")
                if size is None:
                    size = 0

                modified_timestamp = item.get("modified")

                # Convert timestamp to datetime if available
                modified = None
                if modified_timestamp:
                    try:
                        # Handle both timestamp and ISO string formats
                        if isinstance(modified_timestamp, str):
                            # ISO format string
                            from datetime import datetime as dt

                            modified = dt.fromisoformat(modified_timestamp.replace("Z", "+00:00"))
                        else:
                            # Unix timestamp
                            modified = datetime.fromtimestamp(modified_timestamp)
                    except:
                        modified = None

                # Ensure size is valid
                if size is None:
                    size = 0

                # Assume file exists if it's in the database
                # Actual existence can be checked later if needed for specific operations
                self.metadata[path] = {
                    "size": size,
                    "modified": modified,
                    "exists": True,  # Assume exists for performance
                }

    def _load_metadata(self):
        """Load metadata for all files in the group."""
        for path in self.file_paths:
            try:
                # Normalize path for the current OS
                normalized_path = os.path.normpath(path)

                if os.path.exists(normalized_path):
                    stat = os.stat(normalized_path)
                    self.metadata[path] = {
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime),
                        "exists": True,
                    }
                    logging.debug(f"Loaded metadata for {path}: size={stat.st_size}")
                else:
                    # Try to get size from path if it's stored with size info
                    # Some databases might store paths differently
                    self.metadata[path] = {"size": 0, "modified": None, "exists": False}
                    logging.debug(f"File not found: {path}")
            except Exception as e:
                logging.error(f"Error loading metadata for {path}: {e}")
                self.metadata[path] = {
                    "size": 0,
                    "modified": None,
                    "exists": False,
                    "error": str(e),
                }

    def get_total_size(self) -> int:
        """Get total size of all duplicates in bytes."""
        return sum(meta["size"] for meta in self.metadata.values() if meta["exists"])

    def get_wasted_space(self) -> int:
        """Get wasted space (total size minus size of one copy).

        Since duplicates are identical, we assume they all have the same size.
        If we have size info for at least one file, use that for all.
        Wasted space = (number_of_duplicates - 1) * file_size
        """
        # Get the first non-zero size we can find
        file_size = 0
        for meta in self.metadata.values():
            size = meta.get("size", 0)
            if size > 0:
                file_size = size
                break

        # If no size info available, return 0
        if file_size == 0:
            return 0

        # Calculate wasted space: all duplicates except one
        num_files = len(self.file_paths)
        if num_files > 1:
            return (num_files - 1) * file_size
        return 0

    def get_newest_path(self) -> str | None:
        """Get path of the newest file based on modification date."""
        valid_files = [
            (path, meta["modified"])
            for path, meta in self.metadata.items()
            if meta["exists"] and meta["modified"]
        ]
        if valid_files:
            return max(valid_files, key=lambda x: x[1])[0]
        return None

    def get_largest_path(self) -> str | None:
        """Get path of the largest file."""
        valid_files = [
            (path, meta["size"]) for path, meta in self.metadata.items() if meta["exists"]
        ]
        if valid_files:
            return max(valid_files, key=lambda x: x[1])[0]
        return None

    def get_paths_by_location_priority(self, folder_priorities: list[str]) -> list[str]:
        """
        Sort paths by folder priority.
        Earlier folders in the priority list have higher priority.
        """

        def get_priority(path):
            for i, priority_folder in enumerate(folder_priorities):
                if priority_folder in path:
                    return i
            return len(folder_priorities)  # Lowest priority if not in list

        existing_paths = [p for p in self.file_paths if self.metadata[p]["exists"]]
        return sorted(existing_paths, key=get_priority)


class DuplicateWorker(QThread):
    """Worker thread for performing duplicate operations."""

    progress = pyqtSignal(int, str)  # Progress percentage and message
    finished = pyqtSignal(bool, str)  # Success and message
    file_deleted = pyqtSignal(str)  # Path of deleted file

    def __init__(
        self,
        groups: list[DuplicateGroup],
        operation: str,
        use_recycle_bin: bool = True,
        dry_run: bool = False,
    ):
        super().__init__()
        self.groups = groups
        self.operation = operation
        self.use_recycle_bin = use_recycle_bin
        self.dry_run = dry_run
        self.deleted_files = []
        self._is_running = True

    def run(self):
        """Execute the deletion operation."""
        try:
            total_files = sum(len(group.selected_for_deletion) for group in self.groups)
            if total_files == 0:
                self.finished.emit(False, "No files selected for deletion")
                return

            processed = 0

            for group in self.groups:
                if not self._is_running:
                    break

                for file_path in group.selected_for_deletion:
                    if not self._is_running:
                        break

                    try:
                        if not self.dry_run:
                            if self.use_recycle_bin:
                                send2trash.send2trash(file_path)
                            else:
                                os.remove(file_path)

                        self.deleted_files.append(file_path)
                        self.file_deleted.emit(file_path)

                    except Exception as e:
                        logging.error(f"Error deleting {file_path}: {e}")

                    processed += 1
                    progress_pct = int((processed / total_files) * 100)
                    self.progress.emit(
                        progress_pct, f"Processing {processed}/{total_files} files..."
                    )

            if self._is_running:
                mode = "Would delete" if self.dry_run else "Deleted"
                self.finished.emit(True, f"{mode} {len(self.deleted_files)} files successfully")
            else:
                self.finished.emit(False, "Operation cancelled")

        except Exception as e:
            self.finished.emit(False, f"Error during operation: {str(e)}")

    def stop(self):
        """Stop the worker thread."""
        self._is_running = False


class DuplicatesManager(QObject):
    """
    Manager for handling duplicate image detection and management operations.
    """

    duplicates_updated = pyqtSignal(list)  # List of DuplicateGroup objects
    operation_completed = pyqtSignal(str)  # Success message
    operation_failed = pyqtSignal(str)  # Error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.database_manager = None
        self.duplicate_groups = []
        self.worker = None
        self.worker_thread = None

        if hasattr(parent, "database_manager"):
            self.database_manager = parent.database_manager

    def load_duplicates(self, use_thread=True):
        """Load all duplicate groups from the database.

        Args:
            use_thread: If True, load in background thread. If False, load synchronously.
        """
        if not self.database_manager:
            logging.error("Database manager not available")
            return []

        if use_thread:
            # Load in background thread
            from src.managers.duplicates_worker import DuplicateLoadWorker

            if hasattr(self, "load_worker") and self.load_worker and self.load_worker.isRunning():
                logging.warning("Duplicate loading already in progress")
                return []

            self.load_worker = DuplicateLoadWorker(self.database_manager)
            self.load_worker.progress.connect(lambda msg: logging.info(f"Loading progress: {msg}"))
            self.load_worker.finished.connect(self._on_duplicates_loaded)
            self.load_worker.error.connect(
                lambda msg: self.operation_failed.emit(f"Failed to load duplicates: {msg}")
            )
            self.load_worker.start()
            return []  # Return empty, data will be emitted via signal
        else:
            # Load synchronously
            try:
                # Try to get duplicates with metadata if available
                if hasattr(self.database_manager, "get_duplicates_with_metadata"):
                    duplicates_dict = self.database_manager.get_duplicates_with_metadata()

                    # Convert to DuplicateGroup objects with metadata
                    self.duplicate_groups = []
                    for hash_value, file_tuples in duplicates_dict.items():
                        if len(file_tuples) > 1:  # Only include actual duplicates
                            # Pass the tuples directly to DuplicateGroup
                            paths = []

                            for item in file_tuples:
                                if isinstance(item, tuple) and len(item) >= 2:
                                    # Extract from tuple: (hash, file_path, file_size, last_modified)
                                    path = item[1]
                                    paths.append(path)
                                else:
                                    # Fallback for unexpected format
                                    path = str(item)
                                    paths.append(path)

                            if len(paths) > 1:
                                # Pass files_data as tuples for proper metadata loading
                                group = DuplicateGroup(
                                    str(hash_value), paths, files_data=file_tuples
                                )
                                self.duplicate_groups.append(group)
                else:
                    # Fallback to old method
                    duplicates = self.database_manager.get_duplicates()

                    # Convert to DuplicateGroup objects
                    self.duplicate_groups = []
                    for hash_value, paths in duplicates.items():
                        if len(paths) > 1:  # Only include actual duplicates
                            group = DuplicateGroup(str(hash_value), paths)
                            self.duplicate_groups.append(group)

                # Sort by number of duplicates (descending) - groups with most duplicates first
                self.duplicate_groups.sort(key=lambda g: len(g.file_paths), reverse=True)

                self.duplicates_updated.emit(self.duplicate_groups)
                return self.duplicate_groups

            except Exception as e:
                logging.error(f"Error loading duplicates: {e}")
                self.operation_failed.emit(f"Failed to load duplicates: {str(e)}")
                return []

    def _on_duplicates_loaded(self, duplicate_groups):
        """Handle duplicates loaded from worker thread."""
        self.duplicate_groups = duplicate_groups
        self.duplicates_updated.emit(self.duplicate_groups)

        # Clean up worker
        if hasattr(self, "load_worker"):
            self.load_worker.deleteLater()
            self.load_worker = None

    def get_statistics(self) -> dict:
        """Calculate statistics for all duplicate groups."""
        stats = {
            "total_groups": len(self.duplicate_groups),
            "total_duplicate_files": 0,
            "total_unique_files": 0,
            "total_size": 0,
            "wasted_space": 0,
            "selected_for_deletion": 0,
            "recoverable_space": 0,
        }

        for group in self.duplicate_groups:
            # Trust that files exist if they're in the database
            # Treat all files as existing for stats calculation
            stats["total_duplicate_files"] += len(group.file_paths)
            stats["total_unique_files"] += 1

            # Calculate total size - sum of all file sizes in the group
            total_size = sum(group.metadata.get(p, {}).get("size", 0) for p in group.file_paths)
            stats["total_size"] += total_size

            stats["wasted_space"] += group.get_wasted_space()

            # Calculate recoverable space from selected files
            for path in group.selected_for_deletion:
                if path in group.metadata:
                    stats["selected_for_deletion"] += 1
                    stats["recoverable_space"] += group.metadata.get(path, {}).get("size", 0)

        return stats

    def apply_keep_strategy(self, strategy: str, folder_priorities: list[str] = None) -> int:
        """
        Apply a keep strategy to all duplicate groups.
        Returns the number of files marked for deletion.
        """
        total_marked = 0

        for group in self.duplicate_groups:
            group.selected_for_deletion.clear()
            existing_paths = [p for p in group.file_paths if group.metadata[p]["exists"]]

            if len(existing_paths) <= 1:
                continue  # Nothing to delete if only one file exists

            keep_path = None

            if strategy == "newest":
                keep_path = group.get_newest_path()
            elif strategy == "largest":
                keep_path = group.get_largest_path()
            elif strategy == "location" and folder_priorities:
                sorted_paths = group.get_paths_by_location_priority(folder_priorities)
                if sorted_paths:
                    keep_path = sorted_paths[0]  # Keep the highest priority

            if keep_path:
                # Mark all others for deletion
                for path in existing_paths:
                    if path != keep_path:
                        group.selected_for_deletion.add(path)
                        total_marked += 1

        return total_marked

    def clear_selection(self):
        """Clear all deletion selections."""
        for group in self.duplicate_groups:
            group.selected_for_deletion.clear()

    def delete_selected(self, use_recycle_bin: bool = True, dry_run: bool = False):
        """
        Delete selected duplicate files.

        Args:
            use_recycle_bin: If True, move to recycle bin instead of permanent deletion
            dry_run: If True, simulate deletion without actually deleting files
        """
        if self.worker and self.worker.isRunning():
            logging.warning("Deletion operation already in progress")
            return

        # Create worker thread
        self.worker = DuplicateWorker(self.duplicate_groups, "delete", use_recycle_bin, dry_run)

        # Connect signals
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_operation_finished)
        self.worker.file_deleted.connect(self._on_file_deleted)

        # Start operation
        self.worker.start()

    @pyqtSlot(int, str)
    def _on_progress(self, percentage: int, message: str):
        """Handle progress updates from worker."""
        if hasattr(self.parent, "update_progress"):
            self.parent.update_progress(percentage, message)

    @pyqtSlot(bool, str)
    def _on_operation_finished(self, success: bool, message: str):
        """Handle operation completion."""
        if success:
            self.operation_completed.emit(message)
            # Reload duplicates to reflect changes
            self.load_duplicates()
        else:
            self.operation_failed.emit(message)

        # Clean up worker
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    @pyqtSlot(str)
    def _on_file_deleted(self, file_path: str):
        """Handle individual file deletion."""
        logging.info(f"Deleted: {file_path}")

    def stop_operation(self):
        """Stop any running operation."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()

    def export_report(self, format: str = "text") -> str:
        """
        Export a report of all duplicates.

        Args:
            format: Output format ('text', 'csv', or 'json')

        Returns:
            Formatted report string
        """
        if format == "csv":
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                ["Hash", "File Path", "Size (bytes)", "Modified", "Selected for Deletion"]
            )

            for group in self.duplicate_groups:
                for path in group.file_paths:
                    meta = group.metadata.get(path, {})
                    writer.writerow(
                        [
                            group.hash_value,
                            path,
                            meta.get("size", 0),
                            meta.get("modified", ""),
                            "Yes" if path in group.selected_for_deletion else "No",
                        ]
                    )

            return output.getvalue()

        elif format == "json":
            import json

            data = []
            for group in self.duplicate_groups:
                group_data = {"hash": group.hash_value, "files": []}
                for path in group.file_paths:
                    meta = group.metadata.get(path, {})
                    group_data["files"].append(
                        {
                            "path": path,
                            "size": meta.get("size", 0),
                            "modified": (
                                meta.get("modified").isoformat() if meta.get("modified") else None
                            ),
                            "exists": meta.get("exists", False),
                            "selected_for_deletion": path in group.selected_for_deletion,
                        }
                    )
                data.append(group_data)

            return json.dumps(data, indent=2)

        else:  # Default text format
            lines = []
            stats = self.get_statistics()

            lines.append("=== DUPLICATE REPORT ===")
            lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("")
            lines.append(f"Total Duplicate Groups: {stats['total_groups']}")
            lines.append(f"Total Duplicate Files: {stats['total_duplicate_files']}")
            lines.append(f"Wasted Space: {self._format_size(stats['wasted_space'])}")
            lines.append(f"Selected for Deletion: {stats['selected_for_deletion']} files")
            lines.append(f"Recoverable Space: {self._format_size(stats['recoverable_space'])}")
            lines.append("")
            lines.append("=== DUPLICATE GROUPS ===")
            lines.append("")

            for i, group in enumerate(self.duplicate_groups, 1):
                lines.append(f"Group {i} (Hash: {group.hash_value[:16]}...)")
                lines.append(f"  Wasted Space: {self._format_size(group.get_wasted_space())}")

                for path in group.file_paths:
                    meta = group.metadata.get(path, {})
                    status = "✓" if meta.get("exists") else "✗"
                    selected = "[DELETE]" if path in group.selected_for_deletion else ""
                    size = self._format_size(meta.get("size", 0))
                    lines.append(f"  {status} {path} ({size}) {selected}")
                lines.append("")

            return "\n".join(lines)

    def _format_size(self, size_bytes: int) -> str:
        """Format size in bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"
