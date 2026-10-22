"""Attach an sRGB screen-proof OutputIntent to a rendered PDF."""
from __future__ import annotations

from pathlib import Path


def add_srgb_output_intent(pdf_path: Path) -> None:
    from PIL import ImageCms
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject, TextStringObject

    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    profile = DecodedStreamObject()
    profile.set_data(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    profile[NameObject("/N")] = NumberObject(3)
    profile_ref = writer._add_object(profile)
    output_intent = DictionaryObject({
        NameObject("/Type"): NameObject("/OutputIntent"),
        NameObject("/S"): NameObject("/GTS_PDFA1"),
        NameObject("/OutputConditionIdentifier"): TextStringObject("sRGB IEC61966-2.1"),
        NameObject("/Info"): TextStringObject("sRGB IEC61966-2.1"),
        NameObject("/DestOutputProfile"): profile_ref,
    })
    writer._root_object.update({NameObject("/OutputIntents"): ArrayObject([writer._add_object(output_intent)])})
    with pdf_path.open("wb") as stream:
        writer.write(stream)
