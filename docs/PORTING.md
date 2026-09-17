# Full-engine integration and readiness

## Architecture

Modern Blender evaluates its dependency graph. The Python adapter copies meshes,
local coordinates, transforms, material assignments, UV layers, vertex colors,
custom normals, cameras, lights, textures and image pixels into an owned legacy
Main database. An RNA bridge sets original 2.79 properties and constructs original
shader/texture node trees. `RE_BlenderFrame` runs the original Internal pipeline.
Combined and selected pass buffers return as scene-linear floats to modern Blender.

The native library links the original BKE, DNA, RNA, node and renderer code. Its
export list exposes only `bi_full_*`, preventing the old internal symbols from
colliding with the host Blender. It uses no modern C++ ABI or borrowed Blender
pointers. A process-wide lock serializes complete export/render operations because
the legacy engine has global state. Handle epochs reject stale handles after a
scene reset or file load. Python callbacks are cleared before their owners expire.
Legacy Python support is compiled out and script auto-execution is disabled.

The archive source loads original DNA directly and uses the original dependency
graph, particle and animation evaluation. It is a separate workflow from migration
into modern editable objects; differences between those workflows are explicit.

## Native patches

`patches/legacy-full-host.patch` contains the source changes:

* Current macOS dependency/platform configuration and headless ARM64 compilation.
* Fix the upstream no-Python numeric-input declaration.
* Exclude the old Finder launch hook from headless builds.
* Store the render result/part rwlocks by pointer. The original code copies Render
  structures by value (`R = *re`); copying macOS ARM64 pthread rwlocks caused a
  reproducible deadlock. The patch allocates/frees each lock with its Render owner
  and makes structure copies share the lock, preserving existing lock calls.
* Add the isolated shared-library target and exported-symbol list.

The original shading, scanline and ray-tracing algorithms are unchanged. Floating
point architecture/compiler differences can still affect discontinuities, grazing
rays, sampling and checker boundaries. Average image error alone does not prove
pixel equality: the reports include both mean and maximum channel error.

## Implemented and exercised

| Workflow or feature | Evidence |
| --- | --- |
| Original scanline renderer and ray tracer in modern Blender | Full demo, import and archive renders |
| All five legacy diffuse and specular models | Demo and Fresnel reference suite |
| Mirror reflections and ray refraction/transparency | Matched official 2.79b sphere/card scene |
| 31 original shader node types | Registration/export test, grouped-curve and textured-material image comparisons |
| Original texture node evaluation | Per-type export checks and checker/curve graph comparison |
| Editable legacy shader groups, curves and ramps | Export, duplication ownership and saved-file reload checks |
| 18 material texture slots; procedural/image textures | Packed image, UV and bump regression |
| UV layers and vertex color attributes | Original-file import comparisons |
| Ambient occlusion, SSS, area lights | Joint reference fixture |
| Original antialiasing and pixel filter | Eight-sample Mitchell-filter fixture |
| Depth, normal, UV, color, emission, diffuse, specular, shadow, AO, environment, indirect, reflection, refraction, object/material index and mist passes | Native buffers and modern multilayer EXR integration |
| Render borders, with and without crop | Pixel/dimension comparison against full reference render |
| Cancellation and render after cancellation | Host pipeline test |
| Legacy settings migration | Original material/world/light/texture settings and shader graphs survive import |
| Animation motion blur in original-file mode | Official 2.79b animated-object comparison |
| Legacy particle strands in original-file mode | Official 2.79b hair fixture, including modern-host render |
| Portable macOS ARM64 runtime | `otool -L` allows only macOS system libraries |

Node type export coverage is not exhaustive coverage of every operation, texture
submode, property combination or animation path. Texture nodes introduced after
2.79 are rejected; RGB combine/separate nodes are mapped back to the old RGB nodes.

## Measured comparisons

Reports are generated, not hand-authored:

* `artifacts/full-parity.json`: four original Fresnel cases.
* `artifacts/full-import.json`: migrated mirror/glass/shader-node scene. Mean error
  approximately 1.2e-7 per RGBA channel in the initial migration verification.
* `artifacts/legacy-cases/comparison.json`: six editable migration cases.
* `artifacts/legacy-cases/archive-comparison.json`: eight original-file cases,
  including motion blur and strands.
* `artifacts/full-nodes.json`: node/export/storage/reload checks.
* `artifacts/full-pipeline.json`: passes, borders, cancellation and stale handles.
* `artifacts/full-stress.json`: 100 scene resets/loads/renders, deterministic output
  and measured peak-memory growth after warm-up.
* `artifacts/package-source-build.log`: complete offline rebuild from the source
  shipped in the ZIP. Package host reports are saved separately.

Samples with area lighting, image edges, hair and hard procedural checker boundaries
have localized differences much larger than their image-wide mean. These need
broader image review and are not described as bit-identical.

## Remaining work before a comprehensive production release

* Blender 5.2.2 LTS and Blender 5.3.0 Alpha passed the seven integration suites.
  Exact modern-version coverage is recorded by `artifacts/validation-summary.json`;
  don't infer tested versions from the minimum add-on version or source checkout.
* The modern evaluated-scene path does not yet export temporal geometry for motion
  blur or migrate removed particle/strand systems. Original-file mode covers these
  original scenes, but does not make them editable modern particle systems.
* Modern volume objects, point clouds, hair curves and grease-pencil geometry do
  not have migration exporters. They produce a clear render error. Legacy material
  volume shading is compiled, but broad volume regressions are still needed.
* Panoramic camera mapping and modern multiview/stereo integration remain unverified
  and are explicitly rejected in the modern scene path.
* Texture storage options not exposed through modern RNA, texture/world/light
  object-coordinate links, environment maps, image sequences/UDIM behavior and
  shader/texture graph recursion need more coverage and migration work.
* The native build uses the legacy lite configuration: optional smoke solver,
  Freestyle, legacy compositor, OpenEXR decoder and full OpenColorIO integration
  are not included. Modern Blender handles final image color management/output;
  modern image pixels can be transferred into the library, including float images.
* Legacy compositor/sequencer nodes are not migrated or run by archive-source
  rendering. Modern compositing consumes the returned passes.
* Render-layer conversion, baking, persistent/progressive viewport rendering,
  preview thumbnails and broader undo/reload stress need
  dedicated integration work. Material previews are currently disabled.
* The importer rolls back newly appended datablocks after a restoration failure;
  this is checked with failure injection. Broader malformed-file and linked-library
  coverage is still needed.
* Native build and package validation on Windows, Linux and Intel macOS remains.

The full pipeline is substantially beyond the initial proof of concept. These
remaining boundaries mean it must still be labeled a development port.
