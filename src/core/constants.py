"""
Constants and error messages for the Offline Reverse Image Search application.

This module defines all application-wide constants including file size limits,
processing parameters, search thresholds, and error message templates.
"""

import multiprocessing

# File size and processing constants
DEFAULT_HASH_SIZE = 8
DEFAULT_SEARCH_RANGE = 6
MIN_SEARCH_RANGE = 1
MAX_SEARCH_RANGE = 100
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Network and timing constants
REQUEST_TIMEOUT_SECONDS = 15
THREAD_WAIT_TIMEOUT_MS = 5000
SPLASH_SCREEN_DURATION_MS = 1200

# Search and processing constants
DEFAULT_SIMILARITY_THRESHOLD = 10  # Default max hamming distance for results
MIN_SIMILARITY_THRESHOLD = 0
MAX_SIMILARITY_THRESHOLD = 64
# Calculate parallel workers based on CPU count
_CPU_COUNT = multiprocessing.cpu_count()
DEFAULT_PARALLEL_WORKERS = max(1, _CPU_COUNT - 1)  # Default to CPUs - 1
MIN_PARALLEL_WORKERS = 1
MAX_PARALLEL_WORKERS = max(1, _CPU_COUNT - 1)  # Max is CPUs - 1 to leave one for system

# Supported image formats
SUPPORTED_IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".gif",
    ".tiff",
    ".tif",
    ".webp",
    ".ico",
    ".heic",
    ".heif",
    ".jfif",
    ".pjpeg",
    ".pjp",
    ".svg",
    ".avif",
    ".apng",
    ".jpe",
    ".dib",
)


# Error Messages
class ErrorMessages:
    # Index loading errors
    INDEX_NOT_FOUND = "[ERROR] index could not be loaded. VP-Tree or Hashing file not found"
    INDEX_LOAD_FAILED = "[ERROR] Failed to load index: {}"

    # Search errors
    SEARCH_RANGE_INVALID = "[ERROR] search_range is not a valid integer ({}-{})"
    SEARCH_IMAGE_TOO_LARGE = "[ERROR] Search image too large ({:.2f} MB > {} MB)"
    FILE_SIZE_CHECK_FAILED = "[ERROR] Failed to check file size: {}"
    SEARCH_FAILED = "[ERROR] Failed to search index: {}"
    IMAGE_SET_FAILED = "[ERROR] Failed to set image: {}"

    # Path validation errors
    VP_TREE_PATH_EMPTY = "[ERROR] VP-Tree path cannot be empty"
    HASHING_PATH_EMPTY = "[ERROR] Hashing path cannot be empty"

    # File operation errors
    NO_IMAGE_FOUND = "[ERROR] No image found"
    INVALID_FILE_PATH = "[ERROR] Invalid file path"
    FILE_FORMAT_NOT_SUPPORTED = "[ERROR] File format not supported"
    NO_FILE_OR_IMAGE_FOUND = "[ERROR] No file or image found"
    IMAGE_FILE_NOT_FOUND = "[ERROR] Image file not found"

    # Download errors
    DOWNLOAD_TIMEOUT = "[ERROR] Download timeout"
    CONNECTION_ERROR = "[ERROR] Connection error"
    HTTP_ERROR = "[ERROR] HTTP error: {}"
    DOWNLOAD_FAILED = "[ERROR] Failed to download image: {}"

    # Processing errors
    ALREADY_PROCESSING = "[WARNING] Already processing an image, please wait"
    FILE_TOO_LARGE = "Skipping {}: File too large ({:.2f} MB > {} MB)"
    FILE_NOT_FOUND_PROCESSING = "{} Failed: File not found"
    IMAGE_PROCESSING_FAILED = "{} Failed: {}"

    # Warnings
    PICKLE_SECURITY_WARNING = "[WARNING] Loading pickle files. Only use trusted index files as pickle can execute arbitrary code."
    PICKLE_SECURITY_WARNING_EXISTING = "[WARNING] Loading existing pickle index. Only use trusted index files as pickle can execute arbitrary code."
    VP_TREE_PATH_WARNING = "[WARNING] VP-Tree path should end with .pickle"
    HASHING_PATH_WARNING = "[WARNING] Hashing path should end with .pickle"
    PROCESSING_FAILURES_WARNING = "[WARNING] {} images failed to process"

    # Info messages
    INFO_BUILDING_VP_TREE = "[INFO] building VP-Tree..."
    INFO_SERIALIZING_VP_TREE = "[INFO] serializing VP-Tree..."

    # General errors
    FAILED_TO_OPEN_IMAGE = "Failed to open image file: {}"
    INVALID_HASH_CONVERSION = "Invalid input for hash conversion"

    # UI text messages
    ERROR_TEXT = "Error"
    FILE_TOO_LARGE_TEXT = "File too large"
    IMAGE_FILE_NOT_FOUND_TEXT = "Image file not found"
    NOTHING_FOUND_TEXT = "Nothing Found"
    PLACE_NEW_IMAGE_TEXT = "Place New Image"
    NO_FILE_OR_IMAGE_FOUND_TEXT = "No file or image found"
    FILE_FORMAT_NOT_SUPPORTED_TEXT = "File format not supported"
    DOWNLOAD_TIMEOUT_TEXT = "Download timeout - URL took too long to respond"
    CONNECTION_ERROR_TEXT = "Connection error - Could not reach URL"
    DOWNLOAD_FAILED_TEXT = "Failed to download image"

    # Logging messages
    LOGGING_TO_FILE = "[INFO] Logging to file: {}"
    LOGGING_FAILED = "[ERROR] Failed to set up logging: {}"
    BATCH_PROCESSING = "[INFO] Processing batch {} of {}"
