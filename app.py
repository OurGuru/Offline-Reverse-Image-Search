import logging
from re import findall
import sys
import os
from pickle import loads as pickleloads
from pickle import dump as pickledump
from pickle import dumps as pickledumps
from collections import deque
import base64
from io import BytesIO
from datetime import datetime
import subprocess
import threading
from typing import List, Dict, Optional, Tuple, Any, Union
from PyQt6 import QtCore, QtGui
from PyQt6.QtWidgets import QFileDialog, QApplication, QMainWindow, QWidget, QGridLayout, QTabWidget, QPushButton, QLabel, QLineEdit, QSpinBox, QCheckBox, QSplashScreen, QTextEdit, QProgressBar
from PyQt6.QtGui import QPixmap, QIcon
from requests import get as requestsGet, exceptions as RequestExceptions
from chime import success as SuccessSound
from chime import info as ErrorSound
from PIL import Image
from numpy import array as nparray
from vptree import VPTree

# Constants
DEFAULT_HASH_SIZE = 8
DEFAULT_SEARCH_RANGE = 6
MIN_SEARCH_RANGE = 1
MAX_SEARCH_RANGE = 100
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 15
THREAD_WAIT_TIMEOUT_MS = 5000
SPLASH_SCREEN_DURATION_MS = 1200
SUPPORTED_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif')
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
    # Load the image file and convert it to grayscale. This simplifies the
    # subsequent calculations and reduces the amount of data we need to process.
    gray = gray.convert('L')

    # Resize the grayscale image, adding a single column (width) so we can compute
    # the horizontal gradient. The horizontal gradient is the difference in
    # intensity between adjacent pixels in the horizontal direction.
    resized = gray.resize((hash_size + 1, hash_size))

    # Convert the resized image to a numpy array. This allows us to perform
    # efficient element-wise operations on the image data.
    resized = nparray(resized)

    # Compute the (relative) horizontal gradient between adjacent column pixels.
    # This gives us a binary matrix where True indicates that the pixel to the
    # right is brighter than the current pixel, and False indicates the opposite.
    diff = resized[:, 1:] > resized[:, :-1]

    # Convert the difference image to a hash. We do this by flattening the binary
    # matrix into a 1D array, enumerating over it, and for each True value (i.e.,
    # each '1' bit in the hash), calculating 2 raised to the power of its index.
    # The resulting hash is the sum of these values.
    return sum([2 ** i for (i, v) in enumerate(diff.flatten()) if v])

def convert_hash(h: Union[int, float]) -> int:
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
        return int(nparray(h, dtype="float64"))
    except ValueError:
        raise ValueError(ErrorMessages.INVALID_HASH_CONVERSION)

