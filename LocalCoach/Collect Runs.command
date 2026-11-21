#!/bin/zsh
cd -- "${0:A:h}" || exit 1
.venv/bin/python workspace.py collect
.venv/bin/python workspace.py list
read "?Press Enter to close."
