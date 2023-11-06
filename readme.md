# Offline Reverse Image Search

## Overview

This app finds duplicate to near duplicate images by generating a hash value for each image stored with a specialized data structure called VP-Tree which makes searching an image on a dataset of 100Ks almost instantanious

## Updates
3rd update:
* Added a log of actions tab
* Better support for drag n drop
* Fixed various crashes and better error handling
* Upgraded the quality of code

2nd update:
* Replaced OpenCV with Pillow
* Various Small Fixes to prevent crashing
* Added Progress bar
* Added Splash Logo (with more UI Plans on future updates) Thanks to [Creative Force](https://www.facebook.com/creativethunder.eu)

1st update:
* Deprecated .ui & success.wav file
* Added "always on top" on settings 
* Decreased possible crashes on drag n drop 

## Online Examples
Online examples of this are [Google images](https://images.google.com/) & [TinEye](https://tineye.com/) which return near duplicate results from images they indexed across the web

## App UI & example
On the left you can see the given image *(for the example it's slightly different from the original)* and on the right the result

<img src="https://user-images.githubusercontent.com/47922937/138560831-033acbf8-722b-493b-ad6e-927c5a90f69e.JPG" width="50%">

- You can also drag n drop an image from browser! (Firefox / Chrome tested)


## Dependencies

- Python 3.7+ (haven't tested with older versions)

## Requirements & installation

required versions of the Python 3 modules can be found on the requirements.txt

*Pyqt6 is used but works with PyQt5 too if you update the ``app.py`` file modules import*

### Windows
    pip install -r /path/to/requirements.txt
### Linux
    pip3 install -r /path/to/requirements.txt 

run ``app.py`` to start

## First run:
settings.ini will be created on the directory

Hashing Pickle & VPTree pickle files will be created on the first index 

## More detail & Credits

- [What is dHash and how it works](https://github.com/Rayraegah/dhash#difference-value-hash-dhash)<br>
- [A good guide about Python Pickle](https://zetcode.com/python/pickle/)

Special Thanks to Adrian Rosebrock for his tutorials that made this possible<br>
[Detailed Guide how everything works and step by step make your own](https://www.pyimagesearch.com/2019/08/26/building-an-image-hashing-search-engine-with-vp-trees-and-opencv/#download-the-code)

