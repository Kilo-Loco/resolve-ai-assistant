"""
Tests for error handling and edge cases.
"""

import pytest
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestFFmpegErrorHandling:
    """Test ffmpeg failure scenarios."""
    
    def test_extract_audio_ffmpeg_failure(self, tmp_path):
        """Test that ffmpeg failure raises RuntimeError."""
        from transcribe import extract_audio_from_file
        
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        output_path = tmp_path / "audio.wav"
        
        # Mock subprocess.run to simulate ffmpeg failure
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ffmpeg error: Invalid input file"
        
        with patch('transcribe.subprocess.run', return_value=mock_result):
            with pytest.raises(RuntimeError) as exc_info:
                extract_audio_from_file(str(video_path), str(output_path))
            
            assert "ffmpeg error" in str(exc_info.value)
    
    def test_extract_timeline_no_media(self):
        """Test extraction from timeline with no media."""
        from transcribe import get_all_media_paths
        
        mock_timeline = MagicMock()
        mock_timeline.GetTrackCount.return_value = 0
        
        paths = get_all_media_paths(mock_timeline)
        assert paths == []


class TestAnalyzeTranscriptWithMockedAPI:
    """Test analyze_transcript with mocked Anthropic API."""
    
    def test_analyze_transcript_success(self):
        """Test successful API call and parsing."""
        from transcribe import Transcript, TranscriptSegment
        from analyze import analyze_transcript, MarkerType
        
        transcript = Transcript(
            segments=[
                TranscriptSegment(0.0, 10.0, "Welcome to the video"),
                TranscriptSegment(10.5, 25.0, "This is amazing content"),
            ],
            language="en",
            duration=25.0
        )
        
        # Mock API response
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='''[
            {
                "start": "00:00:10.500",
                "end": "00:00:25.000",
                "type": "HIGHLIGHT",
                "label": "Amazing content",
                "note": "High engagement"
            }
        ]''')]
        
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_response
        
        with patch('anthropic.Anthropic', return_value=mock_client_instance):
            markers = analyze_transcript(transcript, {
                "add_highlights": True,
                "mark_dead_air": False,
                "find_shorts": False
            })
        
        assert len(markers) == 1
        assert markers[0].marker_type == MarkerType.HIGHLIGHT
        assert markers[0].label == "Amazing content"
    
    def test_analyze_transcript_malformed_response(self):
        """Test handling of malformed API response."""
        from transcribe import Transcript, TranscriptSegment
        from analyze import analyze_transcript
        
        transcript = Transcript(
            segments=[TranscriptSegment(0.0, 5.0, "Test")],
            language="en",
            duration=5.0
        )
        
        # Response is not valid JSON
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='This is not JSON at all')]
        
        mock_client_instance = MagicMock()
        mock_client_instance.messages.create.return_value = mock_response
        
        with patch('anthropic.Anthropic', return_value=mock_client_instance):
            markers = analyze_transcript(transcript, {"add_highlights": True})
        
        # Should return empty list, not crash
        assert markers == []


class TestEmptyTranscriptHandling:
    """Test edge cases with empty or minimal transcripts."""
    
    def test_analyze_for_silence_empty_transcript(self):
        """Test silence detection with empty transcript."""
        from transcribe import Transcript
        from analyze import analyze_for_silence
        
        transcript = Transcript(
            segments=[],
            language="en",
            duration=0.0
        )
        
        # Should not crash
        markers = analyze_for_silence(transcript)
        assert markers == []
    
    def test_analyze_for_silence_single_segment(self):
        """Test silence detection with single segment."""
        from transcribe import Transcript, TranscriptSegment
        from analyze import analyze_for_silence
        
        transcript = Transcript(
            segments=[TranscriptSegment(0.0, 10.0, "Only segment")],
            language="en",
            duration=10.0
        )
        
        # No gaps possible with single segment
        markers = analyze_for_silence(transcript)
        assert markers == []
    
    def test_transcript_to_text_empty(self):
        """Test to_text with empty transcript."""
        from transcribe import Transcript
        
        transcript = Transcript(segments=[], language="en", duration=0.0)
        
        assert transcript.to_text() == ""
        assert transcript.to_timestamped_text() == ""


