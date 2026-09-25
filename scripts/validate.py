#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run image and host integration checks, retaining evidence per Blender binary."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--blender', action='append', required=True, help='Blender binary; may be repeated')
parser.add_argument('--ui', action='store_true', help='Also run a disposable windowed UI workflow test')
parser.add_argument('--reference', help='Official 2.79b binary, to regenerate reference fixtures')
parser.add_argument('--addon-path', help='Extracted package parent directory for package validation')
args = parser.parse_args()
out = ROOT / 'artifacts/validation'
out.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
if args.addon_path:
    env['BI_TEST_ADDON_PATH'] = str(Path(args.addon_path).resolve())
summary = {'runs': [], 'reference_regenerated': bool(args.reference), 'addon_path': args.addon_path}
summary_file = ROOT / 'artifacts' / ('package-validation-summary.json' if args.addon_path else 'validation-summary.json')
if args.reference:
    for filename, marker in (('scripts/fresnel_reference.py', None), ('tests/full_features.py', 'FULL_FEATURES_OK'), ('tests/full_legacy_cases.py', 'LEGACY_CASE_OK strands'), ('tests/refraction_reference.py', 'REFRACTION_REFERENCE_OK'), ('tests/import_reference.py', 'IMPORT_REFERENCE_OK')):
        with (out / ('reference-' + Path(filename).stem + '.log')).open('w') as log:
            result = subprocess.run([args.reference, '--background', '--factory-startup', '--python', str(ROOT / filename)],
                                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        text = (out / ('reference-' + Path(filename).stem + '.log')).read_text()
        if result.returncode or 'Traceback' in text or (marker and marker not in text):
            raise RuntimeError('Reference fixture generation failed: ' + filename)
tests = [('scripts/test_full_library.py', 'full-parity.json'),
         ('tests/image_cache.py', 'image-cache.json'),
         ('tests/material_workflow.py', 'material-workflow.json'),
         ('tests/render_workflow.py', 'render-workflow.json'),
         ('tests/viewport_pipeline.py', 'viewport-pipeline.json'),
         ('tests/refraction_parity.py', 'refraction-investigation/parity.json'),
         ('tests/full_nodes.py', 'full-nodes.json'), ('tests/full_import.py', 'full-import.json'),
         ('tests/import_workflow.py', 'import-workflow.json'),
         ('tests/full_pipeline.py', 'full-pipeline.json'),
         ('tests/full_case_import.py', 'legacy-cases/comparison.json'),
         ('tests/full_archive.py', 'legacy-cases/archive-comparison.json'),
         ('tests/full_stress.py', 'full-stress.json')]
if args.ui:
    tests.extend([('tests/ui_workflow.py', 'ui-workflow.json'),
                  ('tests/viewport_ui.py', 'viewport-ui.json'),
                  ('tests/texture_preview_ui.py', 'texture-preview-ui.json')])
for index, binary in enumerate(args.blender):
    version = subprocess.check_output([binary, '--version'], text=True, timeout=30).splitlines()[0]
    folder = out / ('host-' + str(index) + '-' + version.replace(' ', '-'))
    folder.mkdir(exist_ok=True)
    run = {'binary': str(Path(binary).resolve()), 'version': version, 'checks': []}
    summary['runs'].append(run)
    for script, report in tests:
        started = time.monotonic()
        log_path = folder / (Path(script).stem + '.log')
        with log_path.open('w') as log:
            result = subprocess.run([binary] + ([] if script in ('tests/ui_workflow.py', 'tests/viewport_ui.py', 'tests/texture_preview_ui.py') else ['--background']) +
                                    ['--factory-startup', '--python-exit-code', '1', '--python', str(ROOT / script)], cwd=ROOT, env=env,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=120)
        passed = result.returncode == 0 and 'Traceback' not in log_path.read_text()
        run['checks'].append({'script': script, 'passed': passed, 'seconds': round(time.monotonic()-started, 3), 'log': str(log_path.relative_to(ROOT))})
        if passed:
            shutil.copyfile(ROOT / 'artifacts' / report, folder / (Path(script).stem + '.json'))
        summary_file.write_text(json.dumps(summary, indent=2) + '\n')
        print(version, script, 'PASS' if passed else 'FAIL', flush=True)
        if not passed:
            raise RuntimeError('See ' + str(log_path))
print('VALIDATION_OK', len(summary['runs']), 'hosts')
