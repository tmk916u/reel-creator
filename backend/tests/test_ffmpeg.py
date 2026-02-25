import pytest
from app.services.ffmpeg import get_video_duration, extract_audio


def test_get_video_duration_invalid_file():
    with pytest.raises(RuntimeError):
        get_video_duration("/nonexistent/file.mp4")
