"""Patch l'icône dans le .exe existant sans reconstruire."""
import struct
import sys
from pathlib import Path

import win32api
import win32con

EXE = Path(r"dist\neoSlice\neoSlice.exe")
ICO = Path(r"assets\neoSlice.ico")

# ── Lecture ICO ───────────────────────────────────────────────────────────────
def read_ico(path: Path):
    """Retourne (header_entries, image_data_list)."""
    data = path.read_bytes()
    # ICONDIR: reserved(2) type(2) count(2)
    reserved, ico_type, count = struct.unpack_from("<HHH", data, 0)
    entries = []
    for i in range(count):
        offset = 6 + i * 16
        width, height, color_count, reserved2 = struct.unpack_from("<BBBB", data, offset)
        planes, bit_count = struct.unpack_from("<HH", data, offset + 4)
        bytes_in_res, image_offset = struct.unpack_from("<II", data, offset + 8)
        entries.append({
            "width": width if width != 0 else 256,
            "height": height if height != 0 else 256,
            "color_count": color_count,
            "planes": planes,
            "bit_count": bit_count,
            "data": data[image_offset: image_offset + bytes_in_res],
        })
    return entries


def build_group_icon(entries, base_id=1):
    """Construit la ressource GRPICONDIR pour RT_GROUP_ICON."""
    # GRPICONDIR header
    hdr = struct.pack("<HHH", 0, 1, len(entries))
    entry_data = b""
    for i, e in enumerate(entries):
        # GRPICONDIRENTRY: width height color_count reserved planes bit_count bytes_in_res id
        w = e["width"] if e["width"] < 256 else 0
        h = e["height"] if e["height"] < 256 else 0
        entry_data += struct.pack(
            "<BBBBHHIh",
            w, h,
            e["color_count"],
            0,                  # reserved
            e["planes"],
            e["bit_count"],
            len(e["data"]),
            base_id + i,        # RT_ICON resource ID
        )
    return hdr + entry_data


# ── Patch exe ─────────────────────────────────────────────────────────────────
def patch_exe_icon(exe_path: Path, ico_path: Path):
    if not exe_path.exists():
        print(f"EXE introuvable : {exe_path}")
        return False
    if not ico_path.exists():
        print(f"ICO introuvable : {ico_path}")
        return False

    entries = read_ico(ico_path)
    print(f"ICO lu : {len(entries)} taille(s) — {[e['width'] for e in entries]}px")

    base_id = 1
    group_icon_data = build_group_icon(entries, base_id)

    handle = win32api.BeginUpdateResource(str(exe_path), False)
    try:
        # Écrire chaque RT_ICON
        for i, e in enumerate(entries):
            win32api.UpdateResource(
                handle,
                win32con.RT_ICON,
                base_id + i,
                e["data"],
            )
            print(f"  RT_ICON #{base_id + i} : {e['width']}x{e['height']} ({len(e['data'])} bytes)")

        # Écrire le RT_GROUP_ICON (ID=1)
        win32api.UpdateResource(
            handle,
            win32con.RT_GROUP_ICON,
            1,
            group_icon_data,
        )
        print(f"  RT_GROUP_ICON écrit ({len(group_icon_data)} bytes)")

        win32api.EndUpdateResource(handle, False)
        print(f"\nPatch réussi : {exe_path}")
        return True

    except Exception as e:
        win32api.EndUpdateResource(handle, True)  # Annuler
        print(f"Erreur : {e}")
        return False


if __name__ == "__main__":
    ok = patch_exe_icon(EXE, ICO)
    sys.exit(0 if ok else 1)
