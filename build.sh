#!/usr/bin/env bash
# exit on error
set -o errexit

# Storage directory download and install zbar manually
echo "Installing zbar..."
mkdir -p libzbar
cd libzbar
# Download Debian package for zbar
curl -o libzbar0.deb http://ftp.de.debian.org/debian/pool/main/z/zbar/libzbar0_0.23.92-9_amd64.deb
dpkg -x libzbar0.deb .
cd ..

# Export library path so python can find it
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/libzbar/usr/lib/x86_64-linux-gnu/

# Install python dependencies
pip install -r requirements.txt