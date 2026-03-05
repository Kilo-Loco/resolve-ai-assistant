"""
Tests for transcript caching functionality.
"""

import pytest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestTranscriptCaching:
    """Test transcript cache operations."""
    
    @pytest.fixture
    def temp_cache_dir(self, tmp_path):
        """Create a temporary cache directory."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        return cache_dir
    
    @pytest.fixture
    def sample_transcript_data(self):
        """Sample transcript data for caching."""
        return {
            "language": "en",
            "duration": 120.5,
            "segments": [
                {"start": 0.0, "end": 5.0, "text": "Hello world"},
                {"start": 5.5, "end": 10.0, "text": "This is a test"},
            ],
            "cached_at": "2026-03-04T19:00:00"
        }
    
    def test_save_and_load_transcript_cache(self, temp_cache_dir, sample_transcript_data):
        """Test saving and loading transcript from cache."""
        from transcribe import Transcript, TranscriptSegment
        
        # Patch CACHE_DIR
        with patch('ai_edit_assistant.CACHE_DIR', temp_cache_dir):
            from ai_edit_assistant import save_transcript_cache, get_cached_transcript
            
            # Create a transcript
            transcript = Transcript(
                segments=[
                    TranscriptSegment(0.0, 5.0, "Hello world"),
                    TranscriptSegment(5.5, 10.0, "This is a test"),
                ],
                language="en",
                duration=120.5
            )
            
            # Save it
            cache_key = "test123"
            save_transcript_cache(cache_key, transcript)
            
            # Verify file exists
            cache_file = temp_cache_dir / f"{cache_key}.json"
            assert cache_file.exists()
            
            # Load it back
            loaded = get_cached_transcript(cache_key)
            
            assert loaded is not None
            assert loaded.language == "en"
            assert loaded.duration == 120.5
            assert len(loaded.segments) == 2
            assert loaded.segments[0].text == "Hello world"
    
    def test_get_nonexistent_cache(self, temp_cache_dir):
        """Test loading non-existent cache returns None."""
        with patch('ai_edit_assistant.CACHE_DIR', temp_cache_dir):
            from ai_edit_assistant import get_cached_transcript
            
            result = get_cached_transcript("nonexistent_key")
            assert result is None
    
    def test_cache_key_generation(self):
        """Test that cache keys are generated consistently."""
        from ai_edit_assistant import get_timeline_cache_key
        
        # Mock timeline
        mock_timeline = MagicMock()
        mock_timeline.GetName.return_value = "My Timeline"
        mock_timeline.GetItemListInTrack.return_value = [1, 2, 3]  # 3 clips
        
        key1 = get_timeline_cache_key(mock_timeline)
        key2 = get_timeline_cache_key(mock_timeline)
        
        # Same timeline should produce same key
        assert key1 == key2
        assert len(key1) == 12  # MD5 hash truncated to 12 chars
    
    def test_cache_key_changes_with_content(self):
        """Test that cache key changes when timeline content changes."""
        from ai_edit_assistant import get_timeline_cache_key
        
        mock_timeline1 = MagicMock()
        mock_timeline1.GetName.return_value = "Timeline"
        mock_timeline1.GetItemListInTrack.return_value = [1, 2]
        
        mock_timeline2 = MagicMock()
        mock_timeline2.GetName.return_value = "Timeline"
        mock_timeline2.GetItemListInTrack.return_value = [1, 2, 3]  # Different clip count
        
        key1 = get_timeline_cache_key(mock_timeline1)
        key2 = get_timeline_cache_key(mock_timeline2)
        
        assert key1 != key2


class TestCostEstimation:
    """Test cost estimation functionality."""
    
    def test_estimate_duration(self):
        """Test duration estimation from timeline."""
        from ai_edit_assistant import estimate_duration_minutes
        
        mock_timeline = MagicMock()
        mock_timeline.GetSetting.return_value = "24"  # 24 fps
        mock_timeline.GetStartFrame.return_value = 0
        mock_timeline.GetEndFrame.return_value = 1440  # 1 minute at 24fps
        
        duration = estimate_duration_minutes(mock_timeline)
        assert duration == pytest.approx(1.0, rel=0.01)
    
    def test_estimate_duration_longer_video(self):
        """Test duration estimation for longer video."""
        from ai_edit_assistant import estimate_duration_minutes
        
        mock_timeline = MagicMock()
        mock_timeline.GetSetting.return_value = "30"  # 30 fps
        mock_timeline.GetStartFrame.return_value = 0
        mock_timeline.GetEndFrame.return_value = 18000  # 10 minutes at 30fps
        
        duration = estimate_duration_minutes(mock_timeline)
        assert duration == pytest.approx(10.0, rel=0.01)
    
    def test_estimate_cost(self):
        """Test cost estimation."""
        from ai_edit_assistant import estimate_cost
        
        # 10 minute video
        cost = estimate_cost(10.0, "base")
        
        assert "estimated_input_tokens" in cost
        assert "estimated_cost_usd" in cost
        assert "whisper_model" in cost
        assert "duration_minutes" in cost
        
        assert cost["duration_minutes"] == 10.0
        assert cost["whisper_model"] == "base"
        assert cost["estimated_cost_usd"] > 0
        assert cost["estimated_input_tokens"] > 0
    
    def test_estimate_cost_scales_with_duration(self):
        """Test that cost scales with video duration."""
        from ai_edit_assistant import estimate_cost
        
        cost_5min = estimate_cost(5.0)
        cost_20min = estimate_cost(20.0)
        
        # Longer video should cost more
        assert cost_20min["estimated_cost_usd"] > cost_5min["estimated_cost_usd"]
        assert cost_20min["estimated_input_tokens"] > cost_5min["estimated_input_tokens"]
