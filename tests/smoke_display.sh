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
open(d + 'empty.jpg', 'wb').write(b'')             # the 0 byte file seen on the pi
PY

# -u because timeout kills the app and buffered output would be lost;
# started from / on purpose, the frame must not depend on the cwd
out=$(cd / && timeout 12 xvfb-run -a python3 -u /frame/Frame/main.py 2>&1 || true)
echo "$out" | sed 's/^/  /'

fail=0
echo "$out" | grep -q '4 files cached!' \
    || { echo '  FAIL only the jpg/PNG/corrupt/empty files should be cached'; fail=1; }
echo "$out" | grep -q 'Skipping "empty.jpg"' \
    || { echo '  FAIL the 0 byte file was not skipped'; fail=1; }
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

# An empty img/ used to spin the slideshow thread at full speed. With
# displaytime at 1s a few seconds may only produce a handful of passes,
# a spinning loop produces thousands.
rm -f "$IMG"/* "$IMG"/.[!.]* 2>/dev/null || true
idle=$(cd / && timeout 8 xvfb-run -a python3 -u /frame/Frame/main.py 2>&1 || true)
passes=$(echo "$idle" | grep -c '0 files cached!')
echo "  empty folder produced $passes cache passes in 8s"
if [ "$passes" -gt 40 ]; then
    echo '  FAIL the loop is spinning on an empty folder'
    fail=1
else
    echo '  ok   the frame idles instead of spinning when there is nothing to show'
fi

# A configured files.path may be absolute, as it is on the deployed pi.
# Joining it onto the script directory used to produce a path that does not
# exist, so nothing was ever cached and the screen stayed black.
cp /frame/Frame/Config.json /tmp/Config.json.bak
python3 - <<'PY'
import json
c = json.load(open('/frame/Frame/Config.json'))
c['files']['path'] = '/frame/Frame/img/'      # absolute, with trailing slash
json.dump(c, open('/frame/Frame/Config.json', 'w'), indent=4)
PY
python3 - <<'PY'
from PIL import Image
Image.new('RGB', (800, 600), (20, 90, 40)).save('/frame/Frame/img/abs.jpg')
PY
absout=$(cd / && timeout 8 xvfb-run -a python3 -u /frame/Frame/main.py 2>&1 || true)
cp /tmp/Config.json.bak /frame/Frame/Config.json
if echo "$absout" | grep -q '0 files cached!'; then
    echo '  FAIL an absolute files.path cached nothing'
    fail=1
else
    echo "  ok   an absolute files.path works ($(echo "$absout" | grep -m1 'files cached!'))"
fi

exit $fail
