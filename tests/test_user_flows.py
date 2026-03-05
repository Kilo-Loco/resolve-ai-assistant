"""
End-to-end user flow tests.
Tests complete workflows from user perspective.
"""

import pytest
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, call

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestFullPipelineFlow:
    """Test complete video → markers pipeline."""
    
    def test_video_to_markers_full_pipeline(self, tmp_path):
        """
        User flow: Video file → Transcribe → Analyze → Apply markers
        
        Steps:
        1. User has a video file
        2. System extracts audio and transcribes
        3. System analyzes transcript with AI
        4. System applies markers to timeline
        """
        from transcribe import Transcript, TranscriptSegment
        from analyze import EditMarker, MarkerType
        
        # Setup: User's video file
        video_path = tmp_path / "my_video.mp4"
        video_path.touch()
        
        # Mock transcript result
        mock_transcript = Transcript(
            segments=[
                TranscriptSegment(0.0, 5.0, "Hey everyone welcome back"),
                TranscriptSegment(5.5, 15.0, "Today I'm going to show you something amazing"),
                TranscriptSegment(20.0, 35.0, "This is the key insight you need to know"),
                TranscriptSegment(35.5, 45.0, "Let me know in the comments what you think"),
            ],
            language="en",
            duration=45.0
        )
        
        # Mock AI analysis result
        mock_markers = [
            EditMarker(5.5, 15.0, MarkerType.HIGHLIGHT, "Hook - something amazing"),
            EditMarker(15.0, 20.0, MarkerType.DEAD_AIR, "Gap in speech"),
            EditMarker(20.0, 35.0, MarkerType.SHORT_CLIP, "Key insight - standalone clip"),
        ]
        
        # Mock timeline
        mock_timeline = MagicMock()
        mock_timeline.GetSetting.return_value = "30"
        mock_timeline.GetStartFrame.return_value = 0
        mock_timeline.AddMarker.return_value = True
        applied_markers = []
        
        def track_marker(frame, color, name, note, duration, custom=""):
            applied_markers.append({
                "frame": frame,
                "color": color,
                "name": name,
                "duration": duration
            })
            return True
        
        mock_timeline.AddMarker.side_effect = track_marker
        
        # Execute pipeline
        with patch('transcribe.transcribe_video_file', return_value=mock_transcript):
            with patch('analyze.analyze_transcript', return_value=mock_markers):
                from transcribe import transcribe_video_file
                from analyze import analyze_transcript
                from markers import apply_markers
                
                # Step 1: Transcribe
                transcript = transcribe_video_file(str(video_path), "base")
                assert transcript.duration == 45.0
                assert len(transcript.segments) == 4
                
                # Step 2: Analyze
                markers = analyze_transcript(transcript, {
                    "add_highlights": True,
                    "mark_dead_air": True,
                    "find_shorts": True
                })
                assert len(markers) == 3
                
                # Step 3: Apply
                added = apply_markers(mock_timeline, markers)
                assert added == 3
        
        # Verify markers were applied correctly
        assert len(applied_markers) == 3
        
        # Check colors are correct
        colors = [m["color"] for m in applied_markers]
        assert "Green" in colors  # Highlight
        assert "Red" in colors    # Dead air
        assert "Blue" in colors   # Short clip
    
    def test_pipeline_with_silence_detection(self, tmp_path):
        """
        User flow: Video with gaps → Silence auto-detected
        
        Tests that silence detection runs alongside AI analysis.
        """
        from transcribe import Transcript, TranscriptSegment
        from analyze import analyze_for_silence, MarkerType
        
        # Transcript with obvious gaps
        transcript = Transcript(
            segments=[
                TranscriptSegment(0.0, 10.0, "Introduction"),
                # 8 second gap here (10 -> 18)
                TranscriptSegment(18.0, 30.0, "Main content"),
                # 5 second gap here (30 -> 35)
                TranscriptSegment(35.0, 45.0, "Conclusion"),
            ],
            language="en",
            duration=45.0
        )
        
        # Run silence detection
        silence_markers = analyze_for_silence(transcript, threshold_seconds=3.0)
        
        # Should find 2 gaps
        assert len(silence_markers) == 2
        
        # Verify gap timings
        assert silence_markers[0].start_seconds == 10.0
        assert silence_markers[0].end_seconds == 18.0
        assert silence_markers[1].start_seconds == 30.0
        assert silence_markers[1].end_seconds == 35.0
        
        # All should be DEAD_AIR type
        for m in silence_markers:
            assert m.marker_type == MarkerType.DEAD_AIR


