#!/usr/bin/env python3
'''
@Project Pic Frame
@author cedric
@date 2020-08-16

Normalises whatever is sitting in img/: everything the frame can read is
turned into an upright jpg. Pictures that arrive by mail are already
converted by readmail.py, so this is for the ones copied in by hand over
scp or from a usb stick, which never pass through the mail fetcher.

Safe to run repeatedly, a picture that is already an upright jpg is left
untouched rather than re-encoded.
'''

import os
import sys
from os.path import abspath, dirname, isfile, islink, join, splitext

sys.path.insert(0, dirname(abspath(__file__)))

from PIL import Image, ImageOps

#the allowlist, the size limits and the img/ path all live in readmail,
#importing it opens no mail connection
import readmail

EXIF_ORIENTATION = 274

#re-saving a jpg costs quality every single time, so only touch a picture
#that is actually rotated or in a format the frame cannot show
def needs_work(image, path):
    upright = image.getexif().get(EXIF_ORIENTATION, 1) in (0, 1)
    is_jpg = image.format == 'JPEG' and path.lower().endswith(('.jpg', '.jpeg'))
    return not (upright and is_jpg)

def normalise(path):
    with Image.open(path) as image:
        if image.format not in readmail.ALLOWED_FORMATS:
            return 'skipped, {fmt} is not displayable'.format(fmt=image.format)
        if not needs_work(image, path):
            return None
        taken, stamp = readmail.capture_date(image)
        upright = ImageOps.exif_transpose(image).convert('RGB')

    target = splitext(path)[0] + '.jpg'
    if target != path and os.path.lexists(target):
        return 'skipped, {name} already exists'.format(name=os.path.basename(target))

    #carry the capture date over, otherwise re-saving would move the picture
    #to the end of the frame's running order
    keep = Image.Exif()
    if taken:
        keep[readmail.EXIF_DATETIME] = taken
        upright.save(target, 'JPEG', quality=90, exif=keep.tobytes())
    else:
        #no exif date, so preserve whatever mtime the file already had
        stamp = os.path.getmtime(path)
        upright.save(target, 'JPEG', quality=90)

    if target != path:
        os.remove(path)
    if stamp:
        os.utime(target, (stamp, stamp))
    if target != path:
        return 'converted to {name}'.format(name=os.path.basename(target))
    return 'rotated upright'

def main():
    folder = readmail.filepath
    if not os.path.isdir(folder):
        print('{folder} does not exist.'.format(folder=folder))
        return

    touched = 0
    for name in sorted(os.listdir(folder)):
        path = join(folder, name)
        if not isfile(path) or islink(path):
            continue
        try:
            result = normalise(path)
        except Exception as error:
            print('  {name}: {error}'.format(name=name, error=error))
            continue
        if result:
            print('  {name}: {result}'.format(name=name, result=result))
            touched += 1

    print('{n} picture(s) changed.'.format(n=touched))


if __name__ == '__main__':
    main()
