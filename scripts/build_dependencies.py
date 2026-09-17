#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the pinned static image/font dependencies entirely inside this workspace."""
from pathlib import Path
import hashlib
import json
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'third_party'
PREFIX = ROOT / 'build-deps/install'


def run(args):
    subprocess.run([str(x) for x in args], check=True)


def build():
    manifest = json.loads((BASE / 'manifest.json').read_text())
    (BASE / 'archives').mkdir(parents=True, exist_ok=True)
    (BASE / 'sources').mkdir(parents=True, exist_ok=True)
    for name, item in manifest.items():
        archive = BASE / 'archives' / item['archive']
        if not archive.exists():
            urllib.request.urlretrieve(item['url'], archive)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != item['sha256']:
            raise RuntimeError('Source archive checksum mismatch: ' + str(archive))
        source = BASE / 'sources' / item['directory']
        if not source.exists():
            run(['tar', '-xf', archive, '-C', BASE / 'sources'])
        directory = ROOT / 'build-deps' / name
        options = ['-DCMAKE_BUILD_TYPE=Release', '-DBUILD_SHARED_LIBS=OFF',
                   '-DCMAKE_POSITION_INDEPENDENT_CODE=ON', '-DCMAKE_OSX_DEPLOYMENT_TARGET=11.0',
                   '-DCMAKE_INSTALL_PREFIX=' + str(PREFIX), '-DCMAKE_PREFIX_PATH=' + str(PREFIX)]
        if name != 'zlib':
            options += ['-DZLIB_LIBRARY=' + str(PREFIX / 'lib/libz.a'),
                        '-DZLIB_INCLUDE_DIR=' + str(PREFIX / 'include')]
        options += item['options']
        run(['cmake', '-S', source, '-B', directory] + options)
        run(['cmake', '--build', directory, '-j8'])
        run(['cmake', '--install', directory])
    return PREFIX


if __name__ == '__main__':
    print(build())