class TestCacheFlow:
    """Test caching behavior for faster subsequent runs."""
    
    def test_second_run_uses_cache(self, tmp_path):
        """
        User flow: Run twice → Second run uses cache
        
        Steps:
        1. First run: transcribes (slow)
        2. Second run: uses cache (fast)
        """
        import ai_edit_assistant
        from transcribe import Transcript, TranscriptSegment
        
        # Setup cache directory
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        
        mock_transcript = Transcript(
            segments=[TranscriptSegment(0.0, 10.0, "Test content")],
            language="en",
            duration=10.0
        )
        
        with patch.object(ai_edit_assistant, 'CACHE_DIR', cache_dir):
            # First run: save to cache
            cache_key = "test_timeline_abc123"
            ai_edit_assistant.save_transcript_cache(cache_key, mock_transcript)
            
            # Verify cache file exists
            cache_file = cache_dir / f"{cache_key}.json"
            assert cache_file.exists()
            
            # Second run: load from cache
            loaded = ai_edit_assistant.get_cached_transcript(cache_key)
            
            assert loaded is not None
            assert loaded.duration == 10.0
            assert len(loaded.segments) == 1
            assert loaded.segments[0].text == "Test content"
    
    def test_cache_invalidation_on_content_change(self, tmp_path):
        """
        User flow: Timeline changes → Cache key changes → Re-transcribe
        """
        from ai_edit_assistant import get_timeline_cache_key
        
        # Timeline v1: 2 clips
        mock_timeline_v1 = MagicMock()
        mock_timeline_v1.GetName.return_value = "My Project"
        mock_timeline_v1.GetItemListInTrack.return_value = [1, 2]
        
        # Timeline v2: 3 clips (user added a clip)
        mock_timeline_v2 = MagicMock()
        mock_timeline_v2.GetName.return_value = "My Project"
        mock_timeline_v2.GetItemListInTrack.return_value = [1, 2, 3]
        
        key_v1 = get_timeline_cache_key(mock_timeline_v1)
        key_v2 = get_timeline_cache_key(mock_timeline_v2)
        
        # Keys should be different
        assert key_v1 != key_v2


class TestPreviewRejectionFlow:
    """Test user reviewing and rejecting markers in preview."""
    
    def test_user_deselects_markers(self):
        """
        User flow: Preview shows 5 markers → User deselects 2 → Only 3 applied
        """
        from analyze import EditMarker, MarkerType
        from markers import apply_markers
        
        # AI found 5 markers
        all_markers = [
            EditMarker(0, 10, MarkerType.HIGHLIGHT, "Intro - good"),
            EditMarker(15, 20, MarkerType.DEAD_AIR, "Pause - user disagrees"),
            EditMarker(25, 40, MarkerType.SHORT_CLIP, "Great clip"),
            EditMarker(45, 50, MarkerType.DEAD_AIR, "Another pause - user disagrees"),
            EditMarker(55, 70, MarkerType.HIGHLIGHT, "Conclusion"),
        ]
        
        # User reviews in preview and deselects indices 1 and 3
        selected_indices = [0, 2, 4]  # User kept markers 0, 2, 4
        
        selected_markers = [all_markers[i] for i in selected_indices]
        
        assert len(selected_markers) == 3
        
        # Apply only selected
        mock_timeline = MagicMock()
        mock_timeline.GetSetting.return_value = "24"
        mock_timeline.GetStartFrame.return_value = 0
        mock_timeline.AddMarker.return_value = True
        
        added = apply_markers(mock_timeline, selected_markers)
        
        assert added == 3
        assert mock_timeline.AddMarker.call_count == 3
        
        # Verify the rejected markers were NOT applied
        call_names = [call[0][2] for call in mock_timeline.AddMarker.call_args_list]
        assert "Intro - good" in call_names
        assert "Great clip" in call_names
        assert "Conclusion" in call_names
        assert "Pause - user disagrees" not in call_names
    
    def test_user_selects_none(self):
        """
        User flow: Preview shows markers → User deselects ALL → Nothing applied
        """
        from analyze import EditMarker, MarkerType
        from markers import apply_markers
        
        markers = [
            EditMarker(0, 10, MarkerType.HIGHLIGHT, "M1"),
            EditMarker(15, 25, MarkerType.DEAD_AIR, "M2"),
        ]
        
        # User deselects everything
        selected_indices = []
        selected_markers = [markers[i] for i in selected_indices]
        
        mock_timeline = MagicMock()
        mock_timeline.GetSetting.return_value = "24"
        mock_timeline.GetStartFrame.return_value = 0
        
        added = apply_markers(mock_timeline, selected_markers)
        
        assert added == 0
        mock_timeline.AddMarker.assert_not_called()


