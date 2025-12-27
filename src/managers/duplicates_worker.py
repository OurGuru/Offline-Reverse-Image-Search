"""
Worker thread for loading duplicates in the background.
Prevents UI freezing when loading large numbers of duplicates.
"""

import logging

from PyQt6.QtCore import QThread, pyqtSignal


class DuplicateLoadWorker(QThread):
    """Worker thread for loading duplicates from database."""

    progress = pyqtSignal(str)  # Progress message
    finished = pyqtSignal(list)  # List of DuplicateGroup objects
    error = pyqtSignal(str)  # Error message

    def __init__(self, database_manager):
        super().__init__()
        self.database_manager = database_manager
        self._is_running = True

    def run(self):
        """Load duplicates in background thread."""
        try:
            self.progress.emit("Loading duplicates from database...")

            # Try to get duplicates with metadata if available
            if hasattr(self.database_manager, "get_duplicates_with_metadata"):
                duplicates_dict = self.database_manager.get_duplicates_with_metadata()
                use_metadata = True
            else:
                # Fallback to old method
                duplicates_dict = self.database_manager.get_duplicates()
                use_metadata = False

            if not self._is_running:
                return

            self.progress.emit(f"Processing {len(duplicates_dict)} duplicate groups...")

            # Import here to avoid circular import
            from src.managers.duplicates_manager import DuplicateGroup

            # Convert to DuplicateGroup objects
            duplicate_groups = []

            if use_metadata:
                # With metadata - process dictionary format
                for i, (hash_value, file_tuples) in enumerate(duplicates_dict.items()):
                    if not self._is_running:
                        break

                    if len(file_tuples) > 1:  # Only include actual duplicates
                        # Convert tuples to metadata list format
                        metadata_list = []
                        paths = []

                        for item in file_tuples:
                            if isinstance(item, tuple) and len(item) >= 2:
                                # Extract from tuple: (hash, file_path, file_size, last_modified)
                                path = item[1]
                                paths.append(path)
                                meta = {
                                    "hash": item[0],
                                    "path": path,
                                    "size": item[2] if len(item) > 2 else None,
                                    "modified": item[3] if len(item) > 3 else None,
                                }
                                metadata_list.append(meta)
                            else:
                                # Fallback for unexpected format
                                path = str(item)
                                paths.append(path)
                                metadata_list.append({"path": path, "size": None, "modified": None})

                        if len(paths) > 1:
                            # Pass files_data as tuples for proper metadata loading
                            group = DuplicateGroup(str(hash_value), paths, files_data=file_tuples)
                            duplicate_groups.append(group)

                        # Emit progress every 100 groups for large datasets
                        if i % 100 == 0:
                            self.progress.emit(f"Processed {i}/{len(duplicates_dict)} groups...")
            else:
                # Without metadata (old method) - process dictionary format
                for i, (hash_value, paths) in enumerate(duplicates_dict.items()):
                    if not self._is_running:
                        break

                    if len(paths) > 1:  # Only include actual duplicates
                        group = DuplicateGroup(str(hash_value), paths)
                        duplicate_groups.append(group)

                        # Emit progress every 100 groups
                        if i % 100 == 0:
                            self.progress.emit(f"Processed {i}/{len(duplicates_dict)} groups...")

            if self._is_running:
                # Sort by number of duplicates (descending) - groups with most duplicates first
                self.progress.emit("Sorting duplicate groups by count...")
                duplicate_groups.sort(key=lambda g: len(g.file_paths), reverse=True)
                self.progress.emit(f"Loaded {len(duplicate_groups)} duplicate groups")
                self.finished.emit(duplicate_groups)

        except Exception as e:
            logging.error(f"Error loading duplicates: {e}")
            self.error.emit(str(e))

    def stop(self):
        """Stop the worker thread."""
        self._is_running = False
