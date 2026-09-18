#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reproduce the source checkouts without modifying an existing checkout."""
import json
import argparse
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[1]
versions = json.loads((ROOT / 'versions.json').read_text())
parser = argparse.ArgumentParser()
parser.add_argument('--legacy-only', action='store_true', help='Only fetch the source needed to build the add-on')
args = parser.parse_args()
for name in (('legacy',) if args.legacy_only else ('modern', 'legacy')):
    version = versions[name]
    destination = ROOT / version['directory']
    if not destination.exists():
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', version['tag'], versions['upstream'], str(destination)], check=True)
    actual = subprocess.check_output(['git', '-C', str(destination), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != version['commit']:
        raise SystemExit('Existing checkout has a different commit; leaving it unchanged: ' + str(destination))
    print(name + ': ' + actual)
