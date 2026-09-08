"""Tests for nlsh/image_utils.py."""

import base64
import io

import pytest
from PIL import Image

from nlsh.image_utils import (
    detect_input_type,
    get_backend_image_size_limit,
    is_image_type,
    prepare_image_for_api,
    validate_image_size,
)


def _make_png_bytes(size=(50, 50), color=(255, 0, 0)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


class TestDetectInputType:
    def test_png_magic_bytes(self):
        assert detect_input_type(_make_png_bytes()) == "image/png"

    def test_jpeg_magic_bytes(self):
        assert detect_input_type(b"\xff\xd8\xff\xe0rest of jpeg data here") == "image/jpeg"

    def test_gif87a_magic_bytes(self):
        assert detect_input_type(b"GIF87a" + b"\x00" * 20) == "image/gif"

    def test_gif89a_magic_bytes(self):
        assert detect_input_type(b"GIF89a" + b"\x00" * 20) == "image/gif"

    def test_webp_magic_bytes(self):
        data = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 20
        assert detect_input_type(data) == "image/webp"

    def test_bmp_magic_bytes(self):
        assert detect_input_type(b"BM" + b"\x00" * 20) == "image/bmp"

    def test_plain_text(self):
        assert detect_input_type(b"just some plain text content") == "text/plain"

    def test_empty_bytes(self):
        assert detect_input_type(b"") == "text/plain"

    def test_data_url_png(self):
        b64 = base64.b64encode(_make_png_bytes()).decode("ascii")
        data_url = f"data:image/png;base64,{b64}".encode()
        assert detect_input_type(data_url) == "image/png"

    def test_raw_base64_encoded_png_bytes(self):
        b64 = base64.b64encode(_make_png_bytes()).decode("ascii")
        assert detect_input_type(b64.encode("ascii")) == "image/png"

    def test_short_text_not_treated_as_base64_image(self):
        assert detect_input_type(b"aGVsbG8=") == "text/plain"


class TestPrepareImageForApi:
    def test_raw_bytes_to_base64(self):
        raw = _make_png_bytes()
        b64_data, mime = prepare_image_for_api(raw, "image/png")
        assert mime == "image/png"
        assert base64.b64decode(b64_data) == raw

    def test_data_url_passthrough(self):
        raw = _make_png_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        data_url = f"data:image/png;base64,{b64}".encode()
        b64_data, mime = prepare_image_for_api(data_url, "image/png")
        assert mime == "image/png"
        assert b64_data == b64

    def test_unsupported_mime_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported image format"):
            prepare_image_for_api(b"whatever", "image/svg+xml")

    def test_already_base64_image_data_passthrough(self):
        raw = _make_png_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        b64_data, mime = prepare_image_for_api(b64.encode("ascii"), "image/png")
        assert mime == "image/png"
        assert base64.b64decode(b64_data) == raw


class TestValidateImageSize:
    def test_under_limit_does_not_raise(self):
        validate_image_size(b"x" * 100, max_size_mb=1.0)

    def test_over_limit_raises_value_error(self):
        data = b"x" * (2 * 1024 * 1024)
        with pytest.raises(ValueError, match="Image too large"):
            validate_image_size(data, max_size_mb=1.0)

    def test_default_max_size(self):
        # Well under the 20MB default.
        validate_image_size(b"x" * 1024)


class TestIsImageType:
    def test_image_types(self):
        assert is_image_type("image/png") is True
        assert is_image_type("image/jpeg") is True

    def test_non_image_types(self):
        assert is_image_type("text/plain") is False
        assert is_image_type("application/json") is False


class TestGetBackendImageSizeLimit:
    def test_default_when_missing(self):
        assert get_backend_image_size_limit({}) == 20.0

    def test_explicit_value(self):
        assert get_backend_image_size_limit({"max_image_size_mb": 5.0}) == 5.0

    def test_none_config_falls_back_to_default(self):
        """config.get_backend() may return None; the default must be used."""
        assert get_backend_image_size_limit(None) == 20.0
