from PyQt6 import QtCore, QtGui
import sys
import os 
from re import findall
from PyQt6.QtWidgets import QFileDialog, QApplication, QMainWindow,QWidget,QGridLayout,QTabWidget, QPushButton,QLabel,QLineEdit,QColumnView,QSpinBox,QCheckBox
from PyQt6.QtGui import QPixmap 
import pickle
import cv2
from collections import deque
from requests import get as requestsGet
from imutils import paths
from chime import success as SuccessSound


def hamming(a, b):
    # compute and return the Hamming distance between the integers
    return bin(int(a) ^ int(b)).count("1")

def dhash(image, hashSize=8):
    # convert the image to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # resize the grayscale image, adding a single column (width) so we
    # can compute the horizontal gradient
    resized = cv2.resize(gray, (hashSize + 1, hashSize))
    # compute the (relative) horizontal gradient between adjacent
    # column pixels
    diff = resized[:, 1:] > resized[:, :-1]
    # convert the difference image to a hash
    return sum([2 ** i for (i, v) in enumerate(diff.flatten()) if v])

def convert_hash(h):
    # convert the hash to NumPy's 64-bit float and then back to
    # Python's built in int
    import numpy as np
    return int(np.array(h, dtype="float64"))

dir_path = (f"{os.path.dirname(os.path.realpath(__file__))}/").replace('\\','/') 
ImagesFound = []
d=deque(ImagesFound)
current = ''
file_path = ''

if os.path.isfile(dir_path+'settings.ini'):
    print('loaded settings')
else:
    with open(dir_path+'settings.ini','w') as f:
        f.write(f'[General]\nVPTree={dir_path}VPtree.pickle\nHashing={dir_path}Hashing.pickle\nSearchRange=10')
    print('no settings file, created one')
settings = QtCore.QSettings(dir_path+'settings.ini',QtCore.QSettings.Format.IniFormat)

class Worker(QtCore.QObject):
    # finished = QtCore.pyqtSignal()
    # progress = QtCore.pyqtSignal(int)
    finished = QtCore.pyqtSignal()

    def run(self):
        #print('start 1')
        window.theEngine()
        #print('done1')
        self.finished.emit()
        #print('done2')


class IndexWorker(QtCore.QObject):
    # finished = QtCore.pyqtSignal()
    # progress = QtCore.pyqtSignal(int)
    finished = QtCore.pyqtSignal()

    def run(self):
        print('start 1')
        window.ImgIndexer()
        print('done1')
        self.finished.emit()
        print('done2')





