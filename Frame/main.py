#!/usr/bin/env python3
'''
@Project Pic Frame
@author cedric
@date 2020-08-16
'''

#tkinter imports
from tkinter import *
from PIL import ImageTk, Image 

#Image.ANTIALIAS was removed in Pillow 10, LANCZOS is the same filter
RESAMPLE = getattr(Image, 'Resampling', Image).LANCZOS

#The frame displays, it does not convert. readmail.py turns every incoming
#picture into a jpg, anything else in img/ is ignored.
DISPLAYABLE = ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff')

#files
import json
from os import walk
from os.path import dirname, isfile, abspath, getmtime, join

#logic
import time
import _thread

#parse config
config = json.load(open(abspath(dirname(__file__))+"/Config.json"))
path_to_img = config['files']['path']
sleeptime = config['display']['displaytime_in_seconds']

#variables
path_to_dir = abspath(dirname(__file__))
dir_to_img = '/'+path_to_img
files = []

#Caching all files found in subdir 'img/'
def cache_files():
    global files
    files = []
    for (dirpath, dirnames, filenames) in walk(path_to_dir+dir_to_img):
        displayable = [name for name in filenames
                    if name.lower().endswith(DISPLAYABLE) and not name.startswith('.')]
        for fname in sorted(displayable, key=lambda name:
                    getmtime(join(dirpath, name))):
            files.append(fname)
    print(str(len(files))+' files cached!')

#running method before init of app
cache_files()

class Window(Frame):

    def __init__(self, parent=None):
        Frame.__init__(self, parent)
        self.parent = parent
        self.pack(fill=BOTH, expand=YES)

        self.img = Label(self, image="")
        self.img.config(background='black')
        self.img.grid(row=0, column=0) 
        self.img.place(relx = 0.5, rely = 0.5, anchor = 'center')
        #start thread for walking through files
        _thread.start_new_thread(self.nextfile, ())
    
    #change image path and reload it from disk
    def changeImage(self, filename):
        render = self.openImage(filename)
        self.img.configure(image=render)
        self.img.image=render
    
    #iterate over files to call next image
    def nextfile(self):
        while (True):
            shown = 0
            for fname in files:
                if isfile(abspath(path_to_dir)+dir_to_img+fname):
                    #a file that is corrupt, half written or simply not an
                    #image must not kill the thread, skip it and carry on
                    try:
                        self.changeImage(fname)
                    except Exception as error:
                        print('Skipping "{fname}": {error}'.format(fname=fname, error=error))
                        continue
                    shown += 1
                    time.sleep(sleeptime)
            #An empty folder, or one where nothing could be decoded, would
            #spin this loop at full speed and heat up the pi for nothing.
            #Wait instead, readmail.py may deliver something later on.
            if shown == 0:
                time.sleep(sleeptime)
            #cache new files
            cache_files()
        #runs in infinite loop!

    #open Image, convert it to fit either landscape or portrait and return as PhotoImage
    def openImage(self, filename):
        #absolute, so the frame also works when it is started from
        #somewhere else than Frame/ (systemd, cron, autostart)
        image = Image.open(abspath(path_to_dir)+dir_to_img+filename)
        screensize = root.winfo_screenwidth(), root.winfo_screenheight()

        #fit longer axis to screen, shorter axis = image * (screen/image)
        #size = [width, height]
        if image.size[0]>image.size[1]:
            newSize = screensize[0], int(image.size[1]*(screensize[0]/image.size[0]))
        else:
            newSize = int(image.size[0]*(screensize[1]/image.size[1])), screensize[1]

        return ImageTk.PhotoImage(image.resize(newSize, RESAMPLE))


root = Tk()
app = Window(root)
root.title("Frame")
# root.geometry("480x480") #enable for windowed
root.attributes('-fullscreen', True) #enable for fullscreen
app.config(background='black', cursor='none')
root.mainloop() 
