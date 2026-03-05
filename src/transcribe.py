#!/usr/bin/env python3
"""
Transcription module using OpenAI Whisper.
Extracts audio from timeline and transcribes with timestamps.
"""

import os
import tempfile
import subprocess
import json
from dataclasses import dataclass
from typing import List, Optional, Callable


@dataclass
class TranscriptSegment:
    """A segment of transcribed audio."""
    start: float  # seconds
    end: float    # seconds
    text: str
    

@dataclass 
class Transcript:
    """Full transcript with segments."""
    segments: List[TranscriptSegment]
    language: str
    duration: float  # total duration in seconds
    
    def to_text(self) -> str:
        """Get plain text of entire transcript."""
        return " ".join(seg.text for seg in self.segments)
    
    def to_timestamped_text(self) -> str:
        """Get text with timestamps for each segment."""
        lines = []
        for seg in self.segments:
            timestamp = f"[{format_timestamp(seg.start)} -> {format_timestamp(seg.end)}]"
            lines.append(f"{timestamp} {seg.text}")
        return "\n".join(lines)


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS.mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def parse_timestamp(ts: str) -> float:
    """Parse HH:MM:SS.mmm to seconds."""
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    else:
        return float(parts[0])


def get_all_media_paths(timeline) -> List[str]:
    """
    Get paths to all media files in the timeline.
    Handles multi-track, multi-clip timelines.
    """
    media_paths = []
    seen_paths = set()
    
    # Check all video tracks
    track_count = timeline.GetTrackCount("video")
    for track_idx in range(1, track_count + 1):
        items = timeline.GetItemListInTrack("video", track_idx)
        if items:
            for clip in items:
                media_item = clip.GetMediaPoolItem()
                if media_item:
                    props = media_item.GetClipProperty()
                    file_path = props.get("File Path", "")
                    if file_path and file_path not in seen_paths and os.path.exists(file_path):
                        media_paths.append(file_path)
                        seen_paths.add(file_path)
    
    # Also check audio tracks
    audio_track_count = timeline.GetTrackCount("audio")
    for track_idx in range(1, audio_track_count + 1):
        items = timeline.GetItemListInTrack("audio", track_idx)
        if items:
            for clip in items:
                media_item = clip.GetMediaPoolItem()
                if media_item:
                    props = media_item.GetClipProperty()
                    file_path = props.get("File Path", "")
                    if file_path and file_path not in seen_paths and os.path.exists(file_path):
                        media_paths.append(file_path)
                        seen_paths.add(file_path)
    
    return media_paths


def extract_audio_from_timeline(timeline, output_path: str) -> str:
    """
    Extract audio from a DaVinci Resolve timeline.
    Handles multiple clips by concatenating audio.
    Returns path to the extracted audio file.
    """
    media_paths = get_all_media_paths(timeline)
    
    if not media_paths:
        raise ValueError("No media files found in timeline")
    
    if len(media_paths) == 1:
        # Single file - simple extraction
        return extract_audio_from_file(media_paths[0], output_path)
    
    # Multiple files - need to concatenate
    # Create temp files for each, then concat
    temp_files = []
    try:
        for i, path in enumerate(media_paths):
            temp_audio = output_path.replace(".wav", f"_part{i}.wav")
            extract_audio_from_file(path, temp_audio)
            temp_files.append(temp_audio)
        
        # Concatenate with ffmpeg
        concat_file = output_path.replace(".wav", "_concat.txt")
        with open(concat_file, "w") as f:
            for tf in temp_files:
                f.write(f"file '{tf}'\n")
        
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat error: {result.stderr}")
        
        # Cleanup concat file
        os.unlink(concat_file)
        
    finally:
        # Cleanup temp audio files
        for tf in temp_files:
            if os.path.exists(tf):
                os.unlink(tf)
    
    return output_path


def extract_audio_from_file(video_path: str, output_path: str) -> str:
    """Extract audio from a video file."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_path
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr}")
    
    return output_path


def transcribe_audio(audio_path: str, model_name: str = "base",
                     progress_callback: Optional[Callable[[int, str], None]] = None) -> Transcript:
    """
    Transcribe audio file using Whisper.
    
    Args:
        audio_path: Path to audio file (wav, mp3, etc.)
        model_name: Whisper model to use (tiny, base, small, medium, large)
        progress_callback: Optional callback(percent, status) for progress updates
    
    Returns:
        Transcript object with segments and timestamps
    """
    import whisper
    
    if progress_callback:
        progress_callback(5, f"Loading Whisper {model_name} model...")
    
    model = whisper.load_model(model_name)
    
    if progress_callback:
        progress_callback(15, "Transcribing audio (this may take a while)...")
    
    result = model.transcribe(audio_path, word_timestamps=True)
    
    if progress_callback:
        progress_callback(95, "Processing transcript...")
    
    segments = []
    for seg in result["segments"]:
        segments.append(TranscriptSegment(
            start=seg["start"],
            end=seg["end"],
            text=seg["text"].strip()
        ))
    
    # Calculate total duration from last segment
    duration = segments[-1].end if segments else 0
    
    return Transcript(
        segments=segments,
        language=result.get("language", "en"),
        duration=duration
    )


def transcribe_timeline_audio(timeline, model_name: str = "base",
                              progress_callback: Optional[Callable[[int, str], None]] = None) -> Transcript:
    """
    Transcribe audio from a DaVinci Resolve timeline.
    
    Args:
        timeline: DaVinci Resolve Timeline object
        model_name: Whisper model to use
        progress_callback: Optional callback for progress updates
    
    Returns:
        Transcript object
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name
    
    try:
        if progress_callback:
            progress_callback(0, "Extracting audio from timeline...")
        
        extract_audio_from_timeline(timeline, audio_path)
        
        return transcribe_audio(audio_path, model_name, progress_callback)
    finally:
        if os.path.exists(audio_path):
            os.unlink(audio_path)


def transcribe_video_file(video_path: str, model_name: str = "base",
                          progress_callback: Optional[Callable[[int, str], None]] = None) -> Transcript:
    """
    Transcribe audio from a video file.
    
    Args:
        video_path: Path to video file
        model_name: Whisper model to use
        progress_callback: Optional callback for progress updates
    
    Returns:
        Transcript object
    """
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name
    
    try:
        if progress_callback:
            progress_callback(0, "Extracting audio...")
        
        extract_audio_from_file(video_path, audio_path)
        
        return transcribe_audio(audio_path, model_name, progress_callback)
    finally:
        if os.path.exists(audio_path):
            os.unlink(audio_path)


if __name__ == "__main__":
    # Test with a video file
    import sys
    if len(sys.argv) > 1:
        video = sys.argv[1]
        print(f"Transcribing: {video}")
        
        def progress(pct, status):
            print(f"  [{pct}%] {status}")
        
        transcript = transcribe_video_file(video, progress_callback=progress)
        print(transcript.to_timestamped_text())
