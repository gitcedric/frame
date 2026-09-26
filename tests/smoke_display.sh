#!/bin/sh
# Starts the real main.py against a virtual display. The frame must cache only
# the files it can show, survive a corrupt one, and keep running.
set -e

IMG=/frame/Frame/img
mkdir -p "$IMG"
rm -f "$IMG"/* "$IMG"/.[!.]* 2>/dev/null || true

python3 - <<'PY'
from PIL import Image
d = '/frame/Frame/img/'
Image.new('RGB', (900, 600), (10, 120, 90)).save(d + 'landscape.jpg')
Image.new('RGB', (600, 900), (120, 10, 90)).save(d + 'portrait.PNG')
open(d + 'ADD_IMAGE_HERE', 'w').write('')          # the placeholder in the repo
open(d + 'notes.txt', 'w').write('x')              # not a picture
open(d + '.hidden.jpg', 'w').write('x')            # dotfile junk
open(d + 'corrupt.jpg', 'wb').write(b'\xff\xd8\xff\xe0broken')
PY

# -u because timeout kills the app and buffered output would be lost;
# started from / on purpose, the frame must not depend on the cwd
out=$(cd / && timeout 12 xvfb-run -a python3 -u /frame/Frame/main.py 2>&1 || true)
echo "$out" | sed 's/^/  /'

fail=0
echo "$out" | grep -q '3 files cached!' \
    || { echo '  FAIL only jpg/PNG/corrupt.jpg should be cached'; fail=1; }
echo "$out" | grep -q 'Skipping "corrupt.jpg"' \
    || { echo '  FAIL the corrupt file was not skipped'; fail=1; }
# the frame is started from / here on purpose, a picture must still be found
echo "$out" | grep -q 'Skipping "landscape.jpg"' \
    && { echo '  FAIL a good jpg was skipped'; fail=1; }
echo "$out" | grep -q 'Skipping "portrait.PNG"' \
    && { echo '  FAIL a good png was skipped'; fail=1; }
echo "$out" | grep -qi 'traceback' \
    && { echo '  FAIL the slideshow thread crashed'; fail=1; }

[ "$fail" -eq 0 ] && echo '  ok   the frame ignored the junk and survived the corrupt file'
exit $fail