class TestMultiClipFlow:
    """Test handling of timelines with multiple clips."""
    
    def test_multi_clip_all_audio_extracted(self):
        """
        User flow: Timeline has 3 video clips → All audio extracted
        """
        from transcribe import get_all_media_paths
        
        # Create mock clips
        def create_mock_clip(path):
            clip = MagicMock()
            clip.GetMediaPoolItem.return_value.GetClipProperty.return_value = {
                "File Path": path
            }
            return clip
        
        clip1 = create_mock_clip("/videos/intro.mp4")
        clip2 = create_mock_clip("/videos/main.mp4")
        clip3 = create_mock_clip("/videos/outro.mp4")
        
        mock_timeline = MagicMock()
        mock_timeline.GetTrackCount.side_effect = lambda t: 1 if t == "video" else 0
        mock_timeline.GetItemListInTrack.return_value = [clip1, clip2, clip3]
        
        with patch('os.path.exists', return_value=True):
            paths = get_all_media_paths(mock_timeline)
        
        assert len(paths) == 3
        assert "/videos/intro.mp4" in paths
        assert "/videos/main.mp4" in paths
        assert "/videos/outro.mp4" in paths
    
    def test_multi_track_timeline(self):
        """
        User flow: Timeline has V1, V2 (B-roll), A1 (voiceover) → All extracted
        """
        from transcribe import get_all_media_paths
        
        def create_mock_clip(path):
            clip = MagicMock()
            clip.GetMediaPoolItem.return_value.GetClipProperty.return_value = {
                "File Path": path
            }
            return clip
        
        v1_clip = create_mock_clip("/videos/main.mp4")
        v2_clip = create_mock_clip("/videos/broll.mp4")
        a1_clip = create_mock_clip("/audio/voiceover.wav")
        
        mock_timeline = MagicMock()
        mock_timeline.GetTrackCount.side_effect = lambda t: 2 if t == "video" else 1
        
        def get_items(track_type, track_idx):
            if track_type == "video":
                return [v1_clip] if track_idx == 1 else [v2_clip]
            elif track_type == "audio":
                return [a1_clip]
            return []
        
        mock_timeline.GetItemListInTrack.side_effect = get_items
        
        with patch('os.path.exists', return_value=True):
            paths = get_all_media_paths(mock_timeline)
        
        assert len(paths) == 3
        assert "/videos/main.mp4" in paths
        assert "/videos/broll.mp4" in paths
        assert "/audio/voiceover.wav" in paths


class TestRetryRecoveryFlow:
    """Test API failure and recovery."""
    
    def test_api_fails_then_succeeds(self):
        """
        User flow: First API call fails → Retry → Success → Markers returned
        """
        from transcribe import Transcript, TranscriptSegment
        from analyze import analyze_transcript, MarkerType
        
        transcript = Transcript(
            segments=[TranscriptSegment(0.0, 10.0, "Test content")],
            language="en",
            duration=10.0
        )
        
        # First call fails, second succeeds
        mock_response_success = MagicMock()
        mock_response_success.content = [MagicMock(text='''[
            {"start": "00:00:00", "end": "00:00:10", "type": "HIGHLIGHT", "label": "Good"}
        ]''')]
        
        mock_client = MagicMock()
        call_count = [0]
        
        def mock_create(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                from anthropic import APIConnectionError
                raise APIConnectionError(request=MagicMock())
            return mock_response_success
        
        mock_client.messages.create.side_effect = mock_create
        
        with patch('anthropic.Anthropic', return_value=mock_client):
            with patch('time.sleep'):  # Don't actually sleep
                markers = analyze_transcript(
                    transcript,
                    {"add_highlights": True},
                    max_retries=3
                )
        
        # Should have retried and succeeded
        assert call_count[0] == 2
        assert len(markers) == 1
        assert markers[0].marker_type == MarkerType.HIGHLIGHT


class TestCLIUserFlows:
    """Test CLI end-to-end workflows."""
    
    def test_cli_transcribe_then_analyze(self, tmp_path):
        """
        User flow: CLI transcribe → produces JSON → CLI analyze uses JSON
        """
        from transcribe import Transcript, TranscriptSegment
        from analyze import EditMarker, MarkerType
        import cli
        
        video_path = tmp_path / "video.mp4"
        video_path.touch()
        transcript_path = tmp_path / "video.transcript.json"
        markers_path = tmp_path / "video.markers.json"
        
        mock_transcript = Transcript(
            segments=[
                TranscriptSegment(0.0, 10.0, "Hello"),
                TranscriptSegment(15.0, 25.0, "World"),
            ],
            language="en",
            duration=25.0
        )
        
        mock_markers = [
            EditMarker(0.0, 10.0, MarkerType.HIGHLIGHT, "Greeting"),
        ]
        
        # Step 1: Transcribe
        with patch('transcribe.transcribe_video_file', return_value=mock_transcript):
            args = MagicMock()
            args.video = str(video_path)
            args.model = "base"
            args.output = str(transcript_path)
            args.text = False
            
            cli.cmd_transcribe(args)
        
        assert transcript_path.exists()
        
        # Step 2: Analyze using the transcript
        with patch('analyze.analyze_transcript', return_value=mock_markers):
            with patch('analyze.analyze_for_silence', return_value=[]):
                args = MagicMock()
                args.video = None
                args.transcript = str(transcript_path)
                args.model = "base"
                args.output = str(markers_path)
                args.highlights = True
                args.dead_air = False
                args.shorts = False
                
                cli.cmd_analyze(args)
        
        assert markers_path.exists()
        
        # Verify markers file content
        with open(markers_path) as f:
            markers_data = json.load(f)
        
        assert len(markers_data) >= 1
        assert markers_data[0]["type"] == "highlight"
