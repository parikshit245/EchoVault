"""
WebRTC Media Tracks Unit Tests — Part 9.

Tests:
  - DemoVideoTrack frame generation, resolution, and PTS
  - DemoAudioTrack frame generation, sample rate, and audio samples
  - Media track factory with configurable video/audio flags
"""

import sys
from pathlib import Path

import av
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.webrtc.tracks import DemoAudioTrack, DemoVideoTrack, create_media_tracks


@pytest.mark.asyncio
async def test_demo_video_track_produces_frames():
    """DemoVideoTrack must produce valid 640x480 av.VideoFrame with valid PTS."""
    track = DemoVideoTrack(node_id="CCTV-A", width=640, height=480, fps=25)
    assert track.kind == "video"
    assert track.node_id == "CCTV-A"

    frame = await track.recv()
    assert isinstance(frame, av.VideoFrame)
    assert frame.width == 640
    assert frame.height == 480
    assert frame.pts is not None

    frame2 = await track.recv()
    assert isinstance(frame2, av.VideoFrame)
    assert frame2.pts > frame.pts


@pytest.mark.asyncio
async def test_demo_audio_track_produces_frames():
    """DemoAudioTrack must produce valid 48kHz av.AudioFrame."""
    track = DemoAudioTrack(sample_rate=48000)
    assert track.kind == "audio"
    assert track.sample_rate == 48000

    frame = await track.recv()
    assert isinstance(frame, av.AudioFrame)
    assert frame.sample_rate == 48000
    assert frame.samples == 960  # 20ms at 48kHz
    assert frame.pts is not None


def test_create_media_tracks_factory():
    """create_media_tracks must produce only requested kinds."""
    both = create_media_tracks("CCTV-A", has_video=True, has_audio=True)
    assert len(both) == 2
    assert any(t.kind == "video" for t in both)
    assert any(t.kind == "audio" for t in both)

    video_only = create_media_tracks("CCTV-A", has_video=True, has_audio=False)
    assert len(video_only) == 1
    assert video_only[0].kind == "video"

    audio_only = create_media_tracks("CCTV-A", has_video=False, has_audio=True)
    assert len(audio_only) == 1
    assert audio_only[0].kind == "audio"

    neither = create_media_tracks("CCTV-A", has_video=False, has_audio=False)
    assert len(neither) == 0
