# Material, node and render workflows (0.2.3)

Select an object and open **Material Properties**. The top panel has Blender's
material slot list, add/remove/reorder controls, Object/Data linking, material
browser, rename, copy and unlink controls. In Edit Mode it also has **Assign**,
**Select**, and **Deselect** for assigning materials to selected faces.

Choose **New** or select an existing material. Change the rendered base color in
**Diffuse → Diffuse Color**. Specular, shading, transparency, mirror, SSS,
texture slots and material ramps have their own panels. Halo and volume settings
appear for those material types. Early adapter materials and imported legacy
materials use the same visible controls; their stored color/shader parameters are
resolved without changing their existing appearance.

## Nodes

In **Blender Internal Nodes**, the header follows the active object's material
slot. **New Material Nodes** can create and assign a material to an empty object.
The tree browser selects a graph *on that material*, including graphs previously
created by the old, unattached generic New button. **New** creates a default
Material → Output graph, or copies an existing graph. **Use Nodes** disables the
graph without discarding it. **Edit Internal Nodes** opens and frames that graph.
Pinning keeps the current graph visible when object selection changes.

Legacy Material nodes show the colors of their referenced material. Their input
sockets override that material only when linked, as in 2.79; ignored, unconnected
socket defaults are no longer presented as editable controls. RGB and Value nodes
expose their output values. Group nodes offer **New** and **Edit Group**; Tab enters
an active group or returns to its parent. The sidebar exposes the group interface.
Blender's built-in automatic Group/Ungroup commands are not implemented for this
custom tree type; create a Group node and edit its contents instead.

Material copy and user-count buttons copy the legacy root graph and retarget its
self-material nodes. This keeps the copied material's color independently editable.
Explicitly assigning the same node tree to multiple materials still shares it,
like other Blender node groups. References to other materials or nested groups
remain references; copying does not duplicate an entire material library.

## Textures and ramps

Add a texture slot, choose **New** or an existing texture, then choose its type.
Image textures expose **New/Open** image controls. Texture settings, mapping and
influence are collapsible sections. **Use Texture Nodes → Edit Texture Nodes**
opens the texture's actual embedded graph in a pinned editor. Use **Edit Internal
Nodes** to return to the material graph.

Diffuse and specular material ramps have color-stop editors and native legacy
blend/input settings. Imported ramps retain their stops. Shared ramp storage has
an explicit **Make Ramps Single User** action before editing.

## Render Properties

Select the **Full Legacy Renderer** backend. Its render controls no longer require
turning on a separate full-settings switch:

* **Anti-Aliasing:** enable, 5/8/11/16 samples, original pixel filters and filter width.
* **Shading:** shadows, textures, SSS, environment maps, ray tracing, world-space
  shading and Sky/Transparent alpha.
* **Ray Tracing:** acceleration method, octree resolution or instancing, local coordinates.
* **Performance:** automatic/fixed thread count and tile dimensions.
* **Edge Enhancement:** enable, threshold and color.
* **Fields:** order and still fields. Current-scene mode uses still fields;
  original-file mode can evaluate the temporal offset between fields.
* **Sampled Motion Blur:** samples and shutter in original-file mode. Current-scene
  temporal geometry is not yet exported, so that mode cannot enable motion blur.
* **Simplify:** modern evaluated subdivision limits plus legacy shadow/SSS/AO quality;
  original-file mode also exposes old particle and triangulation limits.

The top panel includes Render, Animation and Lock Interface. World background and
ambient fill live in **World Properties**. **Output Properties** contain native
resolution/aspect/frame range and time stretching, file format and encoding, metadata/stamping,
compositing, sequencer and dither controls. Render color-management controls include
their native curves, white-balance and advanced subpanels. These host controls are
not overwritten by hidden legacy defaults or applied twice inside the library.

Existing files keep their effective AA, shadow and alpha settings. Editing one of
these controls upgrades their storage together without resetting the others.
Advanced options now work even in files made without the old full-settings switch.

In **Original Legacy File** mode, render settings initially come from that file.
Choose **Load File Render Settings** to inspect and edit them. This copies the
settings and enables **Override File Render Settings**; turning the override off
uses the file settings again. The source file is never written. Frame, output size,
border and selected passes continue to come from the modern host. Pixel aspect and
animation timing in this mode remain those of the original file.

The **Integration Status** panel identifies unsupported native build features:
Freestyle, baking, Full Sample and Save Buffers. Enabled unsupported imported
settings produce a clear error and can be disabled there. They are not presented as
working features. Material preview thumbnails remain unavailable.

## Rendered viewport

Use the **Current Scene** source and **Full Legacy Renderer**, then choose the
rightmost shading sphere in the 3D Viewport, or press **Z, R**. This ports the
2.79 Internal rendered-preview pipeline: the original scanline/ray renderer starts
at low resolution and refines the same scene database up to the viewport size.
Materials, legacy nodes, lights, shadows, mirrors and refraction use the same
legacy shading implementation as F12. The camera follows the viewport, including
perspective, orthographic and camera views; a scene camera is not required.

