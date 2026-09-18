#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build/package both renderers, including the complete corresponding source."""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import zipfile
from build_full import build as build_full

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--package-only', action='store_true', help='Package already-built libraries')
args = parser.parse_args()
addon = ROOT / 'addon/blender_internal'
if not args.package_only:
    subprocess.run([sys.executable, str(ROOT / 'scripts/extract_legacy.py'), '--check'], check=True)
    subprocess.run(['cmake', '-S', str(ROOT), '-B', str(ROOT / 'build'), '-DCMAKE_BUILD_TYPE=Release'], check=True)
    subprocess.run(['cmake', '--build', str(ROOT / 'build'), '--config', 'Release', '-j4'], check=True)
    subprocess.run(['cmake', '--install', str(ROOT / 'build'), '--prefix', str(ROOT / 'addon')], check=True)
    library = build_full()
else:
    library = ROOT / 'build-full/lib/libblender_internal_full.dylib'
published_name = library.name.replace('_full', '_full_v2')
shutil.copyfile(library, addon / published_name)
shutil.copyfile(ROOT / 'LICENSE', addon / 'LICENSE')
shutil.copyfile(ROOT / 'native/provenance.json', addon / 'provenance.json')
versions = json.loads((ROOT / 'versions.json').read_text())
validation_file = ROOT / 'artifacts/validation-summary.json'
validated = json.loads(validation_file.read_text())['runs'] if validation_file.exists() else []
manifest = {'addon_version': '0.2.6', 'platform': platform.system(), 'architecture': platform.machine(),
            'upstream': versions, 'native_sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
            'dependencies': json.loads((ROOT / 'third_party/manifest.json').read_text()),
            'validated_hosts': [run['version'] for run in validated if all(c['passed'] for c in run['checks'])],
            'status': 'Full native engine; see PORTING.md for host migration limitations'}
(addon / 'build_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(ROOT / 'dist').mkdir(exist_ok=True)
upstream_archive = ROOT / 'dist/blender-2.79b-source.tar.gz'
subprocess.run(['git', '-C', str(ROOT / 'blender-legacy'), 'archive', '--format=tar.gz',
                '--prefix=blender-legacy/', '-o', str(upstream_archive), versions['legacy']['commit']], check=True)
output = ROOT / 'dist' / ('blender-internal-port-' + platform.system().lower() + '-' + platform.machine() + '.zip')
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(addon.iterdir()):
        if path.is_file() and path.name not in ('libblender_internal_full.dylib', 'libblender_internal_full.so'):
            archive.write(path, path.relative_to(ROOT / 'addon'))
    # Complete source ships alongside the binary inside the same archive.
    prefix = 'blender_internal/source/'
    archive.write(upstream_archive, prefix + 'upstream/blender-2.79b.tar.gz', compress_type=zipfile.ZIP_STORED)
    for directory in ('full', 'native', 'scripts', 'tests', 'patches', 'docs'):
        for path in sorted((ROOT / directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                archive.write(path, prefix + str(path.relative_to(ROOT)))
    for path in sorted(addon.iterdir()):
        if path.suffix in ('.py', '.json'):
            archive.write(path, prefix + str(path.relative_to(ROOT)))
    for path in sorted((ROOT / 'third_party/archives').iterdir()):
        archive.write(path, prefix + str(path.relative_to(ROOT)), compress_type=zipfile.ZIP_STORED)
    for name in ('CMakeLists.txt', 'LICENSE', 'README.md', 'versions.json', 'third_party/manifest.json'):
        archive.write(ROOT / name, prefix + name)
    archive.writestr(prefix + 'BUILD.txt',
        'macOS ARM64, Xcode command line tools, CMake, Python 3, Git.\n'
        'From this source directory: python3 scripts/build_full.py\n'
        'This extracts the included upstream archive, applies the host patches,\n'
        'builds all four included dependencies statically and builds the dylib.\n'
        'No dependency downloads are required. All installation stays in this directory.\n'
        'Full engine source: Blender 2.79b, GPL-2.0-or-later.\n'
        'Third-party licenses are included in their corresponding source archives.\n')
print(output)
