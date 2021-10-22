#from PyQt5.QtCore import qsrand
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6 import uic
import sys
import os 
from re import findall
import sys
from PyQt6.QtWidgets import QFileDialog, QApplication#, QPushButton, QWidget, QLabel, QGridLayout, QDesktopWidget
from PyQt6.QtCore import Qt, QThread, QObject,pyqtSignal, QSettings
from PyQt6.QtGui import QPixmap
import pickle
import cv2
from collections import deque
import requests
from imutils import paths
from playsound import playsound


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


#print(os.path.dirname(os.path.realpath(__file__)))
dir_path = (f"{os.path.dirname(os.path.realpath(__file__))}/").replace('\\','/') 
#settings = QSettings(os.path.dirname(dir_path+'/settings.ini',QSettings.Format.IniFormat))
ImagesFound = []
d=deque(ImagesFound)
current = ''
file_path = ''

if os.path.isfile(dir_path+'settings.ini'):
    print('loaded settings')
    # print(settings.value('VPTree'))
    # print(settings.value('Hashing'))
else:
    with open(dir_path+'settings.ini','w') as f:
        f.write(f'[General]\nVPTree={dir_path}VPtree.pickle\nHashing={dir_path}Hashing.pickle\nSearchRange=10')
    print('no settings file, created one')
settings = QSettings(dir_path+'settings.ini',QSettings.Format.IniFormat)

class Worker(QObject):
    # finished = pyqtSignal()
    # progress = pyqtSignal(int)
    finished = pyqtSignal()

    def run(self):
        #print('start 1')
        window.theEngine()
        #print('done1')
        self.finished.emit()
        #print('done2')


class IndexWorker(QObject):
    # finished = pyqtSignal()
    # progress = pyqtSignal(int)
    finished = pyqtSignal()

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
        uic.loadUi(dir_path+"ui/design.ui", self) # load the ui file
        #Last UI Configs & connect UI buttons to functions
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

    def SaveSettings(self):
        #Save current Settings
        settings.setValue('VPTree',self.VPTreeDir.text())
        settings.setValue('Hashing',self.HashDir.text())
        settings.setValue('SearchRange',self.SearchRange.value())

    def IndexStarter(self):
        #self.Indexworkerthreader()
        #Create a QThread object
        self.thread = QThread()
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
            playsound(dir_path+'ui/Success.wav')
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
        self.thread = QThread()
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
        
        if event.mimeData().hasImage:
            file_path = str(event.mimeData().urls()[0].toLocalFile())
            if (file_path) and ('Local/Temp' not in str(file_path)) :
                print('has smth')
                pass #Can proceed
            else:
                print('its empty')
                with open(dir_path+'testfile.jpg', 'wb') as f:
                    f.write(requests.get(findall('src="http.*.jpg|png"',event.mimeData().html())[0][5:]).content)
                file_path = dir_path+'testfile.jpg'
            event.accept()
            self.workerthreader()
            print('its true go')
        else:
            print('ignore')
            event.ignore()
    def theEngine(self):
        global file_path
        global d
        global current
        self.searcher(file_path)
        if len(ImagesFound) == 0:
            self.ClearImg()
            self.photoMain.setPixmap(QPixmap(file_path).scaled(self.photoMain.width(),self.photoMain.height(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))#.scaled(600, 800, Qt.KeepAspectRatio, Qt.FastTransformation))
            self.photoViewer.setText('Nothing Found')
            self.btnnxt.setEnabled(False)
            self.btnprev.setEnabled(False)
            self.btnopen.setEnabled(False)
        else:
            self.photoMain.setPixmap(QPixmap(file_path).scaled(self.photoMain.width(),self.photoMain.height(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))#.scaled(600, 800, Qt.KeepAspectRatio, Qt.FastTransformation))
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
        self.photoViewer.setPixmap(QPixmap(current).scaled(self.photoViewer.width(),self.photoViewer.height(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))#.scaled(900, 800, Qt.KeepAspectRatio, Qt.FastTransformation))


app = QApplication(sys.argv)
window = MyWindow()
window.show()

sys.exit(app.exec())
