#!/usr/bin/env python3
"""Validate the committed entry.png and copy it to the output directory."""

import hashlib
import os
import struct
import sys
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_DIMENSION = 1024
MAX_BYTES = 1024 * 1024


class ValidationError(Exception):
    """Raised when entry.png is missing or fails a validation check."""


def find_source():
    here = os.path.realpath(__file__)
    local = os.path.join(os.path.dirname(here), "entry.png")
    if os.path.isfile(local):
        return local
    fallback = "/bot/entry.png"
    if os.path.isfile(fallback):
        return fallback
    raise ValidationError("entry.png not found beside main.py or at /bot/entry.png")


def read_image(path):
    try:
        with open(path, "rb") as handle:
            return handle.read()
    except OSError as exc:
        raise ValidationError(f"cannot read entry.png: {exc}") from exc


def validate(data):
    if not data.startswith(PNG_SIGNATURE):
        raise ValidationError("bad PNG signature")
    if len(data) > MAX_BYTES:
        raise ValidationError(
            f"image is {len(data)} bytes, over the {MAX_BYTES}-byte limit"
        )

    offset = len(PNG_SIGNATURE)
    first = True
    last = False
    while offset < len(data):
        if last:
            raise ValidationError("trailing data after IEND chunk")
        if offset + 8 > len(data):
            raise ValidationError("truncated chunk header")

        length, chunk_type = struct.unpack(">I4s", data[offset : offset + 8])
        body_start = offset + 8
        body_end = body_start + length
        crc_end = body_end + 4
        if crc_end > len(data):
            raise ValidationError(
                f"truncated {chunk_type.decode('latin-1')} chunk"
            )

        body = data[body_start:body_end]
        expected = struct.unpack(">I", data[body_end:crc_end])[0]
        actual = zlib.crc32(chunk_type + body) & 0xFFFFFFFF
        if expected != actual:
            raise ValidationError(
                f"bad CRC in {chunk_type.decode('latin-1')} chunk"
            )

        if first:
            if chunk_type != b"IHDR":
                raise ValidationError("first chunk is not IHDR")
            if length != 13:
                raise ValidationError("IHDR chunk has wrong length")
            width, height = struct.unpack(">II", body[:8])
            if width < 1 or height < 1:
                raise ValidationError(f"invalid dimensions {width}x{height}")
            if width > MAX_DIMENSION or height > MAX_DIMENSION:
                raise ValidationError(
                    f"image is {width}x{height}, over the "
                    f"{MAX_DIMENSION}x{MAX_DIMENSION} limit"
                )
            first = False

        if chunk_type == b"IEND":
            if length != 0:
                raise ValidationError("IEND chunk has wrong length")
            last = True

        offset = crc_end

    if first:
        raise ValidationError("missing IHDR chunk")
    if not last:
        raise ValidationError("missing IEND chunk")


def main():
    try:
        source = find_source()
        data = read_image(source)
        validate(data)
        output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR") or "/output"
        os.makedirs(output_dir, exist_ok=True)
        destination = os.path.join(output_dir, "entry.png")
        with open(destination, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except (ValidationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    digest = hashlib.sha256(data).hexdigest()
    print(f"wrote {destination} ({len(data)} bytes) sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())