"""Export real NRC scans to PNG pages for corner labelling. Nothing leaves this machine.

The pages are written OUTSIDE the repository (default: Documents/smartclear_private_scans),
so real personal documents can never be committed or published with the code.

    python tools/label_corners/export_pages.py "C:/path/to/folder/or/file.pdf" ...

Each PDF page becomes <name>_p<page>.png. Images (png/jpg) are copied as they are.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pypdfium2 as pdfium

OUT = Path.home() / "Documents" / "smartclear_private_scans"
DPI = 150


def export_pdf(path: Path) -> list[Path]:
    pdf = pdfium.PdfDocument(path.read_bytes())
    outs = []
    for i in range(len(pdf)):
        img = pdf[i].render(scale=DPI / 72).to_pil().convert("RGB")
        dest = OUT / f"{path.stem}_p{i + 1}.png"
        img.save(dest)
        outs.append(dest)
    return outs


def collect(args: list[str]) -> list[Path]:
    files: list[Path] = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            files += sorted(p.rglob("*.pdf")) + sorted(p.rglob("*.png")) + sorted(p.rglob("*.jpg"))
        elif p.exists():
            files.append(p)
    return files


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    done = []
    for f in collect(sys.argv[1:]):
        if f.suffix.lower() == ".pdf":
            done += export_pdf(f)
        elif f.suffix.lower() in (".png", ".jpg", ".jpeg"):
            dest = OUT / f.name
            shutil.copy(f, dest)
            done.append(dest)
    print(f"wrote {len(done)} page(s) to {OUT}")
    for d in done:
        print("  ", d.name)


if __name__ == "__main__":
    main()
