import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from image_classifier.utils import validate_image_bytes, decode_base64_image, format_bounding_box


def test_validate_jpeg():
    valid, fmt = validate_image_bytes(b'\xff\xd8' + b'\x00' * 200)
    assert valid is True
    assert fmt == "image/jpeg"


def test_validate_png():
    valid, fmt = validate_image_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 200)
    assert valid is True
    assert fmt == "image/png"


def test_validate_too_large():
    valid, msg = validate_image_bytes(b'\x00' * (6 * 1024 * 1024))
    assert valid is False
    assert "too large" in msg


def test_validate_too_small():
    valid, msg = validate_image_bytes(b'\x00' * 10)
    assert valid is False
    assert "too small" in msg


def test_decode_base64_with_prefix():
    import base64
    data = b"test image data"
    encoded = f"data:image/png;base64,{base64.b64encode(data).decode()}"
    result = decode_base64_image(encoded)
    assert result == data


def test_format_bounding_box():
    bbox = {"Left": 0.1, "Top": 0.2, "Width": 0.3, "Height": 0.4}
    result = format_bounding_box(bbox, 1000, 800)
    assert result["left"] == 100
    assert result["top"] == 160
    assert result["width"] == 300
    assert result["height"] == 320
