# Offline Reverse Image Search

## Overview

This app finds duplicate to near duplicate images by generating a hash value for each image stored with a specialized data structure called VP-Tree which makes searching an image on a dataset of 100Ks almost instantanious

## Updates

1st update:
* Deprecated .ui file
* Added "always on top" on settings 
* Decreased possible crashes on drag n drop 

## Online Examples
Online examples of this are [Google images](https://images.google.com/) & [TinEye](https://tineye.com/) which return near duplicate results from images they indexed across the web


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

