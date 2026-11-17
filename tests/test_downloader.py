"""Tests for the downloader module."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from downloader import is_url, download_video, get_video_title


def test_is_url_standard():
    assert is_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
    assert is_url("http://youtube.com/watch?v=test") is True
    assert is_url("https://youtu.be/dQw4w9WgXcQ") is True
    assert is_url("https://twitch.tv/videos/123456789") is True
    assert is_url("https://vimeo.com/123456789") is True


def test_is_url_shorthand():
    assert is_url("youtu.be/dQw4w9WgXcQ") is True
    assert is_url("youtube.com/watch?v=test") is True
    assert is_url("www.youtube.com/watch?v=test") is True


def test_is_url_local_paths():
    assert is_url("gameplay/video.mp4") is False
    assert is_url(Path("gameplay/video.mp4")) is False
    assert is_url("C:\\videos\\clip.mp4") is False
    assert is_url("/home/user/video.mkv") is False
    assert is_url("") is False
    assert is_url(None) is False


def test_download_video_missing_ytdlp(tmp_path):
    with patch.dict(sys.modules, {"yt_dlp": None}):
        with pytest.raises(ImportError, match="yt-dlp is required"):
            download_video("https://youtube.com/watch?v=123", output_dir=tmp_path)


def test_download_video_mocked(tmp_path):
    mock_ytdl = MagicMock()
    mock_instance = MagicMock()
    mock_ytdl.YoutubeDL.return_value.__enter__.return_value = mock_instance
    mock_instance.download.return_value = 0

    # Simulate yt-dlp creating an output file
    out_file = tmp_path / "Awesome Stream [xyz].mp4"
    out_file.write_bytes(b"dummy video data")

    with patch.dict(sys.modules, {"yt_dlp": mock_ytdl}):
        result = download_video("https://youtube.com/watch?v=xyz", output_dir=tmp_path)
        assert result.exists()
        assert result.name == "Awesome Stream [xyz].mp4"
        assert mock_instance.download.called


def test_get_video_title_mocked():
    mock_ytdl = MagicMock()
    mock_instance = MagicMock()
    mock_ytdl.YoutubeDL.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"title": "Viral Moment Stream"}

    with patch.dict(sys.modules, {"yt_dlp": mock_ytdl}):
        title = get_video_title("https://youtube.com/watch?v=123")
        assert title == "Viral Moment Stream"
