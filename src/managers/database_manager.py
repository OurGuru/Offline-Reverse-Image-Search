"""
Database manager for handling SQLite operations for image hashes.

Part of the hybrid approach: SQLite for hashes, pickle for VP-Tree.
This module provides a unified interface for both SQLite and pickle-based
storage, enabling seamless migration between storage formats.
"""

import logging
import os
import pickle
import sqlite3
from contextlib import contextmanager


class DatabaseManager:
    """Manages SQLite database operations for image hashes."""

    def __init__(self, db_path: str = "image_hashes.db"):
        """Initialize the database manager."""
        self.db_path = db_path
        self.pickle_path = "Hashing.pickle"  # Fallback to pickle if SQLite not available
        self.use_sqlite = os.path.exists(db_path)
        # Only initialize if using SQLite, pickle doesn't need init
        if self.use_sqlite:
            self._init_database()

    def _init_database(self):
        """Initialize the database if using SQLite."""
        if self.use_sqlite:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Enable optimizations
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA synchronous = NORMAL")
                cursor.execute("PRAGMA cache_size = -64000")
                cursor.execute("PRAGMA temp_store = MEMORY")

                # Create tables if they don't exist
                # Using TEXT for hash_value to handle large Python integers
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS images (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        hash_value TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        file_size INTEGER,
                        last_modified REAL,
                        indexed_at REAL DEFAULT (julianday('now')),
                        UNIQUE(hash_value, file_path)
                    )
                """
                )

                cursor.execute("CREATE INDEX IF NOT EXISTS idx_hash ON images(hash_value)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_path ON images(file_path)")

                conn.commit()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def is_migrated(self) -> bool:
        """Check if the database has been migrated to SQLite."""
        return self.use_sqlite and os.path.exists(self.db_path)

    def load_hashes(self) -> dict[int, str | list[str]]:
        """Load all hashes from either SQLite or pickle."""
        if self.use_sqlite:
            return self._load_from_sqlite()
        else:
            return self._load_from_pickle()

    def _load_from_sqlite(self) -> dict[int, str | list[str]]:
        """Load hashes from SQLite database."""
        hashes = {}

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT hash_value, file_path 
                FROM images 
                ORDER BY hash_value
            """
            )

            current_hash = None
            current_paths = []

            for row in cursor.fetchall():
                hash_val = row["hash_value"]
                path = row["file_path"]

                if current_hash != hash_val:
                    if current_hash is not None:
                        # Store previous hash
                        if len(current_paths) == 1:
                            hashes[current_hash] = current_paths[0]
                        else:
                            hashes[current_hash] = current_paths

                    current_hash = hash_val
                    current_paths = [path]
                else:
                    current_paths.append(path)

            # Don't forget the last hash
            if current_hash is not None:
                if len(current_paths) == 1:
                    hashes[current_hash] = current_paths[0]
                else:
                    hashes[current_hash] = current_paths

        return hashes

    def _load_from_pickle(self) -> dict[int, str | list[str]]:
        """Load hashes from pickle file."""
        if os.path.exists(self.pickle_path):
            try:
                with open(self.pickle_path, "rb") as f:
                    return pickle.load(f)
            except Exception as e:
                logging.error(f"Error loading pickle file: {e}")
                return {}
        return {}

    def save_hashes(self, hashes: dict[int, str | list[str]]):
        """Save hashes to either SQLite or pickle."""
        if self.use_sqlite:
            self._save_to_sqlite(hashes)
        else:
            self._save_to_pickle(hashes)

    def _save_to_sqlite(self, hashes: dict[int, str | list[str]]):
        """Save hashes to SQLite database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Clear existing data
            cursor.execute("DELETE FROM images")

            # Insert new data
            batch = []
            for hash_value, paths in hashes.items():
                if not isinstance(paths, list):
                    paths = [paths]

                for path in paths:
                    file_size = None
                    last_modified = None

                    if os.path.exists(path):
                        try:
                            stat = os.stat(path)
                            file_size = stat.st_size
                            last_modified = stat.st_mtime
                        except OSError:
                            pass

                    # Convert hash_value to string to handle large integers
                    batch.append((str(hash_value), path, file_size, last_modified))

            cursor.executemany(
                "INSERT OR IGNORE INTO images (hash_value, file_path, file_size, last_modified) VALUES (?, ?, ?, ?)",
                batch,
            )

            conn.commit()

    def _save_to_pickle(self, hashes: dict[int, str | list[str]]):
        """Save hashes to pickle file."""
        with open(self.pickle_path, "wb") as f:
            pickle.dump(hashes, f, protocol=pickle.HIGHEST_PROTOCOL)

    def add_image(self, hash_value: int, file_path: str):
        """Add a single image to the database."""
        if self.use_sqlite:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                file_size = None
                last_modified = None

                if os.path.exists(file_path):
                    try:
                        stat = os.stat(file_path)
                        file_size = stat.st_size
                        last_modified = stat.st_mtime
                    except OSError:
                        pass

                cursor.execute(
                    "INSERT OR IGNORE INTO images (hash_value, file_path, file_size, last_modified) VALUES (?, ?, ?, ?)",
                    (str(hash_value), file_path, file_size, last_modified),
                )

                conn.commit()
        else:
            # For pickle, we need to load, modify, and save
            hashes = self.load_hashes()

            if hash_value in hashes:
                if isinstance(hashes[hash_value], list):
                    if file_path not in hashes[hash_value]:
                        hashes[hash_value].append(file_path)
                else:
                    if hashes[hash_value] != file_path:
                        hashes[hash_value] = [hashes[hash_value], file_path]
            else:
                hashes[hash_value] = file_path

            self.save_hashes(hashes)

    def remove_non_existing(self, base_path: str) -> tuple[int, int]:
        """Remove entries for non-existing files within a base path."""
        removed = 0
        kept = 0

        if self.use_sqlite:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get all paths within the base path
                cursor.execute(
                    "SELECT id, file_path FROM images WHERE file_path LIKE ?", (f"{base_path}%",)
                )

                to_remove = []
                for row in cursor.fetchall():
                    if not os.path.exists(row["file_path"]):
                        to_remove.append(row["id"])
                        removed += 1
                    else:
                        kept += 1

                # Remove non-existing entries
                if to_remove:
                    placeholders = ",".join("?" * len(to_remove))
                    cursor.execute(f"DELETE FROM images WHERE id IN ({placeholders})", to_remove)
                    conn.commit()
        else:
            # For pickle, load and filter
            hashes = self.load_hashes()
            new_hashes = {}

            import os.path

            base_path = os.path.normpath(base_path)

            for hash_value, paths in hashes.items():
                if not isinstance(paths, list):
                    paths = [paths]

                valid_paths = []
                for path in paths:
                    norm_path = os.path.normpath(path)

                    if norm_path.startswith(base_path + os.sep) or norm_path == base_path:
                        if os.path.exists(path):
                            valid_paths.append(path)
                            kept += 1
                        else:
                            removed += 1
                    else:
                        valid_paths.append(path)
                        kept += 1

                if valid_paths:
                    if len(valid_paths) == 1:
                        new_hashes[hash_value] = valid_paths[0]
                    else:
                        new_hashes[hash_value] = valid_paths

            self.save_hashes(new_hashes)

        return removed, kept

    def get_duplicates(self) -> list[tuple[int, list[str]]]:
        """Get all duplicate hashes (hashes with multiple paths)."""
        duplicates = []

        if self.use_sqlite:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT hash_value, GROUP_CONCAT(file_path, '||') as paths
                    FROM images
                    GROUP BY hash_value
                    HAVING COUNT(*) > 1
                """
                )

                for row in cursor.fetchall():
                    paths = row["paths"].split("||")
                    duplicates.append((row["hash_value"], paths))
        else:
            hashes = self.load_hashes()
            for hash_value, paths in hashes.items():
                if isinstance(paths, list) and len(paths) > 1:
                    duplicates.append((hash_value, paths))

        return duplicates

    def get_duplicates_with_metadata(self):
        """Get all duplicate hashes with file metadata.
        Returns a dictionary mapping hash values to lists of tuples (hash, file_path, file_size, last_modified).
        """
        duplicates = {}

        if self.use_sqlite:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # First get all duplicate hash values
                cursor.execute(
                    """
                    SELECT hash_value
                    FROM images
                    GROUP BY hash_value
                    HAVING COUNT(*) > 1
                """
                )

                duplicate_hashes = [row["hash_value"] for row in cursor.fetchall()]

                # For each duplicate hash, get all files with metadata
                for hash_value in duplicate_hashes:
                    cursor.execute(
                        """
                        SELECT hash_value, file_path, file_size, last_modified
                        FROM images
                        WHERE hash_value = ?
                    """,
                        (hash_value,),
                    )

                    files = []
                    for row in cursor.fetchall():
                        # Return as tuple format for compatibility with DuplicateGroup
                        files.append(
                            (
                                row["hash_value"],
                                row["file_path"],
                                row["file_size"],
                                row["last_modified"],
                            )
                        )

                    if len(files) > 1:  # Double check it's a duplicate
                        duplicates[hash_value] = files
        else:
            # For pickle, we don't have metadata stored, so just return paths
            hashes = self.load_hashes()
            for hash_value, paths in hashes.items():
                if isinstance(paths, list) and len(paths) > 1:
                    files = [(str(hash_value), p, 0, None) for p in paths]
                    duplicates[str(hash_value)] = files

        return duplicates

    def get_statistics(self) -> dict[str, int]:
        """Get database statistics."""
        stats = {"total_hashes": 0, "total_paths": 0, "duplicates": 0, "unique_images": 0}

        if self.use_sqlite:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(DISTINCT hash_value) FROM images")
                stats["total_hashes"] = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM images")
                stats["total_paths"] = cursor.fetchone()[0]

                cursor.execute(
                    """
                    SELECT COUNT(*) FROM (
                        SELECT hash_value FROM images
                        GROUP BY hash_value
                        HAVING COUNT(*) > 1
                    )
                """
                )
                stats["duplicates"] = cursor.fetchone()[0]

                stats["unique_images"] = stats["total_hashes"]
        else:
            hashes = self.load_hashes()
            stats["total_hashes"] = len(hashes)

            for paths in hashes.values():
                if isinstance(paths, list):
                    stats["total_paths"] += len(paths)
                    if len(paths) > 1:
                        stats["duplicates"] += 1
                else:
                    stats["total_paths"] += 1

            stats["unique_images"] = stats["total_hashes"]

        return stats
