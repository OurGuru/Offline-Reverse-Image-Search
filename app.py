import logging
from PyQt6 import QtCore, QtGui
import sys
import os 
from re import findall
from PyQt6.QtWidgets import QFileDialog, QApplication, QMainWindow,QWidget,QGridLayout,QTabWidget, QPushButton,QLabel,QLineEdit,QSpinBox,QCheckBox,QSplashScreen
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import QProgressBar
from pickle import loads as pickleloads
from pickle import dump as pickledump
from pickle import dumps as pickledumps
from collections import deque
from requests import get as requestsGet
from imutils import paths
from chime import success as SuccessSound
from PIL import Image
from numpy import array as nparray


def hamming(a, b):
    # compute and return the Hamming distance between the integers
    return bin(int(a) ^ int(b)).count("1")

def dhash(image, hashSize=8):
    # convert the image to grayscale
    gray = Image.open(image).convert('L')
    # resize the grayscale image, adding a single column (width) so we
    # can compute the horizontal gradient
    resized = gray.resize((hashSize + 1, hashSize))
    # compute the (relative) horizontal gradient between adjacent
    # column pixels
    # diff = resized[:, 1:] > resized[:, :-1]
    resized = nparray(resized)
    diff = resized[:, 1:] > resized[:, :-1]
    # convert the difference image to a hash
    return sum([2 ** i for (i, v) in enumerate(diff.flatten()) if v])

def convert_hash(h):
    # convert the hash to NumPy's 64-bit float and then back to
    # Python's built in int
    import numpy as np
    return int(np.array(h, dtype="float64"))


class Worker(QtCore.QObject):
    # finished = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal(int)
    finished = QtCore.pyqtSignal()

    def run(self):
        #print('start 1')
        window.theEngine()
        #print('done1')
        self.finished.emit()
        #print('done2')


class IndexWorker(QtCore.QObject):
    # finished = QtCore.pyqtSignal()
    progress = QtCore.pyqtSignal(int)
    finished = QtCore.pyqtSignal()

    def run(self):
    
        print('start 1')
        window.ImgIndexer()
        print('done1')
        self.finished.emit()
        print('done2')

# class ProgressBar(QProgressBar):
#     def __init__(self, parent=None):
#         super(ProgressBar, self).__init__(parent)
#         self.setMinimum(0)
#         self.setMaximum(200)
#         self.setValue(0)
#         self._active = False
#     def updateBar(self, value):
#         self.setValue(value)

#create a class for a splashscreen
base64Photo = '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'
import base64
class SplashScreen(QSplashScreen):
    def __init__(self):
        super(QSplashScreen,self).__init__()
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint)
        pixmap = QPixmap()
        pixmap.loadFromData(base64.b64decode(base64Photo))
        self.setPixmap(pixmap)
        QtCore.QTimer.singleShot(1200, self.close)


