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
    check('no .partial scratch file is left behind',
          not [n for n in os.listdir(inbox) if n.endswith('.partial')])
    check('a 0 byte attachment never creates a file',
          deliver('zero.jpg', b'') is None and not os.path.exists(os.path.join(inbox, 'zero.jpg')))

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

    print('\nthe capture date decides the running order')

    def mail_photo(name, taken):
        #a picture as it arrives from a phone: capture date plus the camera
        #identification tags that sit alongside the location data
        buf = BytesIO()
        picture = Image.new('RGB', (160, 120), (60, 60, 60))
        tags = picture.getexif()
        tags[306] = taken
        tags[271] = 'Apple'                 # Make
        tags[272] = 'iPhone 13'             # Model
        tags[305] = 'secret-build-1234'     # Software
        picture.save(buf, 'JPEG', exif=tags)
        return deliver(name, buf.getvalue())

    #delivered newest first, as a backlog of mail would arrive
    newer = mail_photo('second.jpg', '2024:01:01 12:00:00')
    older = mail_photo('first.jpg', '2019:07:14 09:30:00')
    check('the capture date survives conversion',
          str(Image.open(older).getexif().get(306)) == '2019:07:14 09:30:00')
    #the converted file gets a freshly built exif holding the date alone, so
    #anything else the phone attached, location included, cannot survive
    carried = dict(Image.open(older).getexif())
    check('the camera tags are dropped', not any(t in carried for t in (271, 272, 305)))
    check('nothing but the date is carried over', set(carried) <= {306})
    check('the older picture sorts first despite arriving last',
          os.path.getmtime(older) < os.path.getmtime(newer))

    #a picture with no exif date must still work, falling back to now
    plain = deliver('nodate.jpg', jpg)
    check('a picture without an exif date still converts', plain is not None)

    print('\nrotate.py normalises pictures copied in by hand')
    import rotate
    for name in os.listdir(inbox):
        os.remove(os.path.join(inbox, name))

    #a rotated jpg, the phone marks the orientation instead of turning pixels
    sideways = Image.new('RGB', (200, 100), (10, 10, 10))
    tags = sideways.getexif()
    tags[274] = 6
    sideways.save(os.path.join(inbox, 'sideways.jpg'), 'JPEG', exif=tags)
    #a png, which the frame can show but readmail would have converted
    Image.new('RGB', (120, 80), (9, 9, 9)).save(os.path.join(inbox, 'hand-copied.png'))
    #an upright jpg, which must not be touched at all
    upright = os.path.join(inbox, 'fine.jpg')
    Image.new('RGB', (150, 90), (7, 7, 7)).save(upright, 'JPEG', quality=90)
    before = open(upright, 'rb').read()

    rotate.main()

    rotated = Image.open(os.path.join(inbox, 'sideways.jpg'))
    check('a sideways jpg is turned upright', rotated.size == (100, 200))
    check('a hand copied png becomes a jpg', os.path.isfile(os.path.join(inbox, 'hand-copied.jpg')))
    check('the png original is gone', not os.path.isfile(os.path.join(inbox, 'hand-copied.png')))
    check('an upright jpg is not re-encoded', open(upright, 'rb').read() == before)

    #running it again must be a no-op, not another round of recompression
    snapshot = {n: open(os.path.join(inbox, n), 'rb').read() for n in os.listdir(inbox)}
    rotate.main()
    unchanged = all(open(os.path.join(inbox, n), 'rb').read() == b for n, b in snapshot.items())
    check('running it twice changes nothing', unchanged)

    dated = os.path.join(inbox, 'dated.png')
    Image.new('RGB', (100, 60), (5, 5, 5)).save(dated)
    os.utime(dated, (1_000_000_000, 1_000_000_000))
    rotate.main()
    converted = os.path.join(inbox, 'dated.jpg')
    check('rotate keeps the running order when it converts a file',
          os.path.isfile(converted) and abs(os.path.getmtime(converted) - 1_000_000_000) < 2)

finally:
    shutil.rmtree(inbox, ignore_errors=True)

print('')
if failures:
    print('{n} check(s) FAILED: {names}'.format(n=len(failures), names=', '.join(failures)))
    sys.exit(1)
print('all image checks passed')
