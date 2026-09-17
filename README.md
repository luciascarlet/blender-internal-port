# Blender Internal for modern Blender

This project builds the **original Blender 2.79b Internal renderer** as an isolated
native library and integrates it with modern Blender's RenderEngine API. The default
backend executes the original scanline rasterizer, shading and texture nodes,
shadow system, acceleration structures, reflection and refraction code. The earlier
kernel-only experiment remains available for comparisons.

**Status: development build, not yet a comprehensive production-ready port.** The
native engine and the tested workflows work. Modern data migration still has gaps;
see [the compatibility and readiness matrix](docs/PORTING.md). The implementation
is an add-on plus a native library, not a patched modern Blender executable.

## Try it

Validated hosts: Blender 5.2.2 LTS and Blender 5.3.0 Alpha on macOS ARM64.

The macOS ARM64 package is `dist/blender-internal-port-darwin-arm64.zip`. It includes
the native libraries, Python adapter, full upstream source archive, dependency
sources, patches, and build scripts. No 2.79 executable or MacPorts installation
is needed at runtime.

Install the ZIP using Blender Preferences → Add-ons → Install from Disk, enable
**Blender Internal — Experimental Port**, and choose **Blender Internal
(Experimental Port)** in the render engine selector. Installation has not been
made globally by the build scripts.

There are two scene sources under Render properties:

* **Current Scene:** render modern evaluated geometry with legacy materials.
  Material properties provide the original diffuse/specular models, full legacy
  material settings, reflection/refraction, texture slots, and a legacy node tree.
  Choose **Blender Internal Nodes** in the node editor to edit that material tree.
* **Original Legacy File:** choose an original 2.79 `.blend` file. Its scene data,
  nodes, particles and animation are evaluated directly by the embedded old engine,
  with the current frame, output size, render border and requested passes supplied
  by the modern host. This does not modify the source file. The optional scene name
  selects a scene from that file. Original compositor/sequencer output is not used.

To migrate an old scene into editable modern data, use **File → Import → Blender
Internal 2.79 (.blend)**. This reads Internal settings and shader nodes through the
old DNA/RNA implementation before modern Blender's versioning removes them. It
appends scenes and datablocks and preserves name mappings when names collide.
Use the archive source for old particle systems or motion blur that the modern
migration path cannot yet preserve faithfully.

Legacy render passes are selectable in View Layer properties. Full legacy world
controls include ambient occlusion and mist. Color management and final file output
belong to modern Blender; **Standard** is useful for comparisons with 2.79's
**Default** view transform.

## Fresnel investigation

The flat yellow sphere and jagged shadow terminator in the reported screenshot also
occur in the official 2.79b renderer with the original demo parameters. The legacy
**diffuse Fresnel** model is not a physically based reflective Fresnel shader. With
factor 0.7 and power 1.5 its response saturates; factor 3.14 produces a rim-like
response. The original formula is preserved.

Reference fixtures are in `artifacts/fresnel/`. Rendering those same original files
through the full native library gives exact equality for two variants and maximum
linear-channel error around 0.000011 for the other two. The initial kernel driver
had additional no-shadow differences; the default full engine removes that driver.

## Build and test

Source revisions are pinned in `versions.json`:

* Modern source: Blender v5.2.2, `d13f752e3b9c4f8c261cda552b1021f8bcc0382c`.
* Legacy source: Blender v2.79b, `f4dc9f9d68bddaa206b692e1d077d1a1f2bb1528`.

Prerequisites for the current build: macOS ARM64, Xcode command line tools, CMake,
Python 3 and Git. Work remains on Linux, Windows and Intel macOS build validation.

```sh
python3 scripts/clone_sources.py
python3 scripts/build.py
```

The full engine build uses a separate `blender-legacy-port` worktree and the patch
in `patches/legacy-full-host.patch`. It does not edit either pristine source clone.
The four image/font dependencies are built statically under `build-deps`; archive
URLs, versions and SHA-256 checksums are pinned in `third_party/manifest.json`.
The source folder inside the packaged ZIP can build the full library offline:

```sh
python3 scripts/build_full.py
```

Tests run in background Blender. They use real original-renderer comparisons, not
only formula/unit checks. The official 2.79b reference fixture generator requires
its matching executable. `scripts/validate.py --help` describes the test runner.
Reports and images are written to `artifacts/`.

This software and the original Blender code are GPL-2.0-or-later. The full license
is in `LICENSE`. Dependency license texts ship with their corresponding sources.
