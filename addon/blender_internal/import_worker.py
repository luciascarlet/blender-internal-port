# SPDX-License-Identifier: GPL-2.0-or-later
"""Version legacy geometry in a disposable host, without replacing the user's file.

Run only via Blender's --python option. Internal material settings are captured
separately from the original file by legacy_import.Reader before this conversion.
"""
import sys
import bpy


def main():
    source, destination = sys.argv[sys.argv.index('--') + 1:]
    bpy.ops.wm.open_mainfile(filepath=source, load_ui=False, use_scripts=False)
    # Temporary-file relocation must not strand external images, libraries,
    # fonts or caches. Packed images remain packed.
    bpy.ops.file.make_paths_absolute()
    # Modern material versioning removes Internal texture-slot users. Keep the
    # original data even when it now appears orphaned; Reader restores those
    # references in the parent process. Library writing includes zero-user IDs.
    bpy.data.libraries.write(destination, set(bpy.data.user_map()),
                             path_remap='ABSOLUTE', fake_user=False, compress=False)
    print('BI_IMPORT_VERSIONED', flush=True)


if __name__ == '__main__':
    main()
