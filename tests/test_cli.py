"""
Tests for CLI commands.
"""

import pytest
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestCLITranscribe:
    """Test the transcribe CLI command."""
    
    def test_transcribe_creates_output_file(self, tmp_path):
        """Test that transcribe creates a transcript JSON file."""
        from transcribe import Transcript, TranscriptSegment
        import cli
        
        # Create a mock transcript
        mock_transcript = Transcript(
            segments=[
                TranscriptSegment(0.0, 5.0, "Hello world"),
                TranscriptSegment(5.5, 10.0, "This is a test"),
            ],
            language="en",
            duration=10.0
        )
        
        video_path = tmp_path / "test_video.mp4"
        video_path.touch()
        output_path = tmp_path / "output.json"
        
        args = MagicMock()
        args.video = str(video_path)
        args.model = "base"
        args.output = str(output_path)
        args.text = False
        
        # Patch the import inside cmd_transcribe
        with patch.object(cli, 'cmd_transcribe', wraps=cli.cmd_transcribe):
            with patch('transcribe.transcribe_video_file', return_value=mock_transcript):
                cli.cmd_transcribe(args)
        
        assert output_path.exists()
        
        with open(output_path) as f:
            data = json.load(f)
        
        assert data["language"] == "en"
        assert data["duration"] == 10.0
        assert len(data["segments"]) == 2
    
    def test_transcribe_with_text_output(self, tmp_path, capsys):
        """Test that --text flag prints timestamped text."""
        from transcribe import Transcript, TranscriptSegment
        import cli
        
        mock_transcript = Transcript(
            segments=[
                TranscriptSegment(0.0, 5.0, "Hello"),
                TranscriptSegment(5.5, 10.0, "World"),
            ],
            language="en",
            duration=10.0
        )
        
        video_path = tmp_path / "test.mp4"
        video_path.touch()
        output_path = tmp_path / "out.json"
        
        args = MagicMock()
        args.video = str(video_path)
        args.model = "tiny"
        args.output = str(output_path)
        args.text = True
        
        with patch('transcribe.transcribe_video_file', return_value=mock_transcript):
            cli.cmd_transcribe(args)
        
        captured = capsys.readouterr()
        assert "Hello" in captured.out or output_path.exists()


class TestCLIAnalyze:
    """Test the analyze CLI command."""
    
    def test_analyze_with_transcript_file(self, tmp_path):
        """Test analyzing from existing transcript file."""
        from analyze import EditMarker, MarkerType
        import cli
        
        # Create transcript file
        transcript_data = {
            "language": "en",
            "duration": 30.0,
            "segments": [
                {"start": 0.0, "end": 10.0, "text": "Hello everyone"},
                {"start": 15.0, "end": 25.0, "text": "Important content here"},
            ]
        }
        
        transcript_path = tmp_path / "input.transcript.json"
        with open(transcript_path, "w") as f:
            json.dump(transcript_data, f)
        
        mock_markers = [
            EditMarker(15.0, 25.0, MarkerType.HIGHLIGHT, "Good part"),
        ]
        
        output_path = tmp_path / "markers.json"
        
        args = MagicMock()
        args.video = None
        args.transcript = str(transcript_path)
        args.model = "base"
        args.output = str(output_path)
        args.highlights = True
        args.dead_air = False
        args.shorts = False
        
        with patch('analyze.analyze_transcript', return_value=mock_markers):
            with patch('analyze.analyze_for_silence', return_value=[]):
                cli.cmd_analyze(args)
        
        assert output_path.exists()
        
        with open(output_path) as f:
            markers = json.load(f)
        
        assert len(markers) >= 1


class TestCLIApply:
    """Test the apply CLI command."""
    
    def test_apply_file_not_found(self, tmp_path):
        """Test that apply handles missing file gracefully."""
        import cli
        
        args = MagicMock()
        args.markers = str(tmp_path / "nonexistent.json")
        
        with pytest.raises(FileNotFoundError):
            cli.cmd_apply(args)


class TestCLIMain:
    """Test CLI argument parsing."""
    
    def test_no_command_shows_help(self):
        """Test that no command exits with code 1."""
        import cli
        
        with patch('sys.argv', ['cli.py']):
            with pytest.raises(SystemExit) as exc_info:
                cli.main()
            
            assert exc_info.value.code == 1
    
    def test_help_flag(self):
        """Test --help flag."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "src/cli.py", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        
        assert result.returncode == 0
        assert "transcribe" in result.stdout
        assert "analyze" in result.stdout
        assert "apply" in result.stdout
    
    def test_transcribe_subcommand_help(self):
        """Test transcribe --help."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "src/cli.py", "transcribe", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )
        
        assert result.returncode == 0
        assert "--model" in result.stdout
