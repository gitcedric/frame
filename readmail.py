import imaplib
import email
import json
import base64
import os
import re
import time
from io import BytesIO
from os.path import dirname, abspath

from PIL import Image, ImageOps

#HEIF/HEIC support (iPhone photos), optional
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    print('pillow-heif not installed, HEIC attachments will be skipped.')

#parse config
config = json.load(open(abspath(dirname(__file__))+"/Config.json"))
user = config['mail']['login']
settings = config['mail']['settings']
fileconfig = config['files']

#img filepath
path_to_dir = abspath(dirname(__file__))
#files.path may be relative to this script or absolute, join returns the
#configured value unchanged when it is already absolute
filepath = os.path.join(path_to_dir, fileconfig['path'])
max_foldersize = fileconfig['max_foldersize']
mail_folder = settings['folder']


#Mail attachments are untrusted input. Everything below assumes the sender is
#hostile: only formats on this list are decoded at all, the result is always
#re-encoded to jpg, and the original bytes never reach the disk.
#Formats that make Pillow call out to other programs (EPS -> ghostscript) are
#deliberately absent.
ALLOWED_FORMATS = ('JPEG', 'JPEG2000', 'PNG', 'GIF', 'BMP', 'WEBP', 'TIFF',
                   'HEIF', 'AVIF', 'MPO', 'PPM', 'ICO')

#refuse anything bigger than this before it is handed to a decoder
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
#a 100 kB file can claim to be 60000x60000 pixels, decoding it would eat the Pi
MAX_PIXELS = 80 * 1000 * 1000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

#DateTimeOriginal and DateTimeDigitized live in the exif sub ifd, DateTime
#sits at the top level
EXIF_SUB_IFD = 0x8769
EXIF_DATETIME = 306
EXIF_TAKEN = (36867, 36868)

#When the picture was taken, as the exif string and a timestamp. The frame
#orders by this, so a backlog of mail does not show up as one undated lump.
def capture_date(image):
    try:
        exif = image.getexif()
    except Exception:
        return None, None

    value = None
    try:
        sub = exif.get_ifd(EXIF_SUB_IFD)
    except Exception:
        sub = {}
    for tag in EXIF_TAKEN:
        if sub.get(tag):
            value = sub[tag]
            break
    if not value:
        value = exif.get(EXIF_DATETIME)
    if not value:
        return None, None

    value = str(value)
    try:
        stamp = time.mktime(time.strptime(value, '%Y:%m:%d %H:%M:%S'))
    except (ValueError, OverflowError):
        return value, None
    return value, stamp

#the frame only ever stores jpg
def target_name(fileName):
    return os.path.splitext(fileName)[0] + '.jpg'

#The filename comes straight from the mail and may be './../../etc/cron.d/x',
#an absolute path or contain control characters. Keep the last path segment
#only, then confirm the result really sits in img/.
def safe_destination(fileName):
    name = os.path.basename(fileName.replace('\\', '/')).strip()
    name = re.sub(r'[^A-Za-z0-9._-]', '_', name).lstrip('.')
    if not name:
        return None
    dest = os.path.realpath(os.path.join(filepath, target_name(name)))
    if os.path.dirname(dest) != os.path.realpath(filepath):
        return None
    return dest

#Decode in memory, re-encode as jpg. Raises on anything unsupported, oversized
#or malformed, the caller skips those attachments.
def convert_attachment(payload, dest):
    if not payload:
        raise ValueError('empty attachment')
    if len(payload) > MAX_ATTACHMENT_BYTES:
        raise ValueError('attachment larger than {limit} bytes'.format(limit=MAX_ATTACHMENT_BYTES))

    #probe first: format and dimensions are checked before any pixel is decoded
    with Image.open(BytesIO(payload)) as probe:
        image_format = probe.format
        width, height = probe.size
        if image_format not in ALLOWED_FORMATS:
            raise ValueError('unsupported format {fmt}'.format(fmt=image_format))
        if width * height > MAX_PIXELS:
            raise ValueError('{w}x{h} exceeds the pixel limit'.format(w=width, h=height))
        #catches truncated and malformed files before they hit the real decode
        probe.verify()

    #verify() consumes the handle, so open again for the actual decode
    with Image.open(BytesIO(payload)) as image:
        taken, stamp = capture_date(image)
        #honour the exif rotation now, saving as jpg drops exif (and with it
        #the GPS coordinates the phone attached)
        image = ImageOps.exif_transpose(image)
        rgb = image.convert('RGB')

    #Keep the capture date and nothing else. The gps tag the phone attached
    #is not carried over.
    keep = Image.Exif()
    if taken:
        keep[EXIF_DATETIME] = taken
    keep = keep.tobytes() if taken else None
    #Write beside the target and move it into place in one step, so the
    #frame never sees a half written or 0 byte file. The leading dot
    #keeps main.py from caching it even if one is ever left behind.
    tmp = os.path.join(os.path.dirname(dest), '.' + os.path.basename(dest) + '.partial')
    #O_EXCL: never follow a symlink or overwrite something already there
    handle = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(handle, 'wb') as fp:
            if keep:
                rgb.save(fp, 'JPEG', quality=90, exif=keep)
            else:
                rgb.save(fp, 'JPEG', quality=90)
        os.rename(tmp, dest)
        #The frame sorts by mtime, so put the capture date there too.
        #That keeps sorting a cheap stat instead of opening every
        #picture on every cache pass.
        if stamp:
            os.utime(dest, (stamp, stamp))
    except Exception:
        if os.path.lexists(tmp):
            os.unlink(tmp)
        raise


#everything below only runs when this file is executed, not when it is
#imported (the tests import the helpers above)
def main():
    #create IMAP with SSL
    imap = imaplib.IMAP4_SSL(settings['imap'], settings['port'])

    #auth
    imap.login(user['mail'], user['password'])

    status, messages = imap.select(mail_folder)

    type, data = imap.search(None, 'UNSEEN')
    mail_ids = data [0]
    id_list = mail_ids.split()

    for num in data[0].split():
        typ, data = imap.fetch(num, '(RFC822)' )
        raw_mail = data[0][1]
    
        #converts byte literal to string
        email_message = email.message_from_string(raw_mail.decode('utf-8'))
    
        #download attachements
        for part in email_message.walk():
            #..
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue
            fileName = part.get_filename()
            
            if bool(fileName):
                dest = safe_destination(fileName)
                if dest is None:
                    print('Rejected attachment name "{fileName}".'.format(fileName=fileName))
                    continue
                if os.path.lexists(dest):
                    continue
            
                #anything that is not a picture we can convert gets dropped here,
                #nothing but the re-encoded jpg is ever written to img/
                try:
                    convert_attachment(part.get_payload(decode=True), dest)
                except Exception as error:
                    print('Skipped "{fileName}": {error}'.format(fileName=fileName, error=error))
                    continue
            
                subject = str(email_message).split("Subject: ", 1)[1].split("\nTo:", 1)[0]
                print('Downloaded "{fileName}" from email to"{path}".'.format(fileName=os.path.basename(dest), path=filepath))
            
                #if more than X files, delete oldest one
                list_of_files=os.listdir(filepath)
                full_path = [os.path.join(filepath, x) for x in list_of_files]
            
                if len(list_of_files) > max_foldersize:
                    os.remove(min(full_path, key=os.path.getctime))
                    print('Exceeded max_foldersize of ' + str(max_foldersize) + ', deleting oldest file.')
        
    
        imap.store(num, '+FLAGS', '\Deleted')

    imap.close()
    imap.logout()

    print('Done...')


if __name__ == '__main__':
    main()
