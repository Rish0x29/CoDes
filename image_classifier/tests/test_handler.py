import json
import base64
import pytest
import sys, os
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


@pytest.fixture
def mock_rekognition_labels():
    return {
        "Labels": [
            {"Name": "Dog", "Confidence": 98.5, "Parents": [{"Name": "Animal"}],
             "Categories": [{"Name": "Animals"}], "Instances": []},
            {"Name": "Animal", "Confidence": 99.1, "Parents": [],
             "Categories": [{"Name": "Animals"}], "Instances": []},
        ]
    }


@pytest.fixture
def mock_rekognition_moderation():
    return {"ModerationLabels": []}


@pytest.fixture
def mock_rekognition_faces():
    return {
        "FaceDetails": [{
            "AgeRange": {"Low": 25, "High": 35},
            "Gender": {"Value": "Female", "Confidence": 99.0},
            "Emotions": [{"Type": "HAPPY", "Confidence": 95.0}],
            "Smile": {"Value": True, "Confidence": 98.0},
            "Eyeglasses": {"Value": False, "Confidence": 99.0},
            "Sunglasses": {"Value": False, "Confidence": 99.0},
            "BoundingBox": {"Width": 0.3, "Height": 0.4, "Left": 0.2, "Top": 0.1},
            "Confidence": 99.8,
            "Landmarks": [{"Type": "eyeLeft"}],
            "Pose": {"Roll": 1.0, "Yaw": -2.0, "Pitch": 3.0},
            "Quality": {"Brightness": 80.0, "Sharpness": 90.0},
        }]
    }


@patch("image_classifier.handler.s3")
@patch("image_classifier.handler.rekognition")
@patch("image_classifier.handler.dynamodb")
def test_classify_image(mock_dynamo, mock_rek, mock_s3, mock_rekognition_labels,
                        mock_rekognition_moderation, mock_rekognition_faces):
    mock_rek.detect_labels.return_value = mock_rekognition_labels
    mock_rek.detect_moderation_labels.return_value = mock_rekognition_moderation
    mock_rek.detect_faces.return_value = mock_rekognition_faces

    from image_classifier.handler import classify_image
    result = classify_image(image_bytes=b'\xff\xd8' + b'\x00' * 100)

    assert result["label_count"] == 2
    assert result["is_safe"] is True
    assert result["face_count"] == 1
    assert result["labels"][0]["name"] == "Dog"


@patch("image_classifier.handler.save_result")
@patch("image_classifier.handler.classify_image")
@patch("image_classifier.handler.s3")
def test_handler_post(mock_s3, mock_classify, mock_save):
    mock_classify.return_value = {
        "labels": [{"name": "Test", "confidence": 99}],
        "label_count": 1, "moderation_labels": [], "is_safe": True,
        "faces": [], "face_count": 0,
    }

    from image_classifier.handler import handler
    event = {
        "httpMethod": "POST",
        "body": json.dumps({"image_base64": base64.b64encode(b"fake").decode()}),
    }
    response = handler(event, None)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert "classification_id" in body
