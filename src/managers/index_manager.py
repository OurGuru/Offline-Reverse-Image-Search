"""
Image indexing functionality manager for the Offline Reverse Image Search application.

This module handles the indexing of images, creating VP-Tree structures for
efficient similarity searching, and managing hash databases.
"""

import os
import pickle
from multiprocessing import Pool

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from vptree import VPTree

from ..core.constants import (
    DEFAULT_PARALLEL_WORKERS,
    MAX_PARALLEL_WORKERS,
    MIN_PARALLEL_WORKERS,
    SUPPORTED_IMAGE_EXTENSIONS,
)
from ..utils.utils import process_image_batch


class IndexWorker(QObject):
    """
    A worker class that indexes images in the background.
    """

    progress = pyqtSignal(int)
    finished = pyqtSignal()
    status_update = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self, index_manager, directory, vp_tree_path, hash_path, cleanup_non_existing=False
    ):
        super().__init__()
        self.index_manager = index_manager
        self.directory = directory
        self.vp_tree_path = vp_tree_path
        self.hash_path = hash_path
        self.cleanup_non_existing = cleanup_non_existing
        self.is_running = True

    def run(self):
        """Run the indexing process in the background."""
        try:
            self.index_manager.perform_indexing(
                self.directory, self.vp_tree_path, self.hash_path, self, self.cleanup_non_existing
            )
        except Exception as e:
            self.error.emit(f"Indexing error: {str(e)}")
        finally:
            self.finished.emit()

    def stop(self):
        """Stop the indexing process."""
        self.is_running = False


