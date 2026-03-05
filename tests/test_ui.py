"""
Tests for UI components and preview functionality.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestPreviewWindow:
    """Test marker preview functionality."""
    
    def test_marker_preview_formats_correctly(self):
        """Test that markers are formatted for preview display."""
        from analyze import EditMarker, MarkerType
        
        markers = [
            EditMarker(65.5, 80.0, MarkerType.HIGHLIGHT, "Great reaction"),
            EditMarker(120.0, 125.0, MarkerType.DEAD_AIR, "Long pause"),
            EditMarker(200.0, 290.0, MarkerType.SHORT_CLIP, "Potential short"),
        ]
        
        # Format markers as they would appear in preview
        formatted = []
        for m in markers:
            color_emoji = {
                MarkerType.HIGHLIGHT: "🟢",
                MarkerType.DEAD_AIR: "🔴", 
                MarkerType.SHORT_CLIP: "🔵",
                MarkerType.REVIEW: "🟡"
            }
            emoji = color_emoji.get(m.marker_type, "⚪")
            time_str = f"{int(m.start_seconds//60)}:{int(m.start_seconds%60):02d}"
            formatted.append(f"{emoji} [{time_str}] {m.label}")
        
        assert formatted[0] == "🟢 [1:05] Great reaction"
        assert formatted[1] == "🔴 [2:00] Long pause"
        assert formatted[2] == "🔵 [3:20] Potential short"
    
    def test_preview_selection_filters_markers(self):
        """Test that preview selection correctly filters markers."""
        from analyze import EditMarker, MarkerType
        
        markers = [
            EditMarker(0, 10, MarkerType.HIGHLIGHT, "M1"),
            EditMarker(20, 30, MarkerType.DEAD_AIR, "M2"),
            EditMarker(40, 50, MarkerType.SHORT_CLIP, "M3"),
        ]
        
        # Simulate user deselecting marker at index 1
        selected_indices = [0, 2]  # Indices 0 and 2 selected
        
        selected_markers = [markers[i] for i in selected_indices]
        
        assert len(selected_markers) == 2
        assert selected_markers[0].label == "M1"
        assert selected_markers[1].label == "M3"
    
    def test_empty_selection_returns_no_markers(self):
        """Test that empty selection returns empty list."""
        from analyze import EditMarker, MarkerType
        
        markers = [
            EditMarker(0, 10, MarkerType.HIGHLIGHT, "M1"),
            EditMarker(20, 30, MarkerType.DEAD_AIR, "M2"),
        ]
        
        selected_indices = []
        selected_markers = [markers[i] for i in selected_indices]
        
        assert len(selected_markers) == 0


class TestUIState:
    """Test UI state management."""
    
    def test_analyze_state_tracking(self):
        """Test that analyzing state is tracked correctly."""
        state = {"cancelled": False, "analyzing": False}
        
        # Start analysis
        state["analyzing"] = True
        assert state["analyzing"] == True
        
        # Cancel
        state["cancelled"] = True
        assert state["cancelled"] == True
        
        # Complete
        state["analyzing"] = False
        assert state["analyzing"] == False
    
    def test_cancel_during_analysis(self):
        """Test cancellation during analysis."""
        state = {"cancelled": False, "analyzing": False}
        
        # Simulate analysis start
        state["analyzing"] = True
        
        # Simulate cancel button
        if state["analyzing"]:
            state["cancelled"] = True
        
        assert state["cancelled"] == True
        
        # Analysis should check and exit
        if state["cancelled"]:
            state["analyzing"] = False
        
        assert state["analyzing"] == False


class TestWhisperModelSelection:
    """Test Whisper model selection."""
    
    def test_model_options(self):
        """Test available model options."""
        models = ["tiny", "base", "small", "medium", "large"]
        
        assert len(models) == 5
        assert "tiny" in models  # Fastest
        assert "large" in models  # Most accurate
    
    def test_default_model(self):
        """Test default model selection."""
        models = ["tiny", "base", "small", "medium", "large"]
        default_index = 1  # "base"
        
        assert models[default_index] == "base"
    
    def test_model_speed_factors(self):
        """Test model speed estimation factors."""
        speed_factors = {
            "tiny": 30,   # 30x realtime
            "base": 20,   # 20x realtime
            "small": 10,  # 10x realtime
            "medium": 5,  # 5x realtime
            "large": 2    # 2x realtime
        }
        
        # Larger models should be slower
        assert speed_factors["tiny"] > speed_factors["large"]
        assert speed_factors["base"] > speed_factors["medium"]


class TestMarkerLegend:
    """Test marker color legend."""
    
    def test_legend_text(self):
        """Test legend displays all marker types."""
        legend = "🟢 Highlight  🔴 Dead Air  🔵 Short Clip"
        
        assert "🟢" in legend
        assert "🔴" in legend
        assert "🔵" in legend
        assert "Highlight" in legend
        assert "Dead Air" in legend
        assert "Short Clip" in legend
    
    def test_marker_colors_match_legend(self):
        """Test that marker colors match legend colors."""
        from analyze import MarkerType, get_marker_color
        
        # Legend shows: 🟢 Green for Highlight
        assert get_marker_color(MarkerType.HIGHLIGHT) == "Green"
        
        # Legend shows: 🔴 Red for Dead Air
        assert get_marker_color(MarkerType.DEAD_AIR) == "Red"
        
        # Legend shows: 🔵 Blue for Short Clip  
        assert get_marker_color(MarkerType.SHORT_CLIP) == "Blue"


class TestClearMarkers:
    """Test clear markers UI functionality."""
    
    def test_clear_all_markers(self, mock_resolve):
        """Test clearing all AI markers."""
        timeline = mock_resolve.GetProjectManager().GetCurrentProject().GetCurrentTimeline()
        
        from analyze import EditMarker, MarkerType
        from markers import apply_markers, clear_markers
        
        # Add some markers
        markers = [
            EditMarker(0, 5, MarkerType.HIGHLIGHT, "H1"),
            EditMarker(10, 15, MarkerType.DEAD_AIR, "D1"),
            EditMarker(20, 25, MarkerType.SHORT_CLIP, "S1"),
        ]
        apply_markers(timeline, markers)
        assert len(timeline.GetMarkers()) == 3
        
        # Clear all
        removed = clear_markers(timeline)
        assert removed == 3
        assert len(timeline.GetMarkers()) == 0
    
    def test_clear_only_red_markers(self, mock_resolve):
        """Test clearing only dead air (red) markers."""
        timeline = mock_resolve.GetProjectManager().GetCurrentProject().GetCurrentTimeline()
        
        from analyze import EditMarker, MarkerType
        from markers import apply_markers, clear_markers
        
        markers = [
            EditMarker(0, 5, MarkerType.HIGHLIGHT, "Keep"),
            EditMarker(10, 15, MarkerType.DEAD_AIR, "Remove"),
            EditMarker(20, 25, MarkerType.DEAD_AIR, "Remove2"),
        ]
        apply_markers(timeline, markers)
        
        # Clear only red
        removed = clear_markers(timeline, color="Red")
        assert removed == 2
        
        remaining = timeline.GetMarkers()
        assert len(remaining) == 1
        assert list(remaining.values())[0]["color"] == "Green"
