"""
WebRTC Media Tracks — Dynamic synthetic audio and video sources (Part 9).

Provides:
  - DemoVideoTrack: Generates live 640x480 25fps video with real-time timestamp HUD
  - DemoAudioTrack: Generates live 48kHz audio with gentle periodic test signal
  - Factory function to create configured media tracks
"""

import asyncio
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any

import av
import numpy as np
from aiortc import AudioStreamTrack, VideoStreamTrack
from PIL import Image, ImageDraw, ImageFont


class DemoVideoTrack(VideoStreamTrack):
    """
    Live synthetic video stream representing an evidence node camera.
    Generates distinct video frames with dynamic timestamp, live indicator,
    node identifier, and scanline ticker.
    """

    kind = "video"

    def __init__(
        self,
        node_id: str = "CCTV-A",
        width: int = 640,
        height: int = 480,
        fps: int = 25,
    ) -> None:
        super().__init__()
        self.node_id = node_id
        self.width = width
        self.height = height
        self.fps = fps
        self._frame_count = 0
        self._start_time = datetime.now(timezone.utc)

    async def recv(self) -> av.VideoFrame:
        pts, time_base = await self.next_timestamp()

        # Generate live dynamic frame
        now = datetime.now(timezone.utc)
        now_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " UTC"
        self._frame_count += 1

        # Background color with subtle scanline modulation
        scanline_y = (self._frame_count * 4) % self.height
        img = Image.new("RGB", (self.width, self.height), color=(12, 16, 24))
        draw = ImageDraw.Draw(img)

        # Tactical surveillance border & grid lines
        draw.rectangle([(8, 8), (self.width - 9, self.height - 9)], outline=(35, 50, 70), width=1)
        draw.line([(0, scanline_y), (self.width, scanline_y)], fill=(25, 45, 65), width=2)

        # Crosshairs / HUD corners
        ch_len = 16
        draw.line([(12, 12), (12 + ch_len, 12)], fill=(0, 220, 255), width=2)
        draw.line([(12, 12), (12, 12 + ch_len)], fill=(0, 220, 255), width=2)
        draw.line([(self.width - 13, 12), (self.width - 13 - ch_len, 12)], fill=(0, 220, 255), width=2)
        draw.line([(self.width - 13, 12), (self.width - 13, 12 + ch_len)], fill=(0, 220, 255), width=2)
        draw.line([(12, self.height - 13), (12 + ch_len, self.height - 13)], fill=(0, 220, 255), width=2)
        draw.line([(12, self.height - 13), (12, self.height - 13 - ch_len)], fill=(0, 220, 255), width=2)
        draw.line([(self.width - 13, self.height - 13), (self.width - 13 - ch_len, self.height - 13)], fill=(0, 220, 255), width=2)
        draw.line([(self.width - 13, self.height - 13), (self.width - 13, self.height - 13 - ch_len)], fill=(0, 220, 255), width=2)

        # Header Title
        draw.text((24, 20), "ECHOVAULT DISTRIBUTED MULTIMEDIA SYSTEM", fill=(140, 170, 200))
        draw.text((24, 40), f"NODE: {self.node_id}", fill=(255, 255, 255))

        # Live Indicator (pulsing red dot)
        dot_color = (255, 40, 40) if (self._frame_count % 30 < 20) else (120, 20, 20)
        draw.ellipse([(self.width - 95, 24), (self.width - 83, 36)], fill=dot_color)
        draw.text((self.width - 75, 22), "● LIVE", fill=(255, 60, 60))

        # Center Video Reticle
        cx, cy = self.width // 2, self.height // 2
        draw.rectangle([(cx - 40, cy - 30), (cx + 40, cy + 30)], outline=(40, 70, 95), width=1)
        draw.line([(cx - 10, cy), (cx + 10, cy)], fill=(0, 220, 255), width=1)
        draw.line([(cx, cy - 10), (cx, cy + 10)], fill=(0, 220, 255), width=1)

        # Bottom Telemetry HUD
        draw.rectangle([(16, self.height - 70), (self.width - 16, self.height - 16)], fill=(18, 24, 36), outline=(30, 45, 65))
        draw.text((28, self.height - 62), f"TIME:   {now_str}", fill=(0, 255, 180))
        draw.text((28, self.height - 42), f"STREAM: 640x480 @ {self.fps} FPS  |  FRAME: #{self._frame_count:06d}", fill=(180, 200, 220))
        draw.text((self.width - 170, self.height - 42), "SECURE WEBRTC", fill=(100, 140, 180))

        # Convert to av.VideoFrame
        frame = av.VideoFrame.from_image(img)
        frame.pts = pts
        frame.time_base = time_base
        return frame


class DemoAudioTrack(AudioStreamTrack):
    """
    Live synthetic audio stream representing an evidence node microphone.
    Generates 48kHz mono audio with a soft periodic test pulse.
    """

    kind = "audio"

    def __init__(self, sample_rate: int = 48000) -> None:
        super().__init__()
        self.sample_rate = sample_rate
        self.samples_per_frame = 960  # 20ms at 48kHz
        self._total_samples = 0

    async def recv(self) -> av.AudioFrame:
        pts = self._total_samples
        time_base = Fraction(1, self.sample_rate)

        # 48kHz sine wave with periodic soft envelope (beep every 2 seconds)
        t = (np.arange(self._total_samples, self._total_samples + self.samples_per_frame)) / self.sample_rate
        self._total_samples += self.samples_per_frame

        # Pulse every 2.0s for 0.08s
        period = 2.0
        time_in_period = t % period
        beep_mask = (time_in_period < 0.08).astype(np.float32)

        frequency = 440.0  # A4
        # Gentle amplitude (max 0.15 to avoid loud sounds)
        audio_data = (np.sin(2 * np.pi * frequency * t) * beep_mask * 0.12 * 32767).astype(np.int16)

        # Convert to av.AudioFrame
        frame = av.AudioFrame.from_ndarray(
            audio_data.reshape(1, -1),
            format="s16",
            layout="mono",
        )
        frame.sample_rate = self.sample_rate
        frame.pts = pts
        frame.time_base = time_base
        return frame


def create_media_tracks(
    node_id: str = "CCTV-A",
    has_video: bool = True,
    has_audio: bool = True,
) -> list[Any]:
    """Factory creating configured media tracks for WebRTC peer connection."""
    tracks: list[Any] = []
    if has_video:
        tracks.append(DemoVideoTrack(node_id=node_id))
    if has_audio:
        tracks.append(DemoAudioTrack())
    return tracks
