#!/usr/bin/env python3
"""Entry point for the GTA VI trophy rarity forecaster.

The grader drops exactly one case file into the input folder and
expects one forecast file per case in the output folder.  Locally
the two folders can be pointed elsewhere with the MAKEFUN_INPUT_DIR
and MAKEFUN_OUTPUT_DIR environment variables; inside the grader
both fall back to /input and /output.  All modelling lives in the
model module shipped beside this file.
"""

import json
import os
import sys
from pathlib import Path

# The grader starts Python with this file's folder off the import
# path, so put the folder back at the front before importing model.
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from model import build_forecast


def resolve_folders():
    """Input and output folders for this run."""
    source = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
    sink = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))
    return source, sink


def process_case_file(path, sink):
    """Read one .in file and write its matching .out file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    forecast = build_forecast(payload)
    text = json.dumps(forecast, separators=(",", ":")) + "\n"
    (sink / (path.stem + ".out")).write_text(text, encoding="utf-8")


def run():
    source, sink = resolve_folders()
    sink.mkdir(parents=True, exist_ok=True)
    # Name order keeps repeated runs byte-for-byte identical.
    for case_path in sorted(source.glob("*.in")):
        process_case_file(case_path, sink)


if __name__ == "__main__":
    run()
