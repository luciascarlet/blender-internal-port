#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reproduce the source checkouts without modifying an existing checkout."""
import json
from pathlib import Path
import subprocess
ROOT = Path(__file__).resolve().parents[1]
versions = json.loads((ROOT / 'versions.json').read_text())
for name in ('modern', 'legacy'):
    version = versions[name]
    destination = ROOT / version['directory']
    if not destination.exists():
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', version['tag'], versions['upstream'], str(destination)], check=True)
    actual = subprocess.check_output(['git', '-C', str(destination), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != version['commit']:
        raise SystemExit('Existing checkout has a different commit; leaving it unchanged: ' + str(destination))
    print(name + ': ' + actual)
