#!/usr/bin/env python3
'''
The pi runs 32 bit arm, where pillow-heif has no wheel. These checks cover the
libheif command line fallback that handles HEIC there, by importing readmail
with pillow_heif forced unavailable.
'''

import os
import shutil
import sys
import tempfile
import time
from io import BytesIO

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))

from PIL import Image

#build a real heic payload while pillow-heif is still importable
import pillow_heif
pillow_heif.register_heif_opener()
_buf = BytesIO()
_src = Image.new('RGB', (1200, 900), (30, 90, 160))
_tags = _src.getexif()
_tags[306] = '2019:07:14 09:30:00'
_src.save(_buf, 'HEIF', exif=_tags.tobytes())
HEIC = _buf.getvalue()

#now make readmail believe pillow-heif is absent, exactly as on the pi
sys.modules['pillow_heif'] = None
import readmail

failures = []

def check(label, condition):
    print('  {m} {l}'.format(m='ok  ' if condition else 'FAIL', l=label))
    if not condition:
        failures.append(label)

inbox = tempfile.mkdtemp(prefix='frame-heif-test-')
readmail.filepath = inbox + '/'

def deliver(name, payload):
    dest = readmail.safe_destination(name)
    if dest is None or os.path.lexists(dest):
        return None
    try:
        readmail.convert_attachment(payload, dest)
    except Exception as error:
        print('      (' + str(error)[:70] + ')')
        return None
    return dest

try:
    print('\nthe fallback is the one under test')
    check('readmail sees pillow-heif as unavailable', readmail.HAVE_PILLOW_HEIF is False)
    check('heif-convert was located', bool(readmail.HEIF_CONVERT))

    print('\nsniffing heif without decoding it')
    check('a real heic is recognised', readmail.looks_like_heif(HEIC))
    check('a jpeg is not mistaken for heic',
          not readmail.looks_like_heif(b'\xff\xd8\xff\xe0' + b'\x00' * 40))
    check('a shell script is not mistaken for heic',
          not readmail.looks_like_heif(b'#!/bin/sh\nrm -rf /\n' + b'\x00' * 40))
    check('an mp4 (ftyp, wrong brand) is not accepted',
          not readmail.looks_like_heif(b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 40))
    check('a truncated header does not crash the sniffer',
          not readmail.looks_like_heif(b'\x00\x00\x00'))

    print('\nconverting an iphone heic without pillow-heif')
    out = deliver('IMG_0042.HEIC', HEIC)
    check('it produced a file', out is not None)
    if out:
        check('stored as .jpg', out.endswith('.jpg'))
        img = Image.open(out)
        check('the result really is a jpeg', img.format == 'JPEG')
        check('dimensions survived', img.size == (1200, 900))
        #the pipeline still applies: exif reduced to the date alone
        carried = dict(img.getexif())
        check('no stray exif carried over', set(carried) <= {306})
        #the running order depends on this surviving the libheif round trip
        check('the capture date survived heif-convert',
              str(carried.get(306)) == '2019:07:14 09:30:00')
        check('the capture date reached the file mtime',
              time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(out))) == '2019-07-14')

    print('\nthe hardening still applies on this path')
    check('a heic over the size cap is refused',
          deliver('huge.heic', HEIC + b'\x00' * readmail.MAX_ATTACHMENT_BYTES) is None)
    check('a file claiming .heic but holding a script is refused',
          deliver('fake.heic', b'#!/bin/sh\nrm -rf /\n') is None)
    check('a corrupt heic is refused',
          deliver('broken.heic', HEIC[:len(HEIC) // 3]) is None)
    check('no .partial scratch files left behind',
          not [f for f in os.listdir(inbox) if f.endswith('.partial')])
    check('no temp workdirs leaked',
          not [d for d in os.listdir(tempfile.gettempdir()) if d.startswith('frame-heif-')
               and d != os.path.basename(inbox)])

    print('\nordinary pictures are untouched by the fallback')
    jpg = BytesIO(); Image.new('RGB', (320, 240), (7, 7, 7)).save(jpg, 'JPEG')
    check('a plain jpeg still converts', deliver('ordinary.jpg', jpg.getvalue()) is not None)

finally:
    shutil.rmtree(inbox, ignore_errors=True)

print('')
if failures:
    print('{n} check(s) FAILED: {f}'.format(n=len(failures), f=', '.join(failures)))
    sys.exit(1)
print('all heif fallback checks passed')
