"""
Tests for multi-clip timeline handling.
"""

import pytest
import os
from unittest.mock import MagicMock, patch


class TestMultiClipTimeline:
    """Test handling of timelines with multiple clips."""
    
    def test_get_all_media_paths_single_track(self):
        """Test getting media paths from single video track."""
        from transcribe import get_all_media_paths
        
        # Mock timeline with 2 clips on track 1
        mock_clip1 = MagicMock()
        mock_clip1.GetMediaPoolItem.return_value.GetClipProperty.return_value = {
            "File Path": "/path/to/video1.mp4"
        }
        
        mock_clip2 = MagicMock()
        mock_clip2.GetMediaPoolItem.return_value.GetClipProperty.return_value = {
            "File Path": "/path/to/video2.mp4"
        }
        
        mock_timeline = MagicMock()
        mock_timeline.GetTrackCount.side_effect = lambda t: 1 if t == "video" else 0
        mock_timeline.GetItemListInTrack.return_value = [mock_clip1, mock_clip2]
        
        with patch('os.path.exists', return_value=True):
            paths = get_all_media_paths(mock_timeline)
        
        assert len(paths) == 2
        assert "/path/to/video1.mp4" in paths
        assert "/path/to/video2.mp4" in paths
    
    def test_get_all_media_paths_multiple_tracks(self):
        """Test getting media paths from multiple video tracks."""
        from transcribe import get_all_media_paths
        
        mock_clip_v1 = MagicMock()
        mock_clip_v1.GetMediaPoolItem.return_value.GetClipProperty.return_value = {
            "File Path": "/path/to/main.mp4"
        }
        
        mock_clip_v2 = MagicMock()
        mock_clip_v2.GetMediaPoolItem.return_value.GetClipProperty.return_value = {
            "File Path": "/path/to/broll.mp4"
        }
        
        mock_timeline = MagicMock()
        mock_timeline.GetTrackCount.side_effect = lambda t: 2 if t == "video" else 0
        
        def get_items(track_type, track_idx):
            if track_type == "video":
                if track_idx == 1:
                    return [mock_clip_v1]
                elif track_idx == 2:
                    return [mock_clip_v2]
            return []
        
        mock_timeline.GetItemListInTrack.side_effect = get_items
        
        with patch('os.path.exists', return_value=True):
            paths = get_all_media_paths(mock_timeline)
        
        assert len(paths) == 2
    
    def test_get_all_media_paths_deduplication(self):
        """Test that duplicate paths are not included."""
        from transcribe import get_all_media_paths
        
        # Same clip used twice
        mock_clip1 = MagicMock()
        mock_clip1.GetMediaPoolItem.return_value.GetClipProperty.return_value = {
            "File Path": "/path/to/video.mp4"
        }
        
        mock_clip2 = MagicMock()
        mock_clip2.GetMediaPoolItem.return_value.GetClipProperty.return_value = {
            "File Path": "/path/to/video.mp4"  # Same path
        }
        
        mock_timeline = MagicMock()
        mock_timeline.GetTrackCount.side_effect = lambda t: 1 if t == "video" else 0
        mock_timeline.GetItemListInTrack.return_value = [mock_clip1, mock_clip2]
        
        with patch('os.path.exists', return_value=True):
            paths = get_all_media_paths(mock_timeline)
        
        assert len(paths) == 1  # Deduplicated
    
    def test_get_all_media_paths_includes_audio_tracks(self):
        """Test that audio-only tracks are included."""
        from transcribe import get_all_media_paths
        
        mock_video_clip = MagicMock()
        mock_video_clip.GetMediaPoolItem.return_value.GetClipProperty.return_value = {
            "File Path": "/path/to/video.mp4"
        }
        
        mock_audio_clip = MagicMock()
        mock_audio_clip.GetMediaPoolItem.return_value.GetClipProperty.return_value = {
            "File Path": "/path/to/voiceover.wav"
        }
        
        mock_timeline = MagicMock()
        mock_timeline.GetTrackCount.side_effect = lambda t: 1
        
        def get_items(track_type, track_idx):
            if track_type == "video":
                return [mock_video_clip]
            elif track_type == "audio":
                return [mock_audio_clip]
            return []
        
        mock_timeline.GetItemListInTrack.side_effect = get_items
        
        with patch('os.path.exists', return_value=True):
            paths = get_all_media_paths(mock_timeline)
        
        assert len(paths) == 2
        assert "/path/to/video.mp4" in paths
        assert "/path/to/voiceover.wav" in paths
    
    def test_get_all_media_paths_skips_missing_files(self):
        """Test that missing files are skipped."""
        from transcribe import get_all_media_paths
        
        mock_clip1 = MagicMock()
        mock_clip1.GetMediaPoolItem.return_value.GetClipProperty.return_value = {
            "File Path": "/path/to/exists.mp4"
        }
        
        mock_clip2 = MagicMock()
        mock_clip2.GetMediaPoolItem.return_value.GetClipProperty.return_value = {
            "File Path": "/path/to/missing.mp4"
        }
        
        mock_timeline = MagicMock()
        mock_timeline.GetTrackCount.side_effect = lambda t: 1 if t == "video" else 0
        mock_timeline.GetItemListInTrack.return_value = [mock_clip1, mock_clip2]
        
        def file_exists(path):
            return "exists" in path
        
        with patch('os.path.exists', side_effect=file_exists):
            paths = get_all_media_paths(mock_timeline)
        
        assert len(paths) == 1
        assert "/path/to/exists.mp4" in paths
    
    def test_empty_timeline(self):
        """Test handling of empty timeline."""
        from transcribe import get_all_media_paths
        
        mock_timeline = MagicMock()
        mock_timeline.GetTrackCount.return_value = 0
        mock_timeline.GetItemListInTrack.return_value = []
        
        paths = get_all_media_paths(mock_timeline)
        
        assert len(paths) == 0