class MyWindow(QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()
        #self.setAcceptDrops(True) # enable drag n drop
        #Last UI Configs & connect UI buttons to functions
        self.setObjectName("Offline")
        self.resize(900, 900)
        self.setAcceptDrops(True)
        self.centralwidget = QWidget(self)
        self.centralwidget.setAcceptDrops(True)
        self.centralwidget.setObjectName("centralwidget")
        self.gridLayout_4 = QGridLayout(self.centralwidget)
        self.gridLayout_4.setObjectName("gridLayout_4")
        self.tabWidget = QTabWidget(self.centralwidget)
        self.tabWidget.setEnabled(True)
        self.tabWidget.setAcceptDrops(True)
        self.tabWidget.setStyleSheet("")
        self.tabWidget.setObjectName("tabWidget")
        self.tab1 = QWidget()
        self.tab1.setAcceptDrops(True)
        self.tab1.setWhatsThis("")
        self.tab1.setObjectName("tab1")
        self.gridLayout_3 = QGridLayout(self.tab1)
        self.gridLayout_3.setContentsMargins(0, 0, 0, 0)
        self.gridLayout_3.setObjectName("gridLayout_3")
        self.gridLayout = QGridLayout()
        self.gridLayout.setContentsMargins(0, -1, -1, 0)
        self.gridLayout.setSpacing(6)
        self.gridLayout.setObjectName("gridLayout")
        self.btnimgclr = QPushButton(self.tab1)
        self.btnimgclr.setEnabled(True)
        self.btnimgclr.setObjectName("btnimgclr")
        self.gridLayout.addWidget(self.btnimgclr, 3, 1, 1, 1)
        self.btnnxt = QPushButton(self.tab1)
        self.btnnxt.setEnabled(False)
        self.btnnxt.setObjectName("btnnxt")
        self.gridLayout.addWidget(self.btnnxt, 2, 1, 1, 1)
        self.labelcurrent = QLabel(self.tab1)
        self.labelcurrent.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.labelcurrent.setObjectName("labelcurrent")
        self.gridLayout.addWidget(self.labelcurrent, 1, 1, 1, 1)
        self.btnprev = QPushButton(self.tab1)
        self.btnprev.setEnabled(False)
        self.btnprev.setObjectName("btnprev")
        self.gridLayout.addWidget(self.btnprev, 2, 0, 1, 1)
        self.photoViewer = QLabel(self.tab1)
        self.photoViewer.setMinimumSize(QtCore.QSize(1, 1))
        self.photoViewer.setAcceptDrops(True)
        self.photoViewer.setStyleSheet("QLabel{border: 4px dashed #aba}")
        self.photoViewer.setText("")
        self.photoViewer.setScaledContents(False)
        self.photoViewer.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.photoViewer.setObjectName("photoViewer")
        self.gridLayout.addWidget(self.photoViewer, 0, 1, 1, 1)
        self.btnopen = QPushButton(self.tab1)
        self.btnopen.setEnabled(False)
        self.btnopen.setObjectName("btnopen")
        self.gridLayout.addWidget(self.btnopen, 3, 0, 1, 1)
        self.labelresult = QLabel(self.tab1)
        self.labelresult.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.labelresult.setObjectName("labelresult")
        self.gridLayout.addWidget(self.labelresult, 1, 0, 1, 1)
        self.photoMain = QLabel(self.tab1)
        self.photoMain.setMinimumSize(QtCore.QSize(1, 1))
        self.photoMain.setAcceptDrops(True)
        self.photoMain.setStyleSheet("QLabel{border: 4px dashed #aba\n}")
        self.photoMain.setText("")
        self.photoMain.setScaledContents(False)
        self.photoMain.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.photoMain.setObjectName("photoMain")
        self.gridLayout.addWidget(self.photoMain, 0, 0, 1, 1)
        self.gridLayout.setRowStretch(0, 1)
        self.gridLayout_3.addLayout(self.gridLayout, 0, 0, 1, 1)
        self.tabWidget.addTab(self.tab1, "")
        self.tab2 = QWidget()
        self.tab2.setObjectName("tab2")
        self.SaveSettingsbtn = QPushButton(self.tab2)
        self.SaveSettingsbtn.setGeometry(QtCore.QRect(680, 50, 181, 71))
        self.SaveSettingsbtn.setObjectName("SaveSettingsbtn")
        self.label_5 = QLabel(self.tab2)
        self.label_5.setGeometry(QtCore.QRect(10, 50, 81, 21))
        self.label_5.setObjectName("label_5")
        self.VPTreeDir = QLineEdit(self.tab2)
        self.VPTreeDir.setGeometry(QtCore.QRect(100, 50, 381, 22))
        self.VPTreeDir.setObjectName("VPTreeDir")
        self.label_6 = QLabel(self.tab2)
        self.label_6.setGeometry(QtCore.QRect(10, 80, 81, 21))
        self.label_6.setObjectName("label_6")
        self.HashDir = QLineEdit(self.tab2)
        self.HashDir.setGeometry(QtCore.QRect(100, 80, 381, 22))
        self.HashDir.setObjectName("HashDir")
        self.columnView = QColumnView(self.tab2)
        self.columnView.setGeometry(QtCore.QRect(1000, 430, 256, 192))
        self.columnView.setObjectName("columnView")
        self.label_7 = QLabel(self.tab2)
        self.label_7.setGeometry(QtCore.QRect(10, 210, 81, 21))
        self.label_7.setObjectName("label_7")
        self.SelectFolderbtn = QPushButton(self.tab2)
        self.SelectFolderbtn.setGeometry(QtCore.QRect(10, 230, 75, 23))
        self.SelectFolderbtn.setObjectName("SelectFolderbtn")
        self.IndexDir = QLineEdit(self.tab2)
        self.IndexDir.setGeometry(QtCore.QRect(100, 210, 381, 22))
        self.IndexDir.setObjectName("IndexDir")
        self.IndexGobtn = QPushButton(self.tab2)
        self.IndexGobtn.setGeometry(QtCore.QRect(180, 310, 75, 23))
        self.IndexGobtn.setObjectName("IndexGobtn")
        self.IndexStatus = QLabel(self.tab2)
        self.IndexStatus.setGeometry(QtCore.QRect(140, 240, 631, 51))
        font = QtGui.QFont()
        font.setPointSize(14)
        self.IndexStatus.setFont(font)
        self.IndexStatus.setText("")
        self.IndexStatus.setObjectName("IndexStatus")
        self.label = QLabel(self.tab2)
        self.label.setGeometry(QtCore.QRect(100, 170, 221, 31))
        self.label.setObjectName("label")
        self.PlaySoundCheck = QCheckBox(self.tab2)
        self.PlaySoundCheck.setGeometry(QtCore.QRect(100, 240, 70, 17))
        self.PlaySoundCheck.setObjectName("PlaySoundCheck")
        self.label_8 = QLabel(self.tab2)
        self.label_8.setGeometry(QtCore.QRect(10, 110, 80, 21))
        self.label_8.setObjectName("label_8")
        self.SearchRange = QSpinBox(self.tab2)
        self.SearchRange.setGeometry(QtCore.QRect(100, 110, 42, 22))
        self.SearchRange.setObjectName("SearchRange")
        self.label_9 = QLabel(self.tab2)
        self.label_9.setGeometry(QtCore.QRect(150, 110, 191, 21))
        self.label_9.setObjectName("label_9")
        self.OnTopCheck = QCheckBox(self.tab2)
        self.OnTopCheck.setGeometry(QtCore.QRect(680, 155, 91, 17))
        self.OnTopCheck.setObjectName("OnTopCheck")
        self.tabWidget.addTab(self.tab2, "")
        self.gridLayout_4.addWidget(self.tabWidget, 0, 0, 1, 1)
        self.retranslateUi(self)
        self.setCentralWidget(self.centralwidget)
        self.tabWidget.setCurrentIndex(0)
        QtCore.QMetaObject.connectSlotsByName(self)
        self.btnnxt.clicked.connect(self.Next)
        self.btnprev.clicked.connect(self.Previous)
        self.btnopen.clicked.connect(self.OpenDir)
        self.btnimgclr.clicked.connect(self.ClearImg)
        self.VPTreeDir.setText(settings.value('VPTree'))
        self.HashDir.setText(settings.value('Hashing'))
        self.SearchRange.setValue(int(settings.value('SearchRange')))
        self.SelectFolderbtn.clicked.connect(self.SelectFolderToIndex)
        self.IndexGobtn.clicked.connect(self.IndexStarter)
        self.SaveSettingsbtn.clicked.connect(self.SaveSettings)
        self.OnTopCheck.clicked.connect(self.OnTopChecker)
    def retranslateUi(self, Offline):
        _translate = QtCore.QCoreApplication.translate
        Offline.setWindowTitle(_translate("Offline", "Offline Reverse Image Search"))
        self.btnimgclr.setText(_translate("Offline", "Clear Image"))
        self.btnnxt.setText(_translate("Offline", "Next"))
        self.labelcurrent.setText(_translate("Offline", "Current"))
        self.btnprev.setText(_translate("Offline", "Previous"))
        self.btnopen.setText(_translate("Offline", "Open Directory"))
        self.labelresult.setText(_translate("Offline", "Total Results: "))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab1), _translate("Offline", "Finder"))
        self.SaveSettingsbtn.setText(_translate("Offline", "Save Settings"))
        self.label_5.setText(_translate("Offline", "Tree Directory"))
        self.label_6.setText(_translate("Offline", "Hash Directory"))
        self.label_7.setText(_translate("Offline", "Index Directory"))
        self.SelectFolderbtn.setText(_translate("Offline", "Select Folder"))
        self.IndexGobtn.setText(_translate("Offline", "Go"))
        self.label.setText(_translate("Offline", "Update Index Database"))
        self.PlaySoundCheck.setText(_translate("Offline", "Sound"))
        self.label_8.setText(_translate("Offline", "Search Range"))
        self.label_9.setText(_translate("Offline", "Default: 10 (Works best in most cases)"))
        self.OnTopCheck.setText(_translate("Offline", "Always On Top"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab2), _translate("Offline", "Settings - Index"))
    def OnTopChecker(self):
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.show()

    def SaveSettings(self):
        #Save current Settings
        settings.setValue('VPTree',self.VPTreeDir.text())
        settings.setValue('Hashing',self.HashDir.text())
        settings.setValue('SearchRange',self.SearchRange.value())

    def IndexStarter(self):
        #self.Indexworkerthreader()
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
        #self.worker.progress.connect(self.reportProgress)
        #Start the thread
        self.thread.start()

    def SelectFolderToIndex(self):
        #Opens Window dialog to select folder
        self.IndexDir.setText(str(QFileDialog.getExistingDirectory(self, "Select Directory")))

    def ImgIndexer(self):
        import vptree
        # Grab the paths to the input images and initialize the dictionary of hashes
        imagePaths = []
        imagePaths = list(paths.list_images(self.IndexDir.text()))
        hashes = {}
        # Loop over the image paths
        for (i, imagePath) in enumerate(imagePaths):
            try:
                # Load the input image
                self.IndexStatus.setText(f"processing image {i+1}/{len(imagePaths)}")
                image = cv2.imread(imagePath)

                # Compute the hash for the image and convert it
                h = dhash(image)
                h = convert_hash(h)

                # Update the hashes dictionary
                l = hashes.get(h, [])
                l.append(imagePath)
                hashes[h] = l
            except:
                print(imagePath+' Failed')

        # Load & add existing hashes/dirs
        try:
            hashes.update(pickle.loads(open(self.HashDir.text(),"rb").read()))
        except:
            print('no hashes pickle file exists')
        # build the VP-Tree
        self.IndexStatus.setText("[INFO] building VP-Tree...")
        points = list(hashes.keys())
        tree = vptree.VPTree(points, hamming)
        # serialize the VP-Tree to disk
        self.IndexStatus.setText("[INFO] serializing VP-Tree...")
        f = open(self.VPTreeDir.text(), "wb")
        f.write(pickle.dumps(tree))
        f.close()
        # serialize the hashes to dictionary
        self.IndexStatus.setText("[INFO] serializing hashes...")
        f = open(self.HashDir.text(), "wb")
        f.write(pickle.dumps(hashes))
        print(len(hashes))
        f.close()
        self.IndexStatus.setText('Finished')
        if self.PlaySoundCheck.isChecked():
            #playsound(dir_path+'ui/Success.wav')
            SuccessSound()
    def searcher(self,query):
        print(query)
        ImagesFound.clear()
        tree = pickle.loads(open(settings.value('VPTree'), "rb").read())
        hashes = pickle.loads(open(settings.value('Hashing'), "rb").read())
        # load the input query image
        image = cv2.imread(query)
        # compute the hash for the query image, then convert it
        queryHash = dhash(image)
        queryHash = convert_hash(queryHash)
        # perform the search
        results = tree.get_all_in_range(queryHash, int(settings.value('SearchRange')))
        results = sorted(results)
        # loop over the results
        for (d, h) in results:
            # grab all image paths in our dataset with the same hash
            resultPaths = hashes.get(h, [])
            for resultPath in resultPaths:
                ImagesFound.append(resultPath)

    def workerthreader(self):
        #Create a QThread object
        self.thread = QtCore.QThread()
        #Create a worker object
        self.worker = Worker()
        #Move worker to the thread
        self.worker.moveToThread(self.thread)
        #Connect signals and slots
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        #self.worker.progress.connect(self.reportProgress)
        #Start the thread
        self.thread.start()

    def dragEnterEvent(self, event):
        if event.mimeData().hasImage:
            event.accept()
        else:
            event.ignore()

    def OpenDir(self):
        import subprocess
        x = findall(r'\A.*\\',current)[0]
        x = str(x).replace('/','\\')
        print(x)
        subprocess.Popen('explorer "'+x+'"')

    def Previous(self):
        global d
        global current
        d.rotate(1)
        current = d[0]
        self.labelcurrent.setText('Current '+str(ImagesFound.index(current)+1)+'/'+str(len(ImagesFound)))
        self.set_image()

    def Next(self):
        global d
        global current
        d.rotate(-1)
        current = d[0]
        self.labelcurrent.setText('Current '+str(ImagesFound.index(current)+1)+'/'+str(len(ImagesFound)))
        self.set_image()

    def dragMoveEvent(self, event):
        if event.mimeData().hasImage:
            event.accept()
        else:
            event.ignore()

    def ClearImg(self):
        self.photoViewer.clear()
        self.photoMain.clear()
        self.photoViewer.setText('Place New Image')
        self.labelresult.setText('')
        self.labelcurrent.setText('')
        self.btnnxt.setEnabled(False)
        self.btnprev.setEnabled(False)
        self.btnopen.setEnabled(False)
        if os.path.isfile(dir_path+'testfile.jpg'):
            os.remove(dir_path+'testfile.jpg')
        
    def dropEvent(self, event):
        global d
        global current
        global file_path
        if event.mimeData().html():
            with open(dir_path+'testfile.jpg', 'wb') as f:
                f.write(requestsGet(findall('src="http.*.jpg|png"',event.mimeData().html())[0][5:]).content)
                file_path = dir_path+'testfile.jpg'
            event.accept()
            self.workerthreader()
        elif str(event.mimeData().urls()[0].toLocalFile()):
            file_path = str(event.mimeData().urls()[0].toLocalFile())
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp', '.gif')):
                event.accept()
                self.workerthreader()
            else:
                print('ignore')
                event.ignore()
        else:
            print('was something dropped?')
    def theEngine(self):
        global file_path
        global d
        global current
        self.searcher(file_path)
        if len(ImagesFound) == 0:
            self.photoMain.setPixmap(QPixmap(file_path).scaled(self.photoMain.width(),self.photoMain.height(),QtCore.Qt.AspectRatioMode.KeepAspectRatio,QtCore.Qt.TransformationMode.SmoothTransformation))#.scaled(600, 800, Qt.KeepAspectRatio, Qt.FastTransformation))
            self.photoViewer.setText('Nothing Found')
            self.btnnxt.setEnabled(False)
            self.btnprev.setEnabled(False)
            self.btnopen.setEnabled(False)
        else:
            self.photoMain.setPixmap(QPixmap(file_path).scaled(self.photoMain.width(),self.photoMain.height(),QtCore.Qt.AspectRatioMode.KeepAspectRatio,QtCore.Qt.TransformationMode.SmoothTransformation))#.scaled(600, 800, Qt.KeepAspectRatio, Qt.FastTransformation))
            self.btnnxt.setEnabled(True)
            self.btnprev.setEnabled(True)
            self.btnopen.setEnabled(True)

            d=deque(ImagesFound)
            current = d[0]
            self.labelresult.setText('Total results : '+str(len(ImagesFound)))
            self.labelcurrent.setText('Current '+str(ImagesFound.index(current)+1)+'/'+str(len(ImagesFound)))
            self.set_image()
            print('Links of found images:')
            for imageLink in (ImagesFound):
                print(imageLink)
        print('done0')
    def set_image(self):
        self.photoViewer.setPixmap(QPixmap(current).scaled(self.photoViewer.width(),self.photoViewer.height(),QtCore.Qt.AspectRatioMode.KeepAspectRatio,QtCore.Qt.TransformationMode.SmoothTransformation))#.scaled(900, 800, Qt.KeepAspectRatio, Qt.FastTransformation))


app = QApplication(sys.argv)
window = MyWindow()
window.show()

sys.exit(app.exec())
