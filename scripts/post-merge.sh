#!/bin/bash
# Post-merge setup: keep the environment consistent after task merges.
set -e

# Sanity-compile the main app modules so a broken merge fails loudly here.
python3 -m py_compile app.py path_detection.py path_thumbnails.py pages/*.py

echo "post-merge setup OK"