class IndexManager:
    """Manages image indexing operations."""

    def __init__(self, parent):
        """Initialize the IndexManager."""
        self.parent = parent
        self.thread = None
        self.worker = None
        self.is_indexing = False
        self.index_directory = None  # Directory to index
        self.cleanup_non_existing = False  # Whether to clean up non-existing files

    def start_indexing(self):
        """Start the indexing process."""
        if self.is_indexing:
            self.parent.log_message("Indexing is already in progress")
            return

        # Get paths
        vp_tree_path = self.parent.vp_tree_dir.text()
        hash_path = self.parent.hash_dir.text()

        # Use the directory set by the UI, or default to home
        directory = self.index_directory if self.index_directory else os.path.expanduser("~")

        if not os.path.isdir(directory):
            self.parent.log_message(f"Invalid directory: {directory}")
            return

        # Create worker and thread
        self.thread = QThread()
        self.worker = IndexWorker(
            self, directory, vp_tree_path, hash_path, self.cleanup_non_existing
        )
        self.worker.moveToThread(self.thread)

        # Connect signals
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.finished.connect(self.on_indexing_finished)

        self.worker.progress.connect(self.on_progress_update)
        self.worker.status_update.connect(self.on_status_update)
        self.worker.error.connect(self.parent.log_message)

        # Connect to progress dialog if it exists
        if (
            hasattr(self.parent, "indexing_progress_dialog")
            and self.parent.indexing_progress_dialog
        ):
            self.worker.progress.connect(self.parent.indexing_progress_dialog.setValue)
            self.worker.status_update.connect(self.parent.indexing_progress_dialog.setLabelText)

        # Start the thread
        self.is_indexing = True
        self.thread.start()

        self.parent.log_message(f"Started indexing: {directory}")

    def stop_indexing(self):
        """Stop the indexing process."""
        if self.worker:
            self.worker.stop()
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()
        self.is_indexing = False
        self.parent.log_message("Indexing stopped")

    def on_indexing_finished(self):
        """Handle indexing completion."""
        self.is_indexing = False
        self.parent.index_button.setEnabled(True)
        self.parent.stop_index_button.setEnabled(False)
        self.parent.update_total_images_count()
        self.parent.log_message("Indexing completed")

        # Close progress dialog if it exists
        if (
            hasattr(self.parent, "indexing_progress_dialog")
            and self.parent.indexing_progress_dialog
        ):
            self.parent.indexing_progress_dialog.close()
            self.parent.indexing_progress_dialog = None

    def on_progress_update(self, value):
        """Handle progress updates."""
        # Update progress dialog if it exists
        if (
            hasattr(self.parent, "indexing_progress_dialog")
            and self.parent.indexing_progress_dialog
        ):
            self.parent.indexing_progress_dialog.setValue(value)

    def on_status_update(self, message):
        """Handle status updates."""
        # Log the message
        self.parent.log_message(message)
        # Update progress dialog label if it exists
        if (
            hasattr(self.parent, "indexing_progress_dialog")
            and self.parent.indexing_progress_dialog
        ):
            self.parent.indexing_progress_dialog.setLabelText(message)

    def perform_indexing(
        self, directory, vp_tree_path, hash_path, worker, cleanup_non_existing=False
    ):
        """
        Perform the actual indexing operation with optional cleanup of non-existing files.
        """
        # Collect image paths
        image_extensions = SUPPORTED_IMAGE_EXTENSIONS
        image_paths = []

        worker.status_update.emit("Scanning directory for images...")

        for root, dirs, files in os.walk(directory):
            if not worker.is_running:
                worker.status_update.emit("Indexing cancelled")
                return

            for file in files:
                if file.lower().endswith(image_extensions):
                    image_paths.append(os.path.join(root, file))

        if not image_paths:
            worker.status_update.emit("No images found in the selected directory")
            return

        worker.status_update.emit(f"Found {len(image_paths)} images, starting to process...")

        hashes = {}

        # Process images with parallel processing
        num_workers = self.parent.settings.settings.value(
            "parallel_workers", DEFAULT_PARALLEL_WORKERS, type=int
        )
        num_workers = max(MIN_PARALLEL_WORKERS, min(MAX_PARALLEL_WORKERS, num_workers))
        batch_size = max(len(image_paths) // (num_workers * 10), 10)

        # Split into batches
        batches = [image_paths[i : i + batch_size] for i in range(0, len(image_paths), batch_size)]
        total_batches = len(batches)

        processed_count = 0
        failed_count = 0

        # Calculate total images processed so far
        images_processed_so_far = 0

        # Process batches
        with Pool(processes=num_workers) as pool:
            for batch_idx, batch in enumerate(batches):
                if not worker.is_running:
                    worker.status_update.emit("Indexing cancelled")
                    return

                # Calculate images in current batch and end index
                batch_image_count = len(batch)
                images_end = min(images_processed_so_far + batch_image_count, len(image_paths))

                # Update progress
                progress = int((images_processed_so_far / len(image_paths)) * 100)
                worker.progress.emit(progress)

                # More informative status message
                worker.status_update.emit(
                    f"Processing images {images_processed_so_far + 1}-{images_end} of {len(image_paths)} "
                    f"(batch {batch_idx + 1}/{total_batches}, {batch_image_count} images per batch)"
                )

                # Process batch
                batch_results = pool.apply(process_image_batch, (batch,))

                # Process results
                for image_path, hash_value, error_msg in batch_results:
                    if error_msg:
                        failed_count += 1
                    else:
                        # Update hashes dictionary
                        l = hashes.get(hash_value, [])
                        l.append(image_path)
                        hashes[hash_value] = l
                        processed_count += 1

                # Update images processed counter
                images_processed_so_far += batch_image_count

        # Load existing hashes if file exists
        existing_hashes = {}
        if os.path.isfile(hash_path):
            worker.status_update.emit("Loading existing hash database...")
            try:
                with open(hash_path, "rb") as f:
                    existing_hashes = pickle.load(f)
                    # If not cleaning up, just update with existing hashes
                    if not cleanup_non_existing:
                        hashes.update(existing_hashes)
            except Exception as e:
                worker.status_update.emit(f"Error loading existing hashes: {str(e)}")

        # Perform cleanup if requested
        if cleanup_non_existing and existing_hashes:
            worker.status_update.emit("Cleaning up non-existing files...")
            cleaned_count = 0
            kept_count = 0
            inaccessible_count = 0

            # Normalize the directory path for comparison
            index_dir = os.path.normpath(directory)

            # Check each existing hash entry
            for hash_value, paths in existing_hashes.items():
                # Ensure paths is a list
                if not isinstance(paths, list):
                    paths = [paths]

                valid_paths = []
                for path in paths:
                    # Normalize the path for comparison
                    norm_path = os.path.normpath(path)

                    # Check if this path is under the indexed directory
                    if norm_path.startswith(index_dir + os.sep) or norm_path == index_dir:
                        # This file is in the indexed directory, check if it exists
                        if os.path.exists(path):
                            # File exists, keep it
                            valid_paths.append(path)
                            kept_count += 1
                        else:
                            # Check if it's inaccessible (parent directory exists but file doesn't)
                            parent_dir = os.path.dirname(path)
                            if os.path.exists(parent_dir):
                                try:
                                    # Try to access the file to distinguish between non-existent and inaccessible
                                    os.stat(path)
                                    # If we get here, file exists (shouldn't happen)
                                    valid_paths.append(path)
                                    kept_count += 1
                                except FileNotFoundError:
                                    # File truly doesn't exist, remove it
                                    cleaned_count += 1
                                except (PermissionError, OSError):
                                    # File is inaccessible (permission denied), keep it
                                    valid_paths.append(path)
                                    inaccessible_count += 1
                                    kept_count += 1
                            else:
                                # Parent directory doesn't exist, file is gone
                                cleaned_count += 1
                    else:
                        # File is outside the indexed directory, keep it
                        valid_paths.append(path)
                        kept_count += 1

                # Update the hash entry with valid paths
                if valid_paths:
                    # Check if this hash already exists in new hashes
                    if hash_value in hashes:
                        # Merge the paths
                        existing = hashes[hash_value]
                        if isinstance(existing, list):
                            hashes[hash_value] = list(set(existing + valid_paths))
                        else:
                            hashes[hash_value] = list(set([existing] + valid_paths))
                    else:
                        hashes[hash_value] = valid_paths if len(valid_paths) > 1 else valid_paths[0]

            # Report cleanup statistics
            if cleaned_count > 0 or inaccessible_count > 0:
                worker.status_update.emit(
                    f"Cleanup complete: Removed {cleaned_count} non-existing entries, "
                    f"kept {kept_count} valid entries ({inaccessible_count} inaccessible but retained)"
                )
            else:
                worker.status_update.emit("Cleanup complete: All existing entries are valid")
        elif cleanup_non_existing:
            worker.status_update.emit("No existing database to clean up")

        # Build VP-Tree
        worker.status_update.emit("Building VP-Tree index structure...")
        points = list(hashes.keys())

        # Use hamming distance function from parent
        tree = VPTree(points, self.parent.hamming)

        # Save to disk
        worker.status_update.emit("Saving index to disk...")

        try:
            with open(vp_tree_path, "wb") as f:
                pickle.dump(tree, f)
            with open(hash_path, "wb") as f:
                pickle.dump(hashes, f)
        except Exception as e:
            worker.error.emit(f"Error saving index files: {str(e)}")
            return

        # Report results with more detail
        if failed_count > 0:
            worker.status_update.emit(
                f"Indexing complete: {processed_count} images successfully indexed, {failed_count} failed "
                f"(Total unique hashes: {len(hashes)})"
            )
        else:
            worker.status_update.emit(
                f"Indexing complete: {processed_count} images successfully indexed "
                f"(Total unique hashes: {len(hashes)})"
            )

        worker.progress.emit(100)
