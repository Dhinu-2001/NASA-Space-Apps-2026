"""Add coverage/version metadata to data/manifests/kernels.json (metadata inspection only).

Reads DAF (SPK/PCK) segment summaries directly with the stdlib: this extracts the time coverage
stored in the file. It performs NO ephemeris or frame calculations (those are Stage 3).
Usage: python -I scripts/inspect_kernels.py
"""

from __future__ import annotations

import json
import re
import struct
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KDIR = ROOT / "data" / "kernels"
MANIFEST = ROOT / "data" / "manifests" / "kernels.json"
J2000 = datetime(2000, 1, 1, 12, 0, 0)


def _tdb_seconds_to_date(et: float) -> str:
    # Calendar date approximation (TDB~TT, ignores ~69 s offset): metadata display only.
    return (J2000 + timedelta(seconds=et)).strftime("%Y-%m-%d")


def daf_segments(path: Path) -> list[dict]:
    with path.open("rb") as f:
        rec = f.read(1024)
        endian = "<" if rec[88:96].strip() == b"LTL-IEEE" else ">"
        nd, ni = struct.unpack(endian + "ii", rec[8:16])
        fward = struct.unpack(endian + "i", rec[76:80])[0]
        segs, n = [], fward
        while n:
            f.seek((n - 1) * 1024)
            r = f.read(1024)
            nxt, _prev, ns = struct.unpack(endian + "ddd", r[:24])
            size = nd + (ni + 1) // 2
            for i in range(int(ns)):
                o = 24 + i * size * 8
                d = struct.unpack(endian + f"{nd}d", r[o : o + nd * 8])
                ints = struct.unpack(endian + f"{ni}i", r[o + nd * 8 : o + nd * 8 + ni * 4])
                segs.append(
                    {
                        "body_or_frame_id": ints[0],
                        "start_tdb_s_past_j2000": d[0],
                        "end_tdb_s_past_j2000": d[1],
                        "start_date_approx": _tdb_seconds_to_date(d[0]),
                        "end_date_approx": _tdb_seconds_to_date(d[1]),
                    }
                )
            n = int(nxt)
    return segs


def main() -> None:
    m = json.loads(MANIFEST.read_text())
    files = m["files"]

    for name in ("de440s.bsp", "moon_pa_de440_200625.bpc"):
        segs = daf_segments(KDIR / name)
        files[name]["daf_id_word"] = (KDIR / name).read_bytes()[:8].decode().strip()
        files[name]["coverage"] = {
            "n_segments": len(segs),
            "union_start_date_approx": min(s["start_date_approx"] for s in segs),
            "union_end_date_approx": max(s["end_date_approx"] for s in segs),
            "segments": segs,
        }

    fk = (KDIR / "moon_de440_250416.tf").read_text()
    files["moon_de440_250416.tf"]["version"] = {
        "creation_date": re.search(r"Creation date:\s+(.+)", fk).group(1).strip(),
        "created_by": re.search(r"Created by:\s+(.+)", fk).group(1).strip(),
        "pairs_with_pck": "moon_pa_de440_200625.bpc",
        "frames": {"MOON_PA": 31000, "MOON_ME": 31001, "MOON_PA_DE440": 31008,
                   "MOON_ME_DE440_ME421": 31009},
        "moon_me_is_alias_of": "MOON_ME_DE440_ME421",
        "doc_quote_me_vs_de421_me_max_rotation_rad_2000_2040": 3.0709840342771e-07,
        "doc_quote_me_vs_de421_me_max_displacement_2000_2040": "approximately 53.4 cm",
        "doc_quote_pa_vs_me_angle_deg": 0.02886,
        "doc_quote_pa_vs_me_displacement": "approximately 875 m",
    }
    lsk = (KDIR / "naif0012.tls").read_text()
    last = re.findall(r"(\d+),\s+@(\d{4}-[A-Z]{3}-\d+)", lsk)[-1]
    files["naif0012.tls"]["version"] = {
        "latest_leap_second": f"TAI-UTC = {last[0]} s effective {last[1]}",
        "note": "No leap seconds announced after 2017-JAN-1 are represented; future UTC is "
        "assumed to have none (same assumption JPL Horizons states).",
    }
    MANIFEST.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
    print("manifest updated")


if __name__ == "__main__":
    main()