class Worker(QtCore.QObject):
    """
    A worker object for running a reverse image search engine.

    Attributes
    ----------
    progress : QtCore.pyqtSignal
        A signal that emits an integer value indicating the progress of the search.
    finished : QtCore.pyqtSignal
        A signal that emits when the search is finished.
    current_updated : QtCore.pyqtSignal
        A signal that emits when the current image is updated.
    """
    def __init__(self, images_found: List[str], file_path: str, photo_main: QLabel,
                 photo_viewer: QLabel, next_button: QPushButton, previous_button: QPushButton,
                 open_image_button: QPushButton, label_result: QLabel, label_current: QLabel,
                 set_image: Any, append_colored_text: Any, display_queue: deque,
                 current: str, settings: QtCore.QSettings, images_lock: threading.Lock,
                 queue_lock: threading.Lock, current_lock: threading.Lock) -> None:
        super().__init__()
        self.images_found = images_found
        self.file_path = file_path
        self.photo_main = photo_main
        self.photo_viewer = photo_viewer
        self.next_button = next_button
        self.previous_button = previous_button
        self.open_image_button = open_image_button
        self.label_result = label_result
        self.label_current = label_current
        self.set_image = set_image
        self.append_colored_text = append_colored_text
        self.display_queue = display_queue
        self.current = current
        self.settings = settings
        # Thread safety locks
        self.images_lock = images_lock
        self.queue_lock = queue_lock
        self.current_lock = current_lock

    progress = QtCore.pyqtSignal(int)
    finished = QtCore.pyqtSignal()
    current_updated = QtCore.pyqtSignal(str)

    def run(self) -> None:
        """
        Run the reverse image search engine and emit the finished signal when complete.
        """
        # window.theEngine()

        # self.finished.emit()
        # Use lock to safely clear images_found
        with self.images_lock:
            self.images_found.clear()

        #check if the VP-Tree and Hashing files exist
        if not self.settings.value('VPTree') or not self.settings.value('Hashing'):
            self.append_colored_text(ErrorMessages.INDEX_NOT_FOUND, QtGui.QColor("red"))
            ErrorSound()
            self.photo_main.setText(ErrorMessages.ERROR_TEXT)
            return

        vptree_path = self.settings.value('VPTree')
        hashing_path = self.settings.value('Hashing')

        #check if the VP-Tree and Hashing files exist
        if not os.path.exists(vptree_path) or not os.path.exists(hashing_path):
            self.append_colored_text(ErrorMessages.INDEX_NOT_FOUND, QtGui.QColor("red"))
            ErrorSound()
            self.photo_main.setText(ErrorMessages.ERROR_TEXT)
            return

        #check search_range if it is a valid integer
        try:
            search_range_str = str(self.settings.value('search_range', str(DEFAULT_SEARCH_RANGE)))
            search_range = int(search_range_str)
            if search_range < MIN_SEARCH_RANGE or search_range > MAX_SEARCH_RANGE:
                raise ValueError("Search range out of bounds")
        except (ValueError, TypeError):
            self.append_colored_text(ErrorMessages.SEARCH_RANGE_INVALID.format(MIN_SEARCH_RANGE, MAX_SEARCH_RANGE), QtGui.QColor("red"))
            ErrorSound()
            self.photo_main.setText(ErrorMessages.ERROR_TEXT)
            return

        try:
            # Add security warning for pickle files
            self.append_colored_text(ErrorMessages.PICKLE_SECURITY_WARNING, QtGui.QColor("orange"))
            
            with open(vptree_path, 'rb') as vptree_file:
                vptree = pickleloads(vptree_file.read())
            with open(hashing_path, 'rb') as hashing_file:
                hashes = pickleloads(hashing_file.read())
        except Exception as e:
            self.append_colored_text(ErrorMessages.INDEX_LOAD_FAILED.format(str(e)), QtGui.QColor("red"))
            ErrorSound()
            self.photo_main.setText(ErrorMessages.ERROR_TEXT)
            return
        
        # Check file size before processing
        try:
            file_size = os.path.getsize(self.file_path)
            
            if file_size > MAX_FILE_SIZE_BYTES:
                size_mb = file_size / (1024 * 1024)
                self.append_colored_text(ErrorMessages.SEARCH_IMAGE_TOO_LARGE.format(size_mb, MAX_FILE_SIZE_MB), QtGui.QColor("red"))
                ErrorSound()
                self.photo_main.setText(ErrorMessages.FILE_TOO_LARGE_TEXT)
                return
        except Exception as e:
            self.append_colored_text(ErrorMessages.FILE_SIZE_CHECK_FAILED.format(str(e)), QtGui.QColor("red"))
            ErrorSound()
            self.photo_main.setText(ErrorMessages.ERROR_TEXT)
            return
            
        query_hash = dhash(self.file_path)
        query_hash = convert_hash(query_hash)
        try:
            # Use the validated search_range from above
            results = vptree.get_all_in_range(query_hash, search_range)
        except Exception as e:
            self.append_colored_text(ErrorMessages.SEARCH_FAILED.format(str(e)), QtGui.QColor("red"))
            ErrorSound()
            self.photo_main.setText(ErrorMessages.ERROR_TEXT)
            return

        results = sorted(results)

        for (dist, hsh) in results:
            result_paths = hashes.get(hsh, [])
            for result_path in result_paths:
                with self.images_lock:
                    self.images_found.append(result_path)
        try:
            if os.path.isfile(self.file_path):
                self.photo_main.setPixmap(QPixmap(self.file_path).scaled(self.photo_main.width(), self.photo_main.height(), QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation))
            else:
                self.photo_main.setText(ErrorMessages.IMAGE_FILE_NOT_FOUND_TEXT)
                self.photo_viewer.setText(ErrorMessages.IMAGE_FILE_NOT_FOUND_TEXT)
                self.next_button.setEnabled(False)
                self.previous_button.setEnabled(False)
                self.open_image_button.setEnabled(False)
                ErrorSound()
                return
        except Exception as e:
            self.append_colored_text(ErrorMessages.IMAGE_SET_FAILED.format(str(e)), QtGui.QColor("red"))
            self.photo_viewer.setText(ErrorMessages.NOTHING_FOUND_TEXT)
            self.next_button.setEnabled(False)
            self.previous_button.setEnabled(False)
            self.open_image_button.setEnabled(False)
            return
        with self.images_lock:
            if len(self.images_found) > 1:
                self.next_button.setEnabled(True)
            self.open_image_button.setEnabled(True)
            
            with self.queue_lock:
                self.display_queue.clear()
                self.display_queue.extend(self.images_found)
                
                if self.display_queue:
                    with self.current_lock:
                        self.current = self.display_queue[0]
                    self.label_current.setText(f'Current {self.images_found.index(self.current) + 1}/{len(self.images_found)}')
                    self.set_image(self.current)
            
            self.label_result.setText(f'Total results : {len(self.images_found)}')
            logging.info('Links of found images:')
            for image_link in self.images_found:
                logging.info(image_link)
        logging.info('done0')
        self.finished.emit()


class IndexWorker(QtCore.QObject):
    """
    A worker class that indexes images in the background.

    Attributes
    ----------
    progress : QtCore.pyqtSignal
        A signal that emits the progress of the indexing.
    finished : QtCore.pyqtSignal
        A signal that emits when the indexing is finished.
    """

    progress = QtCore.pyqtSignal(int)
    finished = QtCore.pyqtSignal()

    def run(self) -> None:
        """
        Run the indexing process in the background.
        """
        window.image_indexer()
        self.finished.emit()


def get_app_logo() -> QPixmap:
    """
    Return the application logo.

    Returns
    -------
    QPixmap
        The application logo as a QPixmap object.
    """
    BASE64_PHOTO = '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'
    app_logo = QPixmap()
    app_logo.loadFromData(base64.b64decode(BASE64_PHOTO))
    return app_logo

