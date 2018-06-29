#!/bin/bash

sudo apt-get install git libsqlite3-dev
sudo apt-get install build-essential binutils-multiarch ncurses-dev alien
sudo apt-get install gcc-arm-linux-gnueabi
sudo apt-get install --install-recommends gcc-4.7-aarch64-linux-gnu
sudo ln -s /usr/bin/aarch64-linux-gnu-gcc-4.7 /usr/bin/aarch64-linux-gnu-gcc
sudo apt-get install python-pip
pip install -r ./requirements.txt