**Render Properties → Viewport Preview** exposes **Pause Preview**, final
**Resolution** percentage and **Start Resolution**. Navigation and scene edits
cancel obsolete jobs. Rendering runs on a worker using copied scene commands;
Blender data and GPU drawing stay on the main thread. F12 takes priority and the
viewport resumes after it finishes. Multiple viewports share the renderer queue.
Settled views stop requesting redraws once their image/status has been displayed.

This is a CPU-rendered progressive preview. Its responsiveness depends on geometry,
textures, ray depth and lighting; exporting a large changed scene still takes time
on the main thread. Like the old preview, it omits antialiasing, motion blur,
fields, compositing and output effects. F12 remains the final-quality render.
Render borders are currently ignored in preview (the full viewport is drawn).
Preview follows viewport visibility, local view and evaluated viewport modifiers,
including objects hidden only from final rendering. Original-file mode requires
importing the scene and switching to Current Scene for viewport editing.

## Musgrave bump on a mirror

Add a legacy texture slot to the mirror material and create a **Musgrave** texture.
Under the slot's **Influence**, disable **Diffuse Color**, enable
**Normal**, and start with **Normal Factor 0.1**. The texture perturbs the reflected
surface normal. Adjust the texture's Noise Size and the slot's Mapping Scale to
control the size of the pattern.

For a texture-node graph, enable **Use Texture Nodes**, connect Musgrave **Color**
to the texture **Output Color**, and keep the slot's Normal influence enabled.
Changes to the texture or graph update the rendered viewport. Merely drawing the
slot's Remove/Edit Nodes buttons must not trigger rendering; operator settings
are excluded from the material/node update callbacks.

## Tinted ray transparency

For colored glass, enable **Transparency**, choose **Raytrace**, lower **Alpha**,
and set **IOR** above 1. The diffuse color supplies the transmission tint, but
**Transparency → Filter** controls its strength: zero leaves transmitted light
untinted. Start with Filter 0.8 and adjust for the desired result. Keep **Traceable**
enabled so other reflection/refraction rays can intersect the glass correctly.

With legacy material nodes, connect the Material node's **Alpha** output to the
Output node's **Alpha** input as well as connecting Color. An unconnected Output
Alpha defaults to 1, so secondary ray hits can become opaque even when material
Alpha is zero. Disabling Traceable skips these hits and can appear to fix the
transparency while giving incorrect glass intersections. This behavior and the
Color-only default node graph match official Blender 2.79b; the port does not
silently override the output alpha or enable filtering.

## Importing 2.79 scenes

Use **File → Import → Blender Internal 2.79 (.blend)** or **Import Blender Internal
Scene** in Render Properties. Ordinary File → Open cannot restore the removed
Internal material settings. The importer reads those settings from the original
file, converts geometry in a temporary background Blender process, and appends
editable scenes into the current session. This avoids a modern Blender append
crash involving old compositor data. The source file and existing scenes are
preserved. Conversion may take a few seconds for larger files.

Packed textures remain packed; external asset paths are resolved before moving
the converted file. Internal texture-slot data is explicitly retained even when
modern material conversion removes its original users. Conversion failures report
an error without replacing the open scene. Imported geometry and rigs still use
the modern dependency graph; **Original Legacy File** remains the option for
original dependency-graph evaluation.

## Verification and boundaries

`tests/material_workflow.py` exercises slot assignment, ownership, material copies,
save/reload, visible property export, rendered color changes, ramps and unregister.
`tests/render_workflow.py` checks every supported renderer setting against native
RNA, compatibility with existing scenes, host ownership, pixel changes, archive
overrides, sampled blur and save/reload. `tests/ui_workflow.py` runs a disposable windowed Blender instance and verifies
actual redraw/context behavior: empty materials, orphan trees, object selection,
pinning, texture graphs and group editing. `tests/viewport_pipeline.py` checks
preview/F12 pixel agreement, owned scene snapshots and cancellation;
`tests/viewport_ui.py` checks actual GPU display and live edits.
`tests/texture_preview_ui.py` keeps the texture panel visible while checking
Musgrave bump, texture nodes, shader Texture nodes, live edits, slot removal and
re-addition, and stable completion while the interface is idle.
`tests/refraction_reference.py` generates official 2.79b node-alpha, Traceable and
Filter fixtures; `tests/refraction_parity.py` compares final and viewport pixels
and exercises depth-256 glass. Run these with the other suites using:

```
python3 scripts/validate.py --blender /path/to/Blender --ui
```

The live UI review also used the actual New, color picker and texture controls.
Material preview thumbnails and Material Preview studio-light shading remain
unsupported; choose Rendered shading for the Internal viewport. Solid viewport display color
is a separate Blender setting. Original-file scene mode renders the selected
legacy file, so editing current-scene materials does not change that render.
See `PORTING.md` for remaining engine/migration limitations.