class SplashScreen(QSplashScreen):
    """
    Splash Screen Class.
    """
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint | QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowIcon(QIcon(get_app_logo()))
        self.setPixmap(get_app_logo())

class MyWindow(QMainWindow):
    """
    Main Window Class.
    """
    def __init__(self) -> None:
        super(MyWindow, self).__init__()
        self.test_file_ext = ''
        self.current = ''
        self.file_path = ''
        self.dir_path = os.getcwd()
        settings_path = os.path.join(self.dir_path, 'settings.ini')
        if not os.path.isfile(settings_path):
            with open(settings_path, 'w', encoding='utf-8') as f:
                vp_tree_path = os.path.join(self.dir_path, 'VPtree.pickle')
                hashing_path = os.path.join(self.dir_path, 'Hashing.pickle')
                # Convert to forward slashes for INI file compatibility
                vp_tree_path = vp_tree_path.replace(os.sep, '/')
                hashing_path = hashing_path.replace(os.sep, '/')
                f.write(f'[General]\nVPTree={vp_tree_path}\nHashing={hashing_path}\nsearch_range=6')
            print('no settings file, created one')
        self.settings = QtCore.QSettings(settings_path, QtCore.QSettings.Format.IniFormat)
        self.images_found = []
        self.display_queue=deque()
        self.is_processing = False  # Flag to prevent multiple simultaneous drops
        # Thread safety locks
        self.images_lock = threading.Lock()
        self.queue_lock = threading.Lock()
        self.current_lock = threading.Lock()
        #Last UI Configs & connect UI buttons to functions
        self.setObjectName("Offline")
        self.setWindowTitle("Offline Reverse Image Search")
        self.resize(900, 900)
        self.setAcceptDrops(True)
        self.central_widget = QWidget(self)
        self.central_widget.setAcceptDrops(True)
        self.central_widget.setObjectName("central_widget")
        self.grid_layout_4 = QGridLayout(self.central_widget)
        self.grid_layout_4.setObjectName("grid_layout_4")
        self.tab_widget = QTabWidget(self.central_widget)
        self.tab_widget.setEnabled(True)
        self.tab_widget.setAcceptDrops(True)
        self.tab_widget.setStyleSheet("")
        self.tab_widget.setObjectName("tabWidget")
        self.tab1 = QWidget()
        self.tab1.setAcceptDrops(True)
        self.tab1.setWhatsThis("")
        self.tab1.setObjectName("tab1")
        self.grid_layout_3 = QGridLayout(self.tab1)
        self.grid_layout_3.setContentsMargins(0, 0, 0, 0)
        self.grid_layout_3.setObjectName("grid_layout_3")
        self.grid_layout = QGridLayout()
        self.grid_layout.setContentsMargins(0, -1, -1, 0)
        self.grid_layout.setSpacing(6)
        self.grid_layout.setObjectName("gridLayout")
        self.image_clear_button = QPushButton("Clear Image",self.tab1)
        self.image_clear_button.setEnabled(True)
        self.image_clear_button.setObjectName("image_clear_button")
        self.grid_layout.addWidget(self.image_clear_button, 3, 1, 1, 1)
        self.next_button = QPushButton("Next",self.tab1)
        self.next_button.setEnabled(False)
        self.next_button.setObjectName("next_button")
        self.grid_layout.addWidget(self.next_button, 2, 1, 1, 1)
        self.label_current = QLabel("Current",self.tab1)
        self.label_current.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.label_current.setObjectName("label_current")
        self.grid_layout.addWidget(self.label_current, 1, 1, 1, 1)
        self.previous_button = QPushButton("Previous",self.tab1)
        self.previous_button.setEnabled(False)
        self.previous_button.setObjectName("previous_button")
        self.grid_layout.addWidget(self.previous_button, 2, 0, 1, 1)
        self.photo_viewer = QLabel(self.tab1)
        self.photo_viewer.setMinimumSize(QtCore.QSize(1, 1))
        self.photo_viewer.setAcceptDrops(True)
        self.photo_viewer.setStyleSheet("QLabel{border: 4px dashed #aba}")
        self.photo_viewer.setText("")
        self.photo_viewer.setScaledContents(False)
        self.photo_viewer.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.photo_viewer.setObjectName("photo_viewer")
        self.grid_layout.addWidget(self.photo_viewer, 0, 1, 1, 1)
        self.open_image_button = QPushButton("Open Directory",self.tab1)
        self.open_image_button.setEnabled(False)
        self.open_image_button.setObjectName("open_image_button")
        self.grid_layout.addWidget(self.open_image_button, 3, 0, 1, 1)
        self.label_result = QLabel("Total Results: ",self.tab1)
        self.label_result.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.label_result.setObjectName("label_result")
        self.grid_layout.addWidget(self.label_result, 1, 0, 1, 1)
        self.photo_main = QLabel(self.tab1)
        self.photo_main.setMinimumSize(QtCore.QSize(1, 1))
        self.photo_main.setAcceptDrops(True)
        self.photo_main.setStyleSheet("QLabel{border: 4px dashed #aba\n}")
        self.photo_main.setText("")
        self.photo_main.setScaledContents(False)
        self.photo_main.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.photo_main.setObjectName("photo_main")
        self.grid_layout.addWidget(self.photo_main, 0, 0, 1, 1)
        self.grid_layout.setRowStretch(0, 1)
        self.grid_layout_3.addLayout(self.grid_layout, 0, 0, 1, 1)
        self.tab_widget.addTab(self.tab1, "Finder")
        self.tab2 = QWidget()
        self.tab2.setObjectName("tab2")
        self.tab3 = QWidget()
        self.tab3.setObjectName("tab3")
        self.save_settings_button = QPushButton("Save Settings",self.tab2)
        self.save_settings_button.setGeometry(QtCore.QRect(680, 50, 181, 71))
        self.save_settings_button.setObjectName("save_settings_button")
        self.tree_dir_label = QLabel("Tree Directory",self.tab2)
        self.tree_dir_label.setGeometry(QtCore.QRect(10, 50, 81, 21))
        self.tree_dir_label.setObjectName("tree_dir_label")
        self.vp_tree_dir = QLineEdit(self.tab2)
        self.vp_tree_dir.setGeometry(QtCore.QRect(100, 50, 381, 22))
        self.vp_tree_dir.setObjectName("VPTreeDir")
        self.hash_dir_label = QLabel("Hash Directory",self.tab2)
        self.hash_dir_label.setGeometry(QtCore.QRect(10, 80, 81, 21))
        self.hash_dir_label.setObjectName("hash_dir_label")
        self.hash_dir = QLineEdit(self.tab2)
        self.hash_dir.setGeometry(QtCore.QRect(100, 80, 381, 22))
        self.hash_dir.setObjectName("hash_dir")
        self.index_dir_label = QLabel("Index Directory",self.tab2)
        self.index_dir_label.setGeometry(QtCore.QRect(10, 210, 81, 21))
        self.index_dir_label.setObjectName("index_dir_label")
        self.select_folder_button = QPushButton("Select Folder",self.tab2)
        self.select_folder_button.setGeometry(QtCore.QRect(10, 230, 75, 23))
        self.select_folder_button.setObjectName("select_folder_button")
        self.index_directory = QLineEdit(self.tab2)
        self.index_directory.setGeometry(QtCore.QRect(100, 210, 381, 22))
        self.index_directory.setObjectName("index_directory")
        self.index_go_button = QPushButton("Go",self.tab2)
        self.index_go_button.setGeometry(QtCore.QRect(180, 310, 75, 23))
        self.index_go_button.setObjectName("index_go_button")
        self.index_status = QLabel(self.tab2)
        self.index_status.setGeometry(QtCore.QRect(140, 240, 631, 51))
        font = QtGui.QFont()
        font.setPointSize(14)
        self.index_status.setFont(font)
        self.index_status.setText("")
        self.index_status.setObjectName("index_status")
        self.progress_bar = QProgressBar(self.tab2)
        self.progress_bar.setGeometry(QtCore.QRect(10, 310, 161, 23))
        self.progress_bar.setProperty("value", 0)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setObjectName("progress_bar")

        self.label = QLabel("Update Index Database",self.tab2)
        self.label.setGeometry(QtCore.QRect(100, 170, 221, 31))
        self.label.setObjectName("label")
        self.play_sound_check = QCheckBox("Sound",self.tab2)
        self.play_sound_check.setGeometry(QtCore.QRect(100, 240, 70, 17))
        self.play_sound_check.setObjectName("play_sound_check")

        self.search_range_label = QLabel("Search Range",self.tab2)
        self.search_range_label.setGeometry(QtCore.QRect(10, 110, 80, 21))
        self.search_range_label.setObjectName("search_range_label")
        self.search_range = QSpinBox(self.tab2)
        self.search_range.setGeometry(QtCore.QRect(100, 110, 60, 22))
        self.search_range.setFixedSize(60, 22)
        self.search_range.setObjectName("search_range")
        self.default_range_value_label = QLabel(f"Default: {DEFAULT_SEARCH_RANGE}",self.tab2)
        self.default_range_value_label.setGeometry(QtCore.QRect(180, 110, 210, 21))
        self.default_range_value_label.setObjectName("default_range_value_label")
        self.on_top_check = QCheckBox("Always On Top",self.tab2)
        self.on_top_check.setGeometry(QtCore.QRect(680, 155, 100, 17))
        self.on_top_check.setObjectName("OnTopCheck")
        self.tab_widget.addTab(self.tab2, "Settings - Index")
        self.grid_layout_4.addWidget(self.tab_widget, 0, 0, 1, 1)
        self.setCentralWidget(self.central_widget)
        self.tab_widget.setCurrentIndex(0)
        QtCore.QMetaObject.connectSlotsByName(self)
        self.connect_signals()
        self.validate_and_load_settings()
        self.grid_layout_5 = QGridLayout(self.tab3)
        self.grid_layout_5.setObjectName("grid_layout_5")
        self.log_box = QTextEdit(self.tab3)
        self.grid_layout_5.addWidget(self.log_box, 2, 0, 1, 3)  # Change column span to 3
        self.tab_widget.addTab(self.tab3, "Log")
        self.grid_layout_4.addWidget(self.tab_widget, 0, 0, 1, 1)
        self.grid_layout_5.setColumnStretch(0, 1)
        self.grid_layout_5.setRowStretch(2, 1)
        self.log_box.setReadOnly(True)
        self.log_box_append("Welcome to the Offline Reverse Image Search Tool!")
        self.setCentralWidget(self.central_widget)
        self.setWindowIcon(QIcon(get_app_logo()))

    def validate_and_load_settings(self) -> None:
        """
        Validate and load settings with proper error handling.
        """
        # Validate VP-Tree path
        vp_tree_path = self.settings.value('VPTree', '')
        if vp_tree_path:
            self.vp_tree_dir.setText(vp_tree_path)
        else:
            default_path = os.path.join(self.dir_path, 'VPtree.pickle')
            self.vp_tree_dir.setText(default_path)
            self.settings.setValue('VPTree', default_path)
            self.log_box_append("VP-Tree path not found in settings, using default")
            
        # Validate Hashing path
        hashing_path = self.settings.value('Hashing', '')
        if hashing_path:
            self.hash_dir.setText(hashing_path)
        else:
            default_path = os.path.join(self.dir_path, 'Hashing.pickle')
            self.hash_dir.setText(default_path)
            self.settings.setValue('Hashing', default_path)
            self.log_box_append("Hashing path not found in settings, using default")
            
        # Validate search range
        try:
            search_range = self.settings.value('search_range', str(DEFAULT_SEARCH_RANGE))
            search_range_int = int(search_range)
            # Validate range bounds
            if search_range_int < MIN_SEARCH_RANGE:
                search_range_int = MIN_SEARCH_RANGE
                self.log_box_append(f"Search range too low, setting to minimum ({MIN_SEARCH_RANGE})")
            elif search_range_int > MAX_SEARCH_RANGE:
                search_range_int = MAX_SEARCH_RANGE
                self.log_box_append(f"Search range too high, setting to maximum ({MAX_SEARCH_RANGE})")
            self.search_range.setValue(search_range_int)
            self.search_range.setMinimum(MIN_SEARCH_RANGE)
            self.search_range.setMaximum(MAX_SEARCH_RANGE)
        except (ValueError, TypeError):
            # If conversion fails, use default
            self.search_range.setValue(DEFAULT_SEARCH_RANGE)
            self.search_range.setMinimum(MIN_SEARCH_RANGE)
            self.search_range.setMaximum(MAX_SEARCH_RANGE)
            self.settings.setValue('search_range', DEFAULT_SEARCH_RANGE)
            self.log_box_append(f"Invalid search range in settings, using default ({DEFAULT_SEARCH_RANGE})")

    def connect_signals(self) -> None:
        """
        Connect signals to their respective slots.
        """
        self.next_button.clicked.connect(self.next)
        self.previous_button.clicked.connect(self.previous)
        self.open_image_button.clicked.connect(self.open_directory)
        self.select_folder_button.clicked.connect(self.select_folder_to_index)
        self.index_go_button.clicked.connect(self.index_starter)
        self.save_settings_button.clicked.connect(self.save_settings)
        self.on_top_check.clicked.connect(self.on_top_checker)
        self.image_clear_button.clicked.connect(self.clear_image)

    def log_box_append(self, line: str) -> None:
        """
        Append text to the log box.

        Parameters
        ----------
        line : str
            The text to append to the log box.
        """
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        self.log_box.append(f"[{current_time}] {line}")

    @staticmethod
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

    def append_colored_text(self, text: str, color: QtGui.QColor) -> None:
        """
        Append colored text to the log box.

        Parameters
        ----------
        text : str
            The text to append.
        color : QtGui.QColor
            The color to use for the text.
        """
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        cursor = self.log_box.textCursor()
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        char_format = cursor.charFormat()
        char_format.setForeground(QtGui.QBrush(color))
        cursor.setCharFormat(char_format)
        cursor.insertText(f"[{current_time}] {text}")
        cursor.insertBlock()

    def on_top_checker(self) -> None:
        """
        Toggle the window's always-on-top state.
        """
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.show()

    def update_progress_bar(self, value: int) -> None:
        """
        Update the progress bar.

        Parameters
        ----------
        value : int
            The progress value (0-100).
        """
        self.progress_bar.setValue(value)

    def save_settings(self) -> None:
        """
        Save the settings to the settings file with validation.
        """
        # Validate paths before saving
        vp_tree_path = self.vp_tree_dir.text().strip()
        hashing_path = self.hash_dir.text().strip()
        
        if not vp_tree_path:
            self.append_colored_text(ErrorMessages.VP_TREE_PATH_EMPTY, QtGui.QColor("red"))
            return
            
        if not hashing_path:
            self.append_colored_text(ErrorMessages.HASHING_PATH_EMPTY, QtGui.QColor("red"))
            return
            
        # Validate that paths have proper extensions
        if not vp_tree_path.endswith('.pickle'):
            self.append_colored_text(ErrorMessages.VP_TREE_PATH_WARNING, QtGui.QColor("orange"))
            
        if not hashing_path.endswith('.pickle'):
            self.append_colored_text(ErrorMessages.HASHING_PATH_WARNING, QtGui.QColor("orange"))
        
        # Save validated settings
        self.settings.setValue('VPTree', vp_tree_path)
        self.settings.setValue('Hashing', hashing_path)
        self.settings.setValue('search_range', self.search_range.value())
        
        self.log_box_append("Settings saved successfully")
        SuccessSound()

    def index_starter(self) -> None:
        """
        Create a worker thread to run the image indexer.
        """
        #Create a QThread object
        self.thread = QtCore.QThread()
        #Create a worker object
        self.worker = IndexWorker()
        #Move worker to the thread
        self.worker.moveToThread(self.thread)
        #: Connect signals and slots
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.progress.connect(self.update_progress_bar)
        #Start the thread
        self.thread.start()

    def select_folder_to_index(self) -> None:
        """
        Open a dialog to select folder for indexing.
        """
        dialog = QFileDialog.getExistingDirectory(self, "Select Directory")
        if dialog:
            self.index_directory.setText(dialog)

    def image_indexer(self) -> None:
        """
        Index all images in a folder and create a VP-Tree.
        """
        # Grab the paths to the input images and initialize the dictionary of hashes
        image_extensions = SUPPORTED_IMAGE_EXTENSIONS
        image_paths = []
        self.index_status.setText("Count Images...")

        for root, dirs, files in os.walk(self.index_directory.text()):
            for file in files:
                if file.lower().endswith(image_extensions):
                    image_paths.append(os.path.join(root, file))
        hashes = {}
        # Loop over the image paths

        self.index_go_button.setEnabled(False)
        self.select_folder_button.setEnabled(False)
        
        # Track successful and failed images for accurate progress
        processed_count = 0
        failed_count = 0

        for (i, image_path) in enumerate(image_paths):
            try:
                # Load the input image
                self.index_status.setText(f"processing image {i+1}/{len(image_paths)}")
                if len(image_paths) > 0:
                    self.worker.progress.emit(((i+1)/len(image_paths))*100)
                
                # Check file size before processing (100MB limit)
                file_size = os.path.getsize(image_path)
                
                if file_size > MAX_FILE_SIZE_BYTES:
                    size_mb = file_size / (1024 * 1024)
                    logging.warning("Skipping large file: %s (%.2f MB)", image_path, size_mb)
                    self.append_colored_text(ErrorMessages.FILE_TOO_LARGE.format(image_path, size_mb, MAX_FILE_SIZE_MB), QtGui.QColor("orange"))
                    continue
                
                # Compute the hash for the image and convert it
                h = dhash(image_path)
                h = convert_hash(h)
                # Update the hashes dictionary
                l = hashes.get(h, [])
                l.append(image_path)
                hashes[h] = l
                processed_count += 1
            except FileNotFoundError:
                logging.error("File not found: %s", image_path, exc_info=True)
                self.append_colored_text(ErrorMessages.FILE_NOT_FOUND_PROCESSING.format(image_path), QtGui.QColor("red"))
                failed_count += 1
            except Exception as e:
                logging.error("Error processing image: %s", image_path, exc_info=True)
                self.append_colored_text(ErrorMessages.IMAGE_PROCESSING_FAILED.format(image_path, str(e)), QtGui.QColor("red"))
                failed_count += 1

        if not hashes:
            self.index_status.setText("No Images found in folder")
            self.log_box_append("No Images found in folder")
            self.worker.progress.emit(0)
            self.index_go_button.setEnabled(True)
            self.select_folder_button.setEnabled(True)
            SuccessSound()
            return
        # Load & add existing hashes/dirs
        if os.path.isfile(self.hash_dir.text()):
            self.append_colored_text(ErrorMessages.PICKLE_SECURITY_WARNING_EXISTING, QtGui.QColor("orange"))
            with open(self.hash_dir.text(), "rb") as hash_file:
                hashes.update(pickleloads(hash_file.read()))
        else:
            self.log_box_append("Hashes file not found. Creating new one")
            with open(self.hash_dir.text(), "wb") as hash_file:
                pickledump(hashes, hash_file)
        # build the VP-Tree
        self.index_status.setText(ErrorMessages.INFO_BUILDING_VP_TREE)
        points = list(hashes.keys())
        tree = VPTree(points, self.hamming)
        # serialize the VP-Tree to disk
        self.index_status.setText(ErrorMessages.INFO_SERIALIZING_VP_TREE)
        with open(self.vp_tree_dir.text(), 'wb') as vp_tree_file:
            vp_tree_file.write(pickledumps(tree))
        with open(self.hash_dir.text(), 'wb') as hashes_file:
            hashes_file.write(pickledumps(hashes))
        # Display accurate results summary
        total_attempted = processed_count + failed_count
        if failed_count > 0:
            self.log_box_append(f"{processed_count} Images Successfully Indexed, {failed_count} Failed (out of {total_attempted} total)")
            self.append_colored_text(ErrorMessages.PROCESSING_FAILURES_WARNING.format(failed_count), QtGui.QColor("orange"))
        else:
            self.log_box_append(f"{processed_count} Images Successfully Indexed")
        
        self.index_status.setText(f'Finished - {processed_count} indexed, {failed_count} failed')
        if self.play_sound_check.isChecked():
            SuccessSound()
        self.index_go_button.setEnabled(True)
        self.select_folder_button.setEnabled(True)
        self.worker.progress.emit(0)
        self.worker.finished.emit()

    def worker_thread(self) -> None:
        """
        Create a worker thread to run the image search.
        """
        # If a thread is already running, stop it
        if hasattr(self, 'thread') and self.thread is not None:
            try:
                if self.thread.isRunning():
                    # Request the thread to stop and wait for it
                    self.thread.requestInterruption()
                    self.thread.quit()
                    if not self.thread.wait(THREAD_WAIT_TIMEOUT_MS):  # Wait up to 5 seconds
                        self.thread.terminate()  # Force terminate if it doesn't stop
                        self.thread.wait()
            except RuntimeError:
                # The thread was already deleted, so we can ignore this error
                pass
            finally:
                # Clean up old worker and thread references
                if hasattr(self, 'worker'):
                    self.worker = None
                self.thread = None

        #Create a QThread object
        self.thread = QtCore.QThread()
        #Create a worker object
        self.worker = Worker(
            self.images_found, self.file_path, self.photo_main,
            self.photo_viewer, self.next_button, self.previous_button,
            self.open_image_button, self.label_result, self.label_current,
            self.set_image, self.append_colored_text, self.display_queue,
            self.current, self.settings, self.images_lock,
            self.queue_lock, self.current_lock
        )
        #Move worker to the thread
        self.worker.moveToThread(self.thread)
        #Connect signals and slots
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        # Clean up references when thread is done
        self.thread.finished.connect(lambda: setattr(self, 'thread', None))
        self.worker.finished.connect(lambda: setattr(self, 'worker', None))
        # Reset processing flag when worker finishes
        self.worker.finished.connect(lambda: setattr(self, 'is_processing', False))
        #Start the thread
        self.thread.start()

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        """
        Accept the drag event if it has an image.

        Parameters
        ----------
        event : QtGui.QDragEnterEvent
            The drag enter event.
        """
        if event.mimeData().hasImage:
            event.accept()
        else:
            event.ignore()

    def open_directory(self) -> None:
        """
        Open the directory of the current image in the file explorer.
        """
        with self.current_lock:
            current_path = self.current
            
        if not current_path:
            self.append_colored_text(ErrorMessages.NO_IMAGE_FOUND, QtGui.QColor("red"))
            ErrorSound()
            return

        # Get the directory containing the current image
        if os.path.isfile(current_path):
            directory = os.path.dirname(current_path)
            
            # Open the directory in the file explorer based on the OS
            if sys.platform.startswith('win'):
                subprocess.Popen(["explorer", directory])
            elif sys.platform.startswith('darwin'):
                subprocess.Popen(["open", directory])
            else:
                subprocess.Popen(["xdg-open", directory])
        else:
            self.append_colored_text(ErrorMessages.INVALID_FILE_PATH, QtGui.QColor("red"))
            ErrorSound()

    def previous(self) -> None:
        """
        Display the previous image in the queue.
        """
        with self.queue_lock:
            self.display_queue.rotate(1)
            with self.current_lock:
                self.current = self.display_queue[0]
            
            with self.images_lock:
                current_index = self.images_found.index(self.current)
                total_images = len(self.images_found)
                
            self.label_current.setText(f'Current {current_index + 1}/{total_images}')
            self.set_image(self.current)
            
            if current_index == 0:
                self.previous_button.setEnabled(False)
            elif not self.next_button.isEnabled() and current_index != total_images:
                self.next_button.setEnabled(True)

    def next(self) -> None:
        """
        Display the next image in the queue.
        """
        with self.queue_lock:
            self.display_queue.rotate(-1)
            with self.current_lock:
                self.current = self.display_queue[0]
            
            with self.images_lock:
                current_index = self.images_found.index(self.current)
                total_images = len(self.images_found)
                
            self.label_current.setText(f'Current {current_index + 1}/{total_images}')
            self.set_image(self.current)
            
            if current_index + 1 == total_images:
                self.next_button.setEnabled(False)
            elif not self.previous_button.isEnabled() and current_index != 0:
                self.previous_button.setEnabled(True)

    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        """
        Accept the drag move event.

        Parameters
        ----------
        event : QtGui.QDragMoveEvent
            The drag move event.
        """
        if event.mimeData().hasUrls():
            event.setDropAction(QtCore.Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def clear_image(self) -> None:
        """
        Clear the image and reset the UI.
        """
        self.photo_viewer.clear()
        self.photo_main.clear()
        self.photo_viewer.setText(ErrorMessages.PLACE_NEW_IMAGE_TEXT)
        self.label_result.setText('')
        self.label_current.setText('')
        self.next_button.setEnabled(False)
        self.previous_button.setEnabled(False)
        self.open_image_button.setEnabled(False)
        if self.test_file_ext:
            test_file_path = os.path.join(self.dir_path, f'testfile.{self.test_file_ext}')
            if os.path.isfile(test_file_path):
                os.remove(test_file_path)

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        """
        Handle the drop event.

        Parameters
        ----------
        event : QtGui.QDropEvent
            The drop event.
        """
        # Check if already processing to prevent race conditions
        if self.is_processing:
            self.append_colored_text(ErrorMessages.ALREADY_PROCESSING, QtGui.QColor("orange"))
            event.ignore()
            return
        
        # Set processing flag
        self.is_processing = True
        
        print('resetting image.')
        print('current file path:',self.current)
        self.clear_image()
        if event.mimeData().html():
            url = findall('src="(http.*?\\..+?)"', event.mimeData().html())[0]
            print('url:',url)

            try:
                # Download the image file from the URL
                response = requestsGet(url, timeout=REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()  # Raise an exception for bad status codes
                image_data = BytesIO(response.content)

                # Open the image file using Pillow to get the file format
                image = Image.open(image_data)
                self.test_file_ext = image.format.lower()

                # Save the image file with the correct file extension
                file_path = os.path.join(self.dir_path, f"testfile.{self.test_file_ext}")
                # Save the image to disk
                image.save(file_path)
                # Set the file path as an instance variable
                self.file_path = file_path
                event.accept()
                logging.info('File path set as instance variable: %s', self.file_path)
                self.worker_thread()
            except RequestExceptions.Timeout:
                self.photo_viewer.setText(ErrorMessages.DOWNLOAD_TIMEOUT_TEXT)
                self.append_colored_text(ErrorMessages.DOWNLOAD_TIMEOUT, QtGui.QColor("red"))
                ErrorSound()
                event.ignore()
                self.is_processing = False  # Reset processing flag
                return
            except RequestExceptions.ConnectionError:
                self.photo_viewer.setText(ErrorMessages.CONNECTION_ERROR_TEXT)
                self.append_colored_text(ErrorMessages.CONNECTION_ERROR, QtGui.QColor("red"))
                ErrorSound()
                event.ignore()
                self.is_processing = False  # Reset processing flag
                return
            except RequestExceptions.HTTPError as e:
                self.photo_viewer.setText(f'HTTP error: {e}')
                self.append_colored_text(ErrorMessages.HTTP_ERROR.format(e), QtGui.QColor("red"))
                ErrorSound()
                event.ignore()
                self.is_processing = False  # Reset processing flag
                return
            except Exception as e:
                self.photo_viewer.setText(ErrorMessages.DOWNLOAD_FAILED_TEXT)
                self.append_colored_text(ErrorMessages.DOWNLOAD_FAILED.format(str(e)), QtGui.QColor("red"))
                ErrorSound()
                event.ignore()
                self.is_processing = False  # Reset processing flag
                return
        try:
            url = event.mimeData().urls()[0].toLocalFile()
        except IndexError:
            self.photo_viewer.setText(ErrorMessages.NO_FILE_OR_IMAGE_FOUND_TEXT)
            ErrorSound()
            event.ignore()
            self.append_colored_text(ErrorMessages.NO_FILE_OR_IMAGE_FOUND, QtGui.QColor("red"))
            self.is_processing = False  # Reset processing flag
            return

        if url:
            self.file_path = url
            if self.file_path.lower().endswith(SUPPORTED_IMAGE_EXTENSIONS):
                event.accept()
                self.worker_thread()
            else:
                self.photo_viewer.setText(ErrorMessages.FILE_FORMAT_NOT_SUPPORTED_TEXT)
                logging.warning('Mime data:\n%s', event.mimeData().text())
                ErrorSound()
                event.ignore()
                self.append_colored_text(ErrorMessages.FILE_FORMAT_NOT_SUPPORTED, QtGui.QColor("red"))
                self.is_processing = False  # Reset processing flag
        else:
            self.photo_viewer.setText(ErrorMessages.NO_FILE_OR_IMAGE_FOUND_TEXT)
            ErrorSound()
            event.ignore()
            self.append_colored_text(ErrorMessages.NO_FILE_OR_IMAGE_FOUND, QtGui.QColor("red"))
            self.is_processing = False  # Reset processing flag

    def set_image(self, path: str) -> None:
        """
        Set the image to the photo viewer.

        Parameters
        ----------
        path : str
            The path to the image file.
        """
        if path and os.path.isfile(path):
            self._current_image_path = path
            pixmap = QPixmap(path).scaled(
                self.photo_viewer.width(),
                self.photo_viewer.height(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            self.photo_viewer.setPixmap(pixmap)
        else:
            self.append_colored_text(ErrorMessages.IMAGE_FILE_NOT_FOUND, QtGui.QColor("red"))
            self.photo_viewer.setText(ErrorMessages.IMAGE_FILE_NOT_FOUND_TEXT)
            ErrorSound()

    def get_test_file_ext(self) -> str:
        """
        Return the file extension of the test file.

        Returns
        -------
        str
            The file extension of the test file.
        """
        return self.test_file_ext


if __name__ == "__main__":

    app = QApplication(sys.argv)
    splash = SplashScreen()
    splash.show()
    window = MyWindow()
    window.show()
    QtCore.QTimer.singleShot(SPLASH_SCREEN_DURATION_MS, splash.close)
    app.processEvents()
    exit_code = app.exec()

    if window.get_test_file_ext():
        test_file_path = os.path.join(window.dir_path, f'testfile.{window.test_file_ext}')
        try:
            os.remove(test_file_path)
        except FileNotFoundError:
            logging.error("File not found: %s", test_file_path, exc_info=True)
        except PermissionError:
            logging.error("Permission denied: %s", test_file_path, exc_info=True)
        except Exception as e:
            logging.error("Error deleting file: %s", test_file_path, exc_info=True)
            logging.error("Error: %s", str(e))
    sys.exit(exit_code)
