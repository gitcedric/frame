#!/bin/sh
# Runs the frame and serves it to a browser, so the GUI can be watched live
# without installing an X server on the host.
#
#   podman run --rm -p 8080:8080 frame-test sh tests/gui.sh
#   open http://localhost:8080/vnc.html?autoconnect=1&resize=scale
#
# Mount your own pictures to see those instead, heic included:
#   podman run --rm -p 8080:8080 -v ~/Pictures:/pictures:ro frame-test sh tests/gui.sh
set -e

IMG=/frame/img
mkdir -p "$IMG"

if [ -d /pictures ]; then
    # run them through the same converter mail delivery uses, a raw heic
    # would not be displayable
    rm -f "$IMG"/* 2>/dev/null || true
    python3 - <<'PY'
import os, sys
sys.path.insert(0, '/frame')
import readmail

src, taken = '/pictures', 0
for name in sorted(os.listdir(src)):
    if taken >= 25:
        break
    full = os.path.join(src, name)
    if not os.path.isfile(full):
        continue
    dest = readmail.safe_destination(name)
    if dest is None or os.path.lexists(dest):
        continue
    try:
        readmail.convert_attachment(open(full, 'rb').read(), dest)
        print('  converted %s -> %s' % (name, os.path.basename(dest)))
        taken += 1
    except Exception as error:
        print('  skipped   %s: %s' % (name, str(error)[:60]))
print('  %d picture(s) from /pictures' % taken)
PY
elif [ -z "$(ls -A "$IMG" 2>/dev/null)" ]; then
    python3 - <<'PY'
from PIL import Image, ImageDraw
d = '/frame/img/'
for name, size, colour, label in [
    ('01-landscape.jpg', (1600, 1000), (38, 70, 110), 'LANDSCAPE 1600x1000'),
    ('02-portrait.jpg',  (1000, 1600), (110, 48, 38), 'PORTRAIT 1000x1600'),
    ('03-square.jpg',    (1200, 1200), (40, 105, 62), 'SQUARE 1200x1200'),
]:
    im = Image.new('RGB', size, colour)
    dr = ImageDraw.Draw(im)
    dr.rectangle([10, 10, size[0] - 10, size[1] - 10], outline=(255, 255, 255), width=8)
    dr.line([(0, 0), size], fill=(255, 255, 255), width=4)
    dr.line([(0, size[1]), (size[0], 0)], fill=(255, 255, 255), width=4)
    for i in range(6):
        dr.text((40, 40 + i * 30), label, fill=(255, 255, 255))
    im.save(d + name)
PY
fi

SCREEN=${SCREEN:-1280x800}
export DISPLAY=:99

Xvfb :99 -screen 0 "${SCREEN}x24" >/dev/null 2>&1 &
sleep 2
# Tk asks the window manager for fullscreen, so there has to be one. Without
# it the window would stay 1x1 and the screen would be black.
matchbox-window-manager -use_titlebar no >/dev/null 2>&1 &
sleep 1
python3 -u /frame/main.py &
sleep 2

# -nopw is fine, nothing is reachable beyond the port you publish yourself
x11vnc -display :99 -forever -shared -nopw -quiet -bg >/dev/null 2>&1
sleep 1

echo ''
echo "  frame is live at  http://localhost:8080/vnc.html?autoconnect=1&resize=scale"
echo '  ctrl-c to stop'
echo ''
exec websockify --web=/usr/share/novnc 8080 localhost:5900