class TestMarkerApplyFailure:
    """Test marker application failure scenarios."""
    
    def test_apply_marker_returns_false(self):
        """Test handling when AddMarker returns False."""
        from analyze import EditMarker, MarkerType
        from markers import apply_markers
        
        mock_timeline = MagicMock()
        mock_timeline.GetSetting.return_value = "24"
        mock_timeline.GetStartFrame.return_value = 0
        mock_timeline.AddMarker.return_value = False
        
        markers = [
            EditMarker(0, 5, MarkerType.HIGHLIGHT, "Test1"),
            EditMarker(10, 15, MarkerType.DEAD_AIR, "Test2"),
        ]
        
        added = apply_markers(mock_timeline, markers)
        assert added == 0
    
    def test_apply_marker_partial_failure(self):
        """Test when some markers fail to apply."""
        from analyze import EditMarker, MarkerType
        from markers import apply_markers
        
        mock_timeline = MagicMock()
        mock_timeline.GetSetting.return_value = "24"
        mock_timeline.GetStartFrame.return_value = 0
        mock_timeline.AddMarker.side_effect = [True, False, True]
        
        markers = [
            EditMarker(0, 5, MarkerType.HIGHLIGHT, "Success"),
            EditMarker(10, 15, MarkerType.DEAD_AIR, "Fail"),
            EditMarker(20, 25, MarkerType.SHORT_CLIP, "Success"),
        ]
        
        added = apply_markers(mock_timeline, markers)
        assert added == 2


class TestCacheCorruption:
    """Test handling of corrupted cache files."""
    
    def test_corrupted_cache_returns_none(self, tmp_path):
        """Test that corrupted cache file returns None."""
        import ai_edit_assistant
        
        cache_file = tmp_path / "corrupted.json"
        cache_file.write_text("{ this is not valid json }")
        
        with patch.object(ai_edit_assistant, 'CACHE_DIR', tmp_path):
            result = ai_edit_assistant.get_cached_transcript("corrupted")
            assert result is None
    
    def test_cache_missing_fields(self, tmp_path):
        """Test cache file with missing required fields."""
        import ai_edit_assistant
        
        cache_file = tmp_path / "incomplete.json"
        cache_file.write_text('{"language": "en"}')
        
        with patch.object(ai_edit_assistant, 'CACHE_DIR', tmp_path):
            result = ai_edit_assistant.get_cached_transcript("incomplete")
            assert result is None


class TestInvalidMarkerData:
    """Test handling of invalid marker data."""
    
    def test_marker_start_greater_than_end(self):
        """Test creating marker where start > end."""
        from analyze import EditMarker, MarkerType
        
        marker = EditMarker(
            start_seconds=20.0,
            end_seconds=10.0,
            marker_type=MarkerType.HIGHLIGHT,
            label="Invalid marker"
        )
        
        duration = marker.end_seconds - marker.start_seconds
        assert duration < 0
    
    def test_negative_timestamps(self):
        """Test handling negative timestamps."""
        from analyze import parse_timestamp
        
        result = parse_timestamp("-5.0")
        assert result == -5.0
    
    def test_empty_marker_label(self):
        """Test marker with empty label."""
        from analyze import EditMarker, MarkerType
        from markers import apply_markers
        
        mock_timeline = MagicMock()
        mock_timeline.GetSetting.return_value = "24"
        mock_timeline.GetStartFrame.return_value = 0
        mock_timeline.AddMarker.return_value = True
        
        markers = [
            EditMarker(0, 5, MarkerType.HIGHLIGHT, ""),
        ]
        
        added = apply_markers(mock_timeline, markers)
        assert added == 1


class TestDivisionByZero:
    """Test division by zero scenarios."""
    
    def test_seconds_to_frames_zero_fps(self):
        """Test frame conversion with 0 fps."""
        from markers import seconds_to_frames
        
        result = seconds_to_frames(10.0, 0.0)
        assert result == 0
    
    def test_estimate_duration_handles_zero_fps(self):
        """Test duration estimation handles 0 fps gracefully."""
        from ai_edit_assistant import estimate_duration_minutes
        
        mock_timeline = MagicMock()
        mock_timeline.GetSetting.return_value = "0"
        mock_timeline.GetStartFrame.return_value = 0
        mock_timeline.GetEndFrame.return_value = 1000
        
        # Should not raise ZeroDivisionError
        try:
            result = estimate_duration_minutes(mock_timeline)
            # Returns default or handles the error
            assert result >= 0 or result == 10  # Default fallback
        except ZeroDivisionError:
            pytest.fail("Should handle zero fps gracefully")
