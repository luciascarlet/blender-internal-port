#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the pinned static image/font dependencies entirely inside this workspace."""
from pathlib import Path
import hashlib
import json
import subprocess
import urllib.request
import platform
import shutil
from build_platform import cmake_defaults, static_library

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
        if platform.system() not in item.get('platforms', [platform.system()]):
            continue
        archive = BASE / 'archives' / item['archive']
        if not archive.exists():
            urllib.request.urlretrieve(item['url'], archive)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != item['sha256']:
            raise RuntimeError('Source archive checksum mismatch: ' + str(archive))
        source = BASE / 'sources' / item['directory']
        if not source.exists():
            run(['tar', '-xf', archive, '-C', BASE / 'sources'])
        if name == 'pthreads':
            # Build the DLL so pthreads4w manages process/thread attachment itself.
            subprocess.run(['nmake', '/nologo', 'VC'], cwd=source, check=True)
            for subdir in ('include', 'lib', 'bin'):
                (PREFIX / subdir).mkdir(parents=True, exist_ok=True)
            for header in ('pthread.h', 'sched.h', 'semaphore.h', '_ptw32.h'):
                shutil.copyfile(source / header, PREFIX / 'include' / header)
            shutil.copyfile(source / 'pthreadVC3.lib', PREFIX / 'lib/pthreadVC3.lib')
            shutil.copyfile(source / 'pthreadVC3.dll', PREFIX / 'bin/pthreadVC3.dll')
            continue
        directory = ROOT / 'build-deps' / name
        options = cmake_defaults() + ['-DBUILD_SHARED_LIBS=OFF',
                   '-DCMAKE_INSTALL_PREFIX=' + str(PREFIX), '-DCMAKE_PREFIX_PATH=' + str(PREFIX)]
        if name != 'zlib':
            options += ['-DZLIB_LIBRARY=' + str(static_library(PREFIX, 'z')),
                        '-DZLIB_INCLUDE_DIR=' + str(PREFIX / 'include')]
        options += item['options']
        if name == 'jpeg':
            options += ['-DWITH_SIMD=OFF', '-DWITH_CRT_DLL=ON']
        run(['cmake', '-S', source, '-B', directory] + options)
        run(['cmake', '--build', directory, '--config', 'Release', '-j4'])
        run(['cmake', '--install', directory, '--config', 'Release'])
    return PREFIX


if __name__ == '__main__':
    print(build())
