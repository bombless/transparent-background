import os
import re
import cv2
import torch
import hashlib
import argparse

import numpy as np

from PIL import Image
from threading import Thread

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', '-s',     type=str,            help="Path to the source. Single image, video, directory of images, directory of videos is supported.")
    parser.add_argument('--dest', '-d',       type=str,            help="Path to destination. Results will be stored in current directory if not specified.", default=None)
    parser.add_argument('--type', '-t',       type=str,            help="Specify output type. If not specified, output results will make the background transparent. Please refer to the documentation for other types.", default='rgba')
    parser.add_argument('--jit', '-j',        action='store_true', help="Use torchscript to reduce inference time.", default=False)
    return parser.parse_args()

def get_format(source):
    img_count = len([i for i in source if i.lower().endswith(('.jpg', '.png', '.jpeg'))])
    vid_count = len([i for i in source if i.lower().endswith(('.mp4', '.avi', '.mov' ))])
    
    if img_count * vid_count != 0:
        return ''
    elif img_count != 0:
        return 'Image'
    elif vid_count != 0:
        return 'Video'
    else:
        return ''

def sort(x):
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    return sorted(x, key=alphanum_key)

def download_and_unzip(filename, url, dest, unzip=True, **kwargs):
    if not os.path.isdir(dest):
        os.makedirs(dest, exist_ok=True)
    
    if os.path.isfile(os.path.join(dest, filename)) is False:
        os.system("wget -O {} {}".format(os.path.join(dest, filename), url))
    elif 'md5' in kwargs.keys() and kwargs['md5'] != hashlib.md5(open(os.path.join(dest, filename), 'rb').read()).hexdigest():
        os.system("wget -O {} {}".format(os.path.join(dest, filename), url))
        
    if unzip:
        os.system("unzip -o {} -d {}".format(os.path.join(dest, filename), dest))
        os.system("rm {}".format(os.path.join(dest, filename)))
        
class dynamic_resize:
    def __init__(self, L=1280): 
        self.L = L
                    
    def __call__(self, img):
        size = list(img.size)
        if (size[0] >= size[1]) and size[1] > self.L: 
            size[0] = size[0] / (size[1] / self.L)
            size[1] = self.L
        elif (size[1] > size[0]) and size[0] > self.L:
            size[1] = size[1] / (size[0] / self.L)
            size[0] = self.L
        size = (int(round(size[0] / 32)) * 32, int(round(size[1] / 32)) * 32)
    
        return img.resize(size, Image.BILINEAR)
    
class normalize:
    def __init__(self, mean=None, std=None, div=255):
        self.mean = mean if mean is not None else 0.0
        self.std = std if std is not None else 1.0
        self.div = div
        
    def __call__(self, img):
        img /= self.div
        img -= self.mean
        img /= self.std
            
        return img
    
class tonumpy:
    def __init__(self):
        pass

    def __call__(self, img):
        img = np.array(img, dtype=np.float32)
        return img
    
class totensor:
    def __init__(self):
        pass

    def __call__(self, img):
        img = img.transpose((2, 0, 1))
        img = torch.from_numpy(img).float()
        
        return img

class ImageLoader:
    def __init__(self, root):
        if os.path.isdir(root):
            self.images = [os.path.join(root, f) for f in os.listdir(root) if f.lower().endswith(('.jpg', '.png', '.jpeg'))]
            self.images = sort(self.images)
        elif os.path.isfile(root):
            self.images = [root]
        self.size = len(self.images)

    def __iter__(self):
        self.index = 0
        return self

    def __next__(self):
        if self.index == self.size:
            raise StopIteration
        
        img = Image.open(self.images[self.index]).convert('RGB')
        name = self.images[self.index].split(os.sep)[-1]
        name = os.path.splitext(name)[0]
            
        self.index += 1
        return img, name

    def __len__(self):
        return self.size
    
class VideoLoader:
    def __init__(self, root):
        if os.path.isdir(root):
            self.videos = [os.path.join(root, f) for f in os.listdir(root) if f.lower().endswith(('.mp4', '.avi', 'mov'))]
        elif os.path.isfile(root):
            self.videos = [root]
        self.size = len(self.videos)

    def __iter__(self):
        self.index = 0
        self.cap = None
        self.fps = None
        return self

    def __next__(self):
        if self.index == self.size:
            raise StopIteration
        
        if self.cap is None:
            self.cap = cv2.VideoCapture(self.videos[self.index])
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        ret, frame = self.cap.read()
        name = self.videos[self.index].split(os.sep)[-1]
        name = os.path.splitext(name)[0]
        if ret is False:
            self.cap.release()
            self.cap = None
            img = None
            self.index += 1
        
        else:
            img = Image.fromarray(frame).convert('RGB')
            
        return img, name
    
    def __len__(self):
        return self.size