"""
Utility functions for the Offline Reverse Image Search application.
"""

import os

import numpy as np
from PIL import Image

from ..core.constants import (
    DEFAULT_HASH_SIZE,
    MAX_FILE_SIZE_BYTES,
    MAX_FILE_SIZE_MB,
    ErrorMessages,
)


def dhash(image: str, hash_size: int = DEFAULT_HASH_SIZE) -> int:
    """
    Compute the difference hash (dhash) of the input image.

    Parameters
    ----------
    image : str
        The path to the input image file.
    hash_size : int, optional
        The desired hash size (default is 8).

    Returns
    -------
    int
        The dhash value of the input image.

    Raises
    ------
    ValueError
        If the image file cannot be opened.
    """
    # Check if the input image file exists and can be opened. If not, raise an error.
    try:
        gray = Image.open(image)
    except Exception as e:
        raise ValueError(ErrorMessages.FAILED_TO_OPEN_IMAGE.format(str(e)))

    # Load the image file and convert it to grayscale
    gray = gray.convert("L")

    # Resize the grayscale image, adding a single column (width) so we can compute
    # the horizontal gradient
    resized = gray.resize((hash_size + 1, hash_size))

    # Convert the resized image to a numpy array
    resized = np.array(resized)

    # Compute the (relative) horizontal gradient between adjacent column pixels
    diff = resized[:, 1:] > resized[:, :-1]

    # Convert the difference image to a hash
    return sum([2**i for (i, v) in enumerate(diff.flatten()) if v])


def convert_hash(h: int | float) -> int:
    """
    Convert a hash to NumPy's 64-bit float and then back to Python's built-in int.

    Parameters
    ----------
    h : Union[int, float]
        The hash to be converted.

    Returns
    -------
    int
        The converted hash as a Python built-in int.

    Raises
    ------
    ValueError
        If the input is invalid for hash conversion.
    """
    try:
        return int(np.array(h, dtype="float64"))
    except ValueError:
        raise ValueError(ErrorMessages.INVALID_HASH_CONVERSION)


def process_image_batch(image_paths: list[str]) -> list[tuple[str, int | None, str | None]]:
    """
    Process a batch of images and compute their hashes.

    Parameters
    ----------
    image_paths : List[str]
        List of image paths to process.

    Returns
    -------
    List[Tuple[str, Optional[int], Optional[str]]]
        List of tuples containing (image_path, hash, error_message).
    """
    results = []
    for image_path in image_paths:
        try:
            # Check file size before processing
            file_size = os.path.getsize(image_path)

            if file_size > MAX_FILE_SIZE_BYTES:
                size_mb = file_size / (1024 * 1024)
                error_msg = ErrorMessages.FILE_TOO_LARGE.format(
                    image_path, size_mb, MAX_FILE_SIZE_MB
                )
                results.append((image_path, None, error_msg))
                continue

            # Compute the hash for the image
            h = dhash(image_path)
            h = convert_hash(h)
            results.append((image_path, h, None))

        except FileNotFoundError:
            error_msg = ErrorMessages.FILE_NOT_FOUND_PROCESSING.format(image_path)
            results.append((image_path, None, error_msg))
        except Exception as e:
            error_msg = ErrorMessages.IMAGE_PROCESSING_FAILED.format(image_path, str(e))
            results.append((image_path, None, error_msg))

    return results


def hamming(a: int, b: int) -> int:
    """
    Compute the Hamming distance between two integers.

    Parameters
    ----------
    a : int
        First integer.
    b : int
        Second integer.

    Returns
    -------
    int
        The Hamming distance between a and b.
    """
    return bin(int(a) ^ int(b)).count("1")


def get_app_logo():
    """
    Return the path to the application logo.

    Returns
    -------
    str
        The path to the application logo file.
    """
    # Get the path relative to this file (utils.py)
    # utils.py is in src/utils/, so we need to go up two directories
    logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "logo.png")
    # Resolve to absolute path
    logo_path = os.path.abspath(logo_path)
    # Return the path (QIcon can handle the path directly)
    return logo_path


def calculate_parallel_workers() -> tuple[int, int, int]:
    """
    Calculate the default, minimum and maximum parallel workers based on CPU count.

    Returns
    -------
    tuple[int, int, int]
        A tuple containing (default_workers, min_workers, max_workers).
    """
    from multiprocessing import cpu_count

    cpu_cores = cpu_count()
    default_workers = max(1, cpu_cores - 1)
    min_workers = 1
    max_workers = max(1, cpu_cores - 1)

    return default_workers, min_workers, max_workers
