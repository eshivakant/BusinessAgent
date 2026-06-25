"""Image compression utilities for PDFs and other documents."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image
from pypdf import PdfReader, PdfWriter


def compress_pdf_images(pdf_bytes: bytes, max_image_size: int = 1024 * 1024) -> bytes:
    """
    Compress images in PDF if total size exceeds max_image_size.
    Returns compressed PDF bytes.
    
    Args:
        pdf_bytes: Original PDF bytes
        max_image_size: Max size threshold for compression (default 1MB)
    
    Returns:
        Compressed or original PDF bytes
    """
    try:
        # Check if compression needed
        if len(pdf_bytes) < max_image_size:
            return pdf_bytes  # No compression needed

        reader = PdfReader(BytesIO(pdf_bytes))
        writer = PdfWriter()

        compressed_any = False

        for page in reader.pages:
            if "/XObject" in page["/Resources"]:
                xobjects = page["/Resources"]["/XObject"].get_object()

                for obj_name in xobjects:
                    obj = xobjects[obj_name].get_object()

                    if obj["/Subtype"] == "/Image":
                        # Extract and compress image
                        if "/FlateDecode" in obj.get("/Filter", []):
                            try:
                                image_data = obj._data
                                img = Image.open(BytesIO(image_data))

                                # Compress: reduce quality and resize if very large
                                if img.size[0] > 2000 or img.size[1] > 2000:
                                    img = img.resize(
                                        (
                                            min(2000, img.size[0]),
                                            min(2000, img.size[1]),
                                        ),
                                        Image.Resampling.LANCZOS,
                                    )

                                compressed_buffer = BytesIO()
                                img.save(
                                    compressed_buffer,
                                    format="JPEG",
                                    quality=75,
                                    optimize=True,
                                )
                                compressed_any = True
                            except Exception:
                                pass

            writer.add_page(page)

        if not compressed_any:
            return pdf_bytes

        output = BytesIO()
        writer.write(output)
        compressed_bytes = output.getvalue()

        # Only return if compression was effective
        return compressed_bytes if len(compressed_bytes) < len(pdf_bytes) else pdf_bytes

    except Exception:
        # On any error, return original
        return pdf_bytes


def compress_image_file(image_path: Path, max_quality: int = 75) -> bytes:
    """
    Compress image file and return bytes.
    
    Args:
        image_path: Path to image file
        max_quality: JPEG quality (1-95)
    
    Returns:
        Compressed image bytes
    """
    try:
        img = Image.open(image_path)

        # Resize if very large
        if img.size[0] > 3000 or img.size[1] > 3000:
            img = img.resize(
                (
                    min(3000, img.size[0]),
                    min(3000, img.size[1]),
                ),
                Image.Resampling.LANCZOS,
            )

        output = BytesIO()
        format_map = {
            ".png": "PNG",
            ".jpg": "JPEG",
            ".jpeg": "JPEG",
            ".gif": "GIF",
            ".webp": "WEBP",
        }
        fmt = format_map.get(image_path.suffix.lower(), "JPEG")

        if fmt == "JPEG":
            img.save(output, format=fmt, quality=max_quality, optimize=True)
        else:
            img.save(output, format=fmt, optimize=True)

        return output.getvalue()
    except Exception:
        # Fallback: return original
        return image_path.read_bytes()