class MyWindow(QMainWindow):
    def __init__(self):
        super(MyWindow, self).__init__()
        #Last UI Configs & connect UI buttons to functions
        pixmap = QPixmap()
        pixmap.loadFromData(base64.b64decode(base64Photo))
        self.setWindowIcon(QIcon(pixmap))
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
        self.progressBar = QProgressBar(self.tab2)
        self.progressBar.setGeometry(QtCore.QRect(10, 310, 161, 23))
        self.progressBar.setProperty("value", 0)
        self.progressBar.setRange(0, 100)
        self.progressBar.setObjectName("progressBar")
        
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
        self.label_9.setGeometry(QtCore.QRect(150, 110, 210, 21))
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
        self.label_9.setText(_translate("Offline", "Default: 6 (5 = identical)"))
        self.OnTopCheck.setText(_translate("Offline", "Always On Top"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab2), _translate("Offline", "Settings - Index"))
    def OnTopChecker(self):
        self.setWindowFlags(self.windowFlags() ^ QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.show()

    def updateProgressBar(self, value):
        self.progressBar.setValue(value)

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
        self.worker.progress.connect(self.updateProgressBar)
        #Start the thread
        self.thread.start()

    def SelectFolderToIndex(self):
        #Opens Window dialog to select folder
        self.IndexDir.setText(str(QFileDialog.getExistingDirectory(self, "Select Directory")))

    def ImgIndexer(self):
        import vptree
        # Grab the paths to the input images and initialize the dictionary of hashes
        imagePaths = []
        self.IndexStatus.setText("Count Images...")
        imagePaths = list(paths.list_images(self.IndexDir.text()))
        hashes = {}
        # Loop over the image paths
        
        self.IndexGobtn.setEnabled(False)
        self.SelectFolderbtn.setEnabled(False)

        for (i, imagePath) in enumerate(imagePaths):
            try:
                # Load the input image
                self.IndexStatus.setText(f"processing image {i+1}/{len(imagePaths)}")
                self.worker.progress.emit(((i+1)/len(imagePaths))*100)


                # Compute the hash for the image and convert it
                h = dhash(imagePath)
                h = convert_hash(h)

                # Update the hashes dictionary
                l = hashes.get(h, [])
                l.append(imagePath)
                hashes[h] = l
            except Exception as e:
                print(e)
                logging.error(e, exc_info=True)
                print(imagePath+' Failed')

        # Load & add existing hashes/dirs
        try:
            hashes.update(pickleloads(open(self.HashDir.text(),"rb").read()))
        except:
            print('no hashes pickle file exists, creating one')
            pickledump(hashes, open(self.HashDir.text(), "wb"))
        

        # build the VP-Tree
        self.IndexStatus.setText("[INFO] building VP-Tree...")
        points = list(hashes.keys())
        tree = vptree.VPTree(points, hamming)
        # serialize the VP-Tree to disk
        self.IndexStatus.setText("[INFO] serializing VP-Tree...")
        f = open(self.VPTreeDir.text(), "wb")
        f.write(pickledumps(tree))
        f.close()
        # serialize the hashes to dictionary
        self.IndexStatus.setText("[INFO] serializing hashes...")
        f = open(self.HashDir.text(), "wb")
        f.write(pickledumps(hashes))
        print(len(hashes))
        f.close()
        self.IndexStatus.setText('Finished')
        if self.PlaySoundCheck.isChecked():
            #playsound(dir_path+'ui/Success.wav')
            SuccessSound()
        self.IndexGobtn.setEnabled(True)
        self.SelectFolderbtn.setEnabled(True)
        self.worker.progress.emit(0)

    def searcher(self,query):
        print(query)
        ImagesFound.clear()
        tree = pickleloads(open(settings.value('VPTree'), "rb").read())
        hashes = pickleloads(open(settings.value('Hashing'), "rb").read())
        # load the input query image
        # compute the hash for the query image, then convert it
        queryHash = dhash(query)
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
        self.ClearImg()
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




if __name__ == "__main__":

    # dir_path = (f"{os.path.dirname(os.path.realpath(__file__))}/").replace('\\','/') 
    dir_path = os.getcwd().replace('\\','\\\\')+"\\\\"
    ImagesFound = []
    d=deque(ImagesFound)
    current = ''
    file_path = ''

    if os.path.isfile(dir_path+'settings.ini'):
        print('loaded settings')
    else:
        with open(dir_path+'settings.ini','w') as f:
            f.write(f'[General]\nVPTree={dir_path}VPtree.pickle\nHashing={dir_path}Hashing.pickle\nSearchRange=6')
        print('no settings file, created one')
    settings = QtCore.QSettings(dir_path+'settings.ini',QtCore.QSettings.Format.IniFormat)

    app = QApplication(sys.argv)
    window = MyWindow()
    window.show()
    splash = SplashScreen()
    splash.show()
    app.processEvents()


    sys.exit(app.exec())
