"""
Duplicates manager for tkinter-based application.
Simplified version without Qt dependencies.
"""

import logging
import os
from datetime import datetime

import send2trash


class DuplicateGroup:
    """Represents a group of duplicate images with the same hash."""

    def __init__(self, hash_value: str, file_data: list):
        """
        Initialize duplicate group.

        Args:
            hash_value: The hash identifying this group
            file_data: List of tuples (hash, file_path, file_size, last_modified) from database
        """
        self.hash = hash_value
        self.file_paths = []
        self.file_metadata = {}
        self.wasted_space = 0

        # Process file data
        for item in file_data:
            if isinstance(item, tuple):
                # Database entry format: (hash, file_path, file_size, last_modified)
                file_path = item[1] if len(item) > 1 else item[0]
                db_size = item[2] if len(item) > 2 else None
                db_modified = item[3] if len(item) > 3 else None
            else:
                file_path = item
                db_size = None
                db_modified = None

            self.file_paths.append(file_path)

            # Check if file exists
            exists = os.path.exists(file_path)

            # Try to get metadata from filesystem if database values are missing
            if exists and (db_size is None or db_modified is None):
                try:
                    stat = os.stat(file_path)
                    size = stat.st_size
                    modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
                except Exception:
                    size = db_size if db_size is not None else 0
                    modified = db_modified
            else:
                size = db_size if db_size is not None else 0
                modified = db_modified

            self.file_metadata[file_path] = {"size": size, "modified": modified, "exists": exists}

        # Calculate wasted space
        self._calculate_wasted_space()

    def _calculate_wasted_space(self):
        """Calculate the wasted space for this duplicate group."""
        sizes = [
            meta["size"]
            for meta in self.file_metadata.values()
            if meta.get("exists", False) and meta.get("size", 0) > 0
        ]

        if len(sizes) > 1:
            # Wasted space is total size minus one copy
            self.wasted_space = sum(sizes) - max(sizes)
        else:
            self.wasted_space = 0

    def get_newest_file(self) -> str | None:
        """Get the path of the newest file."""
        newest = None
        newest_time = None

        for path, meta in self.file_metadata.items():
            if meta["exists"] and meta["modified"]:
                if not newest_time or meta["modified"] > newest_time:
                    newest_time = meta["modified"]
                    newest = path

        return newest

    def get_largest_file(self) -> str | None:
        """Get the path of the largest file."""
        largest = None
        largest_size = 0

        for path, meta in self.file_metadata.items():
            if meta["exists"] and meta["size"] > largest_size:
                largest_size = meta["size"]
                largest = path

        return largest


class DuplicatesManager:
    """Manager for handling duplicate images in tkinter application."""

    def __init__(self, db_manager):
        """Initialize the duplicates manager."""
        self.db_manager = db_manager
        self.duplicate_groups = []

    def load_duplicates(self):
        """Load all duplicate groups from the database."""
        self.duplicate_groups = []

        try:
            # Get duplicates with metadata from database
            duplicates_dict = self.db_manager.get_duplicates_with_metadata()

            # Convert to DuplicateGroup objects
            for hash_value, file_data in duplicates_dict.items():
                if len(file_data) > 1:  # Only include actual duplicates
                    group = DuplicateGroup(hash_value, file_data)
                    self.duplicate_groups.append(group)

            # Sort by wasted space (largest first)
            self.duplicate_groups.sort(key=lambda g: g.wasted_space, reverse=True)

        except Exception as e:
            logging.error(f"Error loading duplicates: {e}")

    def get_statistics(self) -> dict:
        """Calculate statistics for all duplicate groups."""
        stats = {
            "total_groups": len(self.duplicate_groups),
            "total_files": 0,
            "total_duplicates": 0,  # Extra copies
            "wasted_space": 0,
        }

        for group in self.duplicate_groups:
            accessible_files = sum(
                1 for meta in group.file_metadata.values() if meta.get("exists", False)
            )
            if accessible_files > 0:
                stats["total_files"] += accessible_files
                stats["total_duplicates"] += accessible_files - 1  # Don't count the original
                stats["wasted_space"] += group.wasted_space

        return stats

    def apply_strategy(
        self, strategy: str, folder_priorities: list[str] = None
    ) -> dict[str, list[str]]:
        """
        Apply a keep strategy and return files to delete.

        Returns:
            Dict mapping group hash to list of files to delete
        """
        to_delete = {}

        for group in self.duplicate_groups:
            # Get accessible files
            accessible_files = [
                path for path, meta in group.file_metadata.items() if meta.get("exists", False)
            ]

            if len(accessible_files) <= 1:
                continue  # Nothing to delete

            keep_file = None

            if strategy == "keep_newest":
                keep_file = group.get_newest_file()
            elif strategy == "keep_largest":
                keep_file = group.get_largest_file()
            elif strategy == "keep_by_location" and folder_priorities:
                # Find the first file matching priority folders
                for priority_folder in folder_priorities:
                    for path in accessible_files:
                        if priority_folder in path:
                            keep_file = path
                            break
                    if keep_file:
                        break

                # If no priority match, keep the first one
                if not keep_file and accessible_files:
                    keep_file = accessible_files[0]

            if keep_file:
                # Mark all others for deletion
                files_to_delete = [f for f in accessible_files if f != keep_file]
                if files_to_delete:
                    to_delete[group.hash] = files_to_delete

        return to_delete

    def delete_files(
        self, files_to_delete: list[str], use_recycle_bin: bool = True
    ) -> tuple[int, list[str]]:
        """
        Delete specified files.

        Returns:
            Tuple of (number of successfully deleted files, list of errors)
        """
        deleted_count = 0
        errors = []

        for file_path in files_to_delete:
            try:
                if os.path.exists(file_path):
                    if use_recycle_bin:
                        send2trash.send2trash(file_path)
                    else:
                        os.remove(file_path)
                    deleted_count += 1

                    # Remove from database
                    if self.db_manager:
                        try:
                            self.db_manager.remove_image(file_path)
                        except:
                            pass  # Don't fail if database update fails
            except Exception as e:
                errors.append(f"{file_path}: {str(e)}")

        return deleted_count, errors

    def export_duplicates(self, filename: str):
        """Export duplicate information to a CSV file."""
        import csv

        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Hash", "File Path", "Size (bytes)", "Modified", "Exists"])

            for group in self.duplicate_groups:
                for path in group.file_paths:
                    meta = group.file_metadata.get(path, {})
                    writer.writerow(
                        [
                            group.hash[:16] + "...",
                            path,
                            meta.get("size", 0),
                            meta.get("modified", ""),
                            "Yes" if meta.get("exists", False) else "No",
                        ]
                    )
