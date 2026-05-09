"""Synthetic passport image generator for end-to-end testing.

Renders a passport-page-like JPEG with the TD3 MRZ at the bottom, in a
clean monospace font on a white background. PassportEye + Tesseract reads
the MRZ region from the bottom of the image, so the rest of the page is
just visual filler — we draw a placeholder photo and a few data lines so
the image looks plausible at a glance.

The MRZ itself is real: every check digit is computed via the production
ICAO 9303 routines from ``hawiya.extractors.validators``. Submitting one
of these images to ``/v1/identity/resolve`` exercises the full pipeline.

Usage as a library:

    from scripts.generate_passport_image import build_passport_image
    img_bytes = build_passport_image(passport_number="P1234567", ...)

Usage as a CLI:

    python -m scripts.generate_passport_image --out /tmp/p.jpg \\
        --passport P1234567 --surname ALMANSOORI --given MOHAMED \\
        --nationality ARE --dob 900112 --sex M --expiry 300101
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from hawiya.extractors.validators import compute_check_digit

# Canvas geometry. PassportEye looks for the MRZ as a darkly-textured
# band; if the band is too thin or the surrounding page too crowded the
# region detector misses. Wide image with the MRZ taking the full bottom
# third works reliably.
WIDTH, HEIGHT = 1100, 760
MRZ_BAND_HEIGHT = 220
MRZ_FONT_SIZE = 40
HEADER_FONT_SIZE = 20
LABEL_FONT_SIZE = 13

NAME_LENGTH = 39  # MRZ line 1 chars 6..44


def _pad(value: str, length: int) -> str:
    if len(value) > length:
        raise ValueError(f"value {value!r} too long for field of {length}")
    return value + "<" * (length - len(value))


def _name_field(surname: str, given: str) -> str:
    body = surname.upper().replace(" ", "<") + "<<" + given.upper().replace(" ", "<")
    return _pad(body, NAME_LENGTH)


def build_td3_mrz(
    *,
    issuing: str = "ARE",
    nationality: str = "ARE",
    surname: str = "ALMANSOORI",
    given: str = "MOHAMED",
    passport_number: str = "P1234567",
    dob: str = "900112",  # YYMMDD
    sex: str = "M",
    expiry: str = "300101",
    personal: str = "",
) -> tuple[str, str]:
    """Compute a valid TD3 MRZ pair with all 5 ICAO check digits."""
    line1 = "P<" + issuing + _name_field(surname, given)
    if len(line1) != 44:
        raise AssertionError(f"line1 length {len(line1)}")

    doc_field = _pad(passport_number, 9)
    doc_check = str(compute_check_digit(doc_field))
    dob_check = str(compute_check_digit(dob))
    expiry_check = str(compute_check_digit(expiry))
    personal_field = _pad(personal, 14)
    personal_check = str(compute_check_digit(personal_field))

    composite_input = (
        doc_field
        + doc_check
        + dob
        + dob_check
        + expiry
        + expiry_check
        + personal_field
        + personal_check
    )
    composite_check = str(compute_check_digit(composite_input))

    line2 = (
        doc_field
        + doc_check
        + nationality
        + dob
        + dob_check
        + sex
        + expiry
        + expiry_check
        + personal_field
        + personal_check
        + composite_check
    )
    if len(line2) != 44:
        raise AssertionError(f"line2 length {len(line2)}")
    return line1, line2


def _load_mono_font(size: int) -> ImageFont.ImageFont:
    """Find a monospace TTF on the host. Falls back to Pillow's default."""
    candidates = [
        # Linux container
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        # macOS
        "/System/Library/Fonts/Menlo.ttc",
        # Windows
        "C:\\Windows\\Fonts\\consola.ttf",
        "C:\\Windows\\Fonts\\cour.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def build_passport_image(
    *,
    issuing: str = "ARE",
    nationality: str = "ARE",
    surname: str = "ALMANSOORI",
    given: str = "MOHAMED",
    passport_number: str = "P1234567",
    dob: str = "900112",
    sex: str = "M",
    expiry: str = "300101",
    personal: str = "",
) -> bytes:
    """Return JPEG bytes for a synthetic passport with the supplied fields."""
    line1, line2 = build_td3_mrz(
        issuing=issuing,
        nationality=nationality,
        surname=surname,
        given=given,
        passport_number=passport_number,
        dob=dob,
        sex=sex,
        expiry=expiry,
        personal=personal,
    )

    img = Image.new("RGB", (WIDTH, HEIGHT), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    header_font = _load_mono_font(HEADER_FONT_SIZE)
    label_font = _load_mono_font(LABEL_FONT_SIZE)
    mrz_font = _load_mono_font(MRZ_FONT_SIZE)

    # Faux passport header.
    draw.text((30, 20), "PASSPORT — SYNTHETIC SPECIMEN", font=header_font, fill=(0, 0, 0))
    draw.line([(30, 55), (WIDTH - 30, 55)], fill=(0, 0, 0), width=2)

    # Photo placeholder.
    draw.rectangle([(30, 80), (200, 320)], outline=(0, 0, 0), width=2)
    draw.text((50, 190), "PHOTO", font=header_font, fill=(150, 150, 150))

    # Data lines (visual context only — the API only reads the MRZ).
    rows = [
        ("Surname",         surname.upper()),
        ("Given names",     given.upper()),
        ("Nationality",     nationality),
        ("Date of birth",   f"{dob[2:4]}/{dob[4:6]}/{dob[0:2]}"),
        ("Sex",             sex),
        ("Place of birth",  "—"),
        ("Date of issue",   "—"),
        ("Date of expiry",  f"{expiry[2:4]}/{expiry[4:6]}/{expiry[0:2]}"),
        ("Passport No.",    passport_number),
    ]
    y = 90
    for label, value in rows:
        draw.text((230, y), label.upper(), font=label_font, fill=(120, 120, 120))
        draw.text((230, y + 14), value, font=header_font, fill=(0, 0, 0))
        y += 50

    # MRZ band — high contrast strip at the bottom. PassportEye looks for
    # this region first.
    band_top = HEIGHT - MRZ_BAND_HEIGHT
    draw.rectangle([(0, band_top), (WIDTH, HEIGHT)], fill=(255, 255, 255))
    draw.line([(0, band_top), (WIDTH, band_top)], fill=(0, 0, 0), width=2)

    # Centre the MRZ horizontally.
    bbox = draw.textbbox((0, 0), line1, font=mrz_font)
    text_w = bbox[2] - bbox[0]
    x = (WIDTH - text_w) // 2
    draw.text((x, band_top + 14), line1, font=mrz_font, fill=(0, 0, 0))
    draw.text((x, band_top + 60), line2, font=mrz_font, fill=(0, 0, 0))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True, help="JPEG output path")
    p.add_argument("--passport", default="P1234567")
    p.add_argument("--surname", default="ALMANSOORI")
    p.add_argument("--given", default="MOHAMED")
    p.add_argument("--issuing", default="ARE")
    p.add_argument("--nationality", default="ARE")
    p.add_argument("--dob", default="900112", help="YYMMDD")
    p.add_argument("--expiry", default="300101", help="YYMMDD")
    p.add_argument("--sex", default="M", choices=("M", "F", "X"))
    args = p.parse_args()

    payload = build_passport_image(
        issuing=args.issuing,
        nationality=args.nationality,
        surname=args.surname,
        given=args.given,
        passport_number=args.passport,
        dob=args.dob,
        expiry=args.expiry,
        sex=args.sex,
    )
    args.out.write_bytes(payload)
    print(f"Wrote {len(payload)} bytes to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
