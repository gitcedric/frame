# Test image for the frame. Debian bookworm is what current Raspberry Pi OS is
# built on, so this installs the same packages the README asks for and catches
# problems that would only show up on the Pi.
#
#   podman build -t frame-test .        (or docker build)
#   podman run --rm frame-test
FROM debian:bookworm-slim

# The packages from the README, plus libheif for HEIC and xvfb so the Tk
# window can be opened without a real display.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-tk \
        python3-pil.imagetk \
        python3-pip \
        libheif1 \
        xvfb \
        xauth \
        matchbox-window-manager \
        x11vnc \
        novnc \
        websockify \
    && rm -rf /var/lib/apt/lists/*

# Debian 12 marks the system python as externally managed and refuses a plain
# `pip3 install`. Recent Raspberry Pi OS needs the same flag.
RUN pip3 install --break-system-packages --no-cache-dir pillow-heif

WORKDIR /frame
COPY main.py readmail.py rotate.py ./
COPY img/ img/
COPY tests/ tests/

# Config.json is untracked and kept out of the image, mail credentials
# have no business in a container image. Tests use a dummy.
COPY tests/Config.test.json Config.json

EXPOSE 8080
CMD ["sh", "tests/run.sh"]
