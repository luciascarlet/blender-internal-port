#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate an inventory, not a claim that all migration blockers are enumerated."""
import json
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
legacy = ROOT / 'blender-legacy'
modern = ROOT / 'blender-modern'
render = legacy / 'source/blender/render'
sources = sorted(p for p in render.rglob('*') if p.suffix in ('.c', '.cpp', '.h'))
modern_headers = {p.name for p in modern.rglob('*') if p.suffix in ('.h', '.hh', '.hpp')}
includes = set()
for path in sources:
    includes.update(re.findall(r'^#\s*include\s*"([^"]+)"', path.read_text(), re.M))
provenance = json.loads((ROOT / 'native/provenance.json').read_text())
report = {
    'legacy_render_source_files': len(sources),
    'legacy_render_source_lines': sum(len(p.read_text().splitlines()) for p in sources),
    'ported_functions': sum(len(v['functions']) for v in provenance['files'].values()),
    'legacy_quoted_include_names_not_present_in_modern_tree': sorted(name for name in includes if Path(name).name not in modern_headers),
    'caveat': 'Header names may have been renamed or replaced. This is an inventory, not a compiler diagnostic.',
    'host_adapter': 'Modern bpy.types.RenderEngine and evaluated dependency graph, using a standalone C ABI',
    'native_modern_blender_binary_rebuilt': False,
}
output = ROOT / 'docs/source-audit.json'
output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
