# Unifile

A python script to unify your files indents, encoding, line endings according to specified rules or editorconfig file


# Prerequisites

Install requirements `python -m pip install src/requirements.txt`

# Usage

Trivial case to process most of files: `python unifile.py <path-to-file or path-to-folder>` which would fix files right in place.

If specified path is a folder, then it should contain text files only, including nested folders, or avoid blobs and other files with `--include` and `--exclude` options. If there is files encodings other than `utf-8` - specify all possible encodings via `--encoding` options.

Check help for other cases with `python unifile.py -h`.

Checkout `test/test.sh` for example.
