#!/bin/sh
# Everything the container checks. Any failure fails the run.
set -e
echo '== attachment handling =='
python3 /frame/tests/test_images.py
echo
echo '== display, real main.py on a virtual screen =='
sh /frame/tests/smoke_display.sh
echo
echo 'ALL TESTS PASSED'
