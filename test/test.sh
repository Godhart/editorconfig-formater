#!/bin/bash

# Fix .txt files according to .editorconfig, take into account multiple encodings
python ../src/unifile.py -o ../.out -e "utf-8" -e "windows-1251" -i ".*?\\.txt\$" .
