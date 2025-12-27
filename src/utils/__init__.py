"""
Utility modules for the Offline Reverse Image Search application.
"""

from .file_handler import DragDropWidget, FileHandler
from .utils import *

__all__ = [
    # From utils
    "supported_formats",
    "get_crc32",
    "scale_pixmap_to_label",
    "get_image_hash",
    "create_pixmap_async",
    "get_file_details_async",
    "scale_cv2_image",
    "normalize_features",
    "calculate_similarity",
    "hamming_distance",
    "cosine_similarity",
    "compare_color_histograms",
    "compare_images",
    "get_detailed_similarity",
    "read_image_rgb",
    "extract_features",
    "get_app_logo",
    "process_image_file",
    "FileDetailsResult",
    # From file_handler
    "FileHandler",
    "DragDropWidget",
]
