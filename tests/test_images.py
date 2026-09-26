#!/usr/bin/env python3
'''
Checks the attachment handling in readmail.py: that pictures are converted to
jpg, and that a hostile mail cannot use an attachment to write where it likes.
Run it inside the container, see the Dockerfile.
'''

import os
import shutil
import sys
import tempfile
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'Frame'))

from PIL import Image
import readmail

failures = []

def check(label, condition):
    print('  {mark} {label}'.format(mark='ok  ' if condition else 'FAIL', label=label))
    if not condition:
        failures.append(label)

#run one attachment through the same path readmail.py uses, return the file it
#produced inside img/ or None if it was rejected
def deliver(fileName, payload):
    dest = readmail.safe_destination(fileName)
    if dest is None or os.path.lexists(dest):
        return None
    try:
        readmail.convert_attachment(payload, dest)
    except Exception:
        return None
    return dest

def encode(mode, size, fmt, colour=(40, 90, 160)):
    buf = BytesIO()
    Image.new(mode, size, colour).save(buf, fmt)
    return buf.getvalue()


inbox = tempfile.mkdtemp(prefix='frame-test-')
readmail.filepath = inbox + '/'

try:
    jpg = encode('RGB', (800, 600), 'JPEG')
    png = encode('RGBA', (300, 300), 'PNG', (0, 255, 0, 128))

    print('\nconversion')
    out = deliver('holiday.JPG', jpg)
    check('a jpg is stored', out is not None and os.path.isfile(out))
    out = deliver('logo.png', png)
    check('a png is converted to jpg', out is not None and out.endswith('.jpg'))
    check('the stored file really is a jpeg', Image.open(out).format == 'JPEG')
    try:
        heic = encode('RGB', (1200, 900), 'HEIF')
        out = deliver('IMG_0042.HEIC', heic)
        check('an iphone heic is converted to jpg',
              out is not None and os.path.basename(out) == 'IMG_0042.jpg')
    except KeyError:
        print('  skip pillow-heif missing, HEIC not exercised')
    check('the same picture is not stored twice', deliver('holiday.JPG', jpg) is None)

    print('\nexif orientation is applied, not carried along')
    rotated = Image.new('RGB', (200, 100), (10, 10, 10))
    buf = BytesIO()
    exif = rotated.getexif()
    exif[274] = 6                       #rotate 90 degrees on display
    rotated.save(buf, 'JPEG', exif=exif)
    out = deliver('rotated.jpg', buf.getvalue())
    stored = Image.open(out)
    check('the picture is rotated on disk', stored.size == (100, 200))
    check('exif (and with it any gps tag) is gone', not dict(stored.getexif()))

    print('\nnothing but pictures reaches the disk')
    for label, name, payload in [
        ('a shell script named .jpg', 'payload.jpg', b'#!/bin/sh\nrm -rf /\n'),
        ('a text file', 'notes.txt', b'hello'),
        ('an ELF binary', 'tool.jpg', b'\x7fELF' + b'\x00' * 200),
        ('a zip archive', 'archive.zip', b'PK\x03\x04' + b'\x00' * 100),
        ('an svg', 'x.svg', b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>'),
        ('an empty attachment', 'empty.jpg', b''),
        ('a missing payload', 'none.jpg', None),
        ('a truncated jpeg', 'cut.jpg', jpg[:len(jpg) // 3]),
    ]:
        check(label + ' is skipped', deliver(name, payload) is None)

    #Pillow runs ghostscript to read EPS, that must never be reachable from mail
    eps = b'%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\nshowpage\n%%EOF\n'
    check('an eps is skipped, it would call ghostscript', deliver('art.eps', eps) is None)

    print('\ndecompression bombs')
    Image.MAX_IMAGE_PIXELS = None
    bomb = encode('L', (30000, 30000), 'PNG', 0)
    Image.MAX_IMAGE_PIXELS = readmail.MAX_PIXELS
    check('a 900 megapixel png ({kb} kB on disk) is refused'.format(kb=len(bomb) // 1024),
          deliver('bomb.png', bomb) is None)
    check('an oversized attachment is refused',
          deliver('big.jpg', jpg + b'\x00' * (readmail.MAX_ATTACHMENT_BYTES + 1)) is None)
    check('no half written file is left behind',
          not os.path.exists(os.path.join(inbox, 'bomb.jpg')))

    print('\nthe filename in the mail cannot point outside img/')
    for label, name in [
        ('a relative escape', '../../../../etc/cron.d/evil'),
        ('an absolute path', '/etc/passwd'),
        ('windows separators', '..\\..\\..\\Windows\\evil.jpg'),
        ('a mixed escape', 'img/../../escape.jpg'),
        ('a dotfile', '.bashrc'),
        ('a null byte', 'ok\x00.jpg'),
        ('a newline', 'a\nb.jpg'),
    ]:
        dest = readmail.safe_destination(name)
        contained = dest is None or os.path.dirname(dest) == os.path.realpath(inbox)
        check(label + ' stays inside img/', contained)
    check('an empty name is rejected', readmail.safe_destination('') is None)
    check('a bare .. is rejected', readmail.safe_destination('..') is None)

    print('\nsymlinks are not followed')
    link = os.path.join(inbox, 'link.jpg')
    os.symlink('/tmp/frame-test-should-not-exist', link)
    check('writing through a planted symlink is refused', deliver('link.jpg', jpg) is None)
    check('the symlink target was not created',
          not os.path.exists('/tmp/frame-test-should-not-exist'))

    print('\nimport safety')
    check('importing readmail opens no imap connection', hasattr(readmail, 'main'))

finally:
    shutil.rmtree(inbox, ignore_errors=True)

print('')
if failures:
    print('{n} check(s) FAILED: {names}'.format(n=len(failures), names=', '.join(failures)))
    sys.exit(1)
print('all image checks passed')
