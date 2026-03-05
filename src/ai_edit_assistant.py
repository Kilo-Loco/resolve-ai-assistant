#!/usr/bin/env python3
"""
AI Edit Assistant for DaVinci Resolve
Analyzes timeline, adds markers, extracts shorts, generates rough cuts.
"""

import sys
import os
import json
import hashlib
from pathlib import Path
from datetime import datetime

# Add our modules to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Cache directory for transcripts
CACHE_DIR = Path.home() / ".resolve-ai-assistant" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_resolve():
    """Get the Resolve application object."""
    try:
        import DaVinciResolveScript as dvr
        return dvr.scriptapp("Resolve")
    except ImportError:
        # Set up environment for external execution
        if sys.platform == "darwin":
            script_api = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
            script_lib = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
        elif sys.platform == "win32":
            script_api = os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"),
                                      "Blackmagic Design", "DaVinci Resolve", "Support", "Developer", "Scripting")
            script_lib = os.path.join(os.environ.get("PROGRAMFILES", "C:\\Program Files"),
                                      "Blackmagic Design", "DaVinci Resolve", "fusionscript.dll")
        elif sys.platform.startswith("linux"):
            script_api = "/opt/resolve/Developer/Scripting"
            script_lib = "/opt/resolve/libs/Fusion/fusionscript.so"
        else:
            raise RuntimeError(f"Unsupported platform: {sys.platform}")
        
        os.environ["RESOLVE_SCRIPT_API"] = script_api
        os.environ["RESOLVE_SCRIPT_LIB"] = script_lib
        sys.path.append(os.path.join(script_api, "Modules"))
        
        import DaVinciResolveScript as dvr
        return dvr.scriptapp("Resolve")


def get_current_timeline(resolve):
    """Get the current project and timeline."""
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject()
    if not project:
        return None, None, "No project open"
    
    timeline = project.GetCurrentTimeline()
    if not timeline:
        return project, None, "No timeline selected"
    
    return project, timeline, None


def get_timeline_cache_key(timeline):
    """Generate a cache key for the timeline based on its content."""
    name = timeline.GetName()
    # Include clip count and duration for cache invalidation
    video_items = timeline.GetItemListInTrack("video", 1) or []
    clip_info = f"{len(video_items)}"
    return hashlib.md5(f"{name}:{clip_info}".encode()).hexdigest()[:12]


def get_cached_transcript(cache_key):
    """Load transcript from cache if available."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                data = json.load(f)
            from transcribe import Transcript, TranscriptSegment
            return Transcript(
                segments=[TranscriptSegment(s["start"], s["end"], s["text"]) for s in data["segments"]],
                language=data.get("language", "en"),
                duration=data.get("duration", 0)
            )
        except Exception:
            pass
    return None


def save_transcript_cache(cache_key, transcript):
    """Save transcript to cache."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    data = {
        "language": transcript.language,
        "duration": transcript.duration,
        "segments": [{"start": s.start, "end": s.end, "text": s.text} for s in transcript.segments],
        "cached_at": datetime.now().isoformat()
    }
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)


def estimate_duration_minutes(timeline):
    """Estimate timeline duration in minutes for cost estimation."""
    try:
        fps = float(timeline.GetSetting("timelineFrameRate") or 24)
        end_frame = timeline.GetEndFrame()
        start_frame = timeline.GetStartFrame()
        duration_seconds = (end_frame - start_frame) / fps
        return duration_seconds / 60
    except Exception:
        return 10  # Default estimate


def estimate_cost(duration_minutes, whisper_model="base"):
    """Estimate processing cost."""
    # Whisper is local, no cost
    # Claude costs ~$3/1M input tokens, ~$15/1M output tokens
    # Rough estimate: 150 words/min speech, ~200 tokens/min
    estimated_tokens = int(duration_minutes * 200)
    # Add prompt overhead
    estimated_tokens += 500
    # Cost estimate (Claude Sonnet)
    input_cost = (estimated_tokens / 1_000_000) * 3
    output_cost = (1000 / 1_000_000) * 15  # ~1000 output tokens typical
    return {
        "estimated_input_tokens": estimated_tokens,
        "estimated_cost_usd": round(input_cost + output_cost, 4),
        "whisper_model": whisper_model,
        "duration_minutes": round(duration_minutes, 1)
    }


def create_ui(resolve, fusion):
    """Create the UI dialog for the assistant."""
    ui = fusion.UIManager
    disp = ui.UIDispatcher(fusion)
    
    # Window definition - larger to accommodate new features
    win = disp.AddWindow({
        "ID": "AIEditAssistant",
        "WindowTitle": "AI Edit Assistant",
        "Geometry": [100, 100, 450, 520],
    }, [
        ui.VGroup({"Spacing": 8}, [
            # Header
            ui.Label({
                "ID": "Header",
                "Text": "🎬 AI Edit Assistant",
                "Alignment": {"AlignHCenter": True},
                "Font": ui.Font({"PixelSize": 18, "Bold": True}),
            }),
            
            # Marker legend
            ui.Label({
                "ID": "Legend",
                "Text": "🟢 Highlight  🔴 Dead Air  🔵 Short Clip",
                "Alignment": {"AlignHCenter": True},
            }),
            
            ui.HGroup([
                ui.Label({"Text": "Timeline:", "Weight": 0.3}),
                ui.Label({"ID": "TimelineName", "Text": "(none)", "Weight": 0.7}),
            ]),
            
            ui.HGroup([
                ui.Label({"Text": "Duration:", "Weight": 0.3}),
                ui.Label({"ID": "Duration", "Text": "0 min", "Weight": 0.35}),
                ui.Label({"Text": "Est. Cost:", "Weight": 0.15}),
                ui.Label({"ID": "EstCost", "Text": "$0.00", "Weight": 0.2}),
            ]),
            
            ui.VGap(5),
            
            # Whisper model selection
            ui.HGroup([
                ui.Label({"Text": "Whisper Model:", "Weight": 0.35}),
                ui.ComboBox({
                    "ID": "WhisperModel",
                    "Weight": 0.65,
                }),
            ]),
            
            ui.VGap(5),
            
            # Analysis options
            ui.Label({"Text": "Analysis Options:", "Font": ui.Font({"Bold": True})}),
            
            ui.CheckBox({"ID": "AddHighlights", "Text": "Find highlights (green markers)", "Checked": True}),
            ui.CheckBox({"ID": "MarkDeadAir", "Text": "Mark dead air for removal (red markers)", "Checked": True}),
            ui.CheckBox({"ID": "FindShorts", "Text": "Identify potential shorts (blue markers)", "Checked": True}),
            
            ui.VGap(5),
            
            # Actions (rough cut disabled until implemented)
            ui.Label({"Text": "Actions:", "Font": ui.Font({"Bold": True})}),
            
            ui.CheckBox({"ID": "CreateShortsTimeline", "Text": "Create separate Shorts timeline", "Checked": False}),
            ui.CheckBox({
                "ID": "CreateRoughCut",
                "Text": "Generate rough cut (coming soon)",
                "Checked": False,
                "Enabled": False,  # P0 fix: disable unimplemented feature
            }),
            
            ui.VGap(5),
            
            # Cache info
            ui.HGroup([
                ui.CheckBox({"ID": "UseCache", "Text": "Use cached transcript if available", "Checked": True}),
            ]),
            
            ui.VGap(5),
            
            # Status
            ui.Label({"ID": "Status", "Text": "", "Alignment": {"AlignHCenter": True}}),
            
            # Progress with percentage
            ui.HGroup([
                ui.ProgressBar({"ID": "Progress", "Value": 0, "Maximum": 100, "Weight": 0.85}),
                ui.Label({"ID": "ProgressPct", "Text": "0%", "Weight": 0.15}),
            ]),
            
            # ETA
            ui.Label({"ID": "ETA", "Text": "", "Alignment": {"AlignHCenter": True}}),
            
            ui.VGap(5),
            
            # Buttons row 1
            ui.HGroup([
                ui.Button({"ID": "Analyze", "Text": "🔍 Analyze", "Weight": 0.5}),
                ui.Button({"ID": "Cancel", "Text": "Cancel", "Weight": 0.5}),
            ]),
            
            # Buttons row 2 - Clear markers
            ui.HGroup([
                ui.Button({"ID": "ClearAll", "Text": "🗑️ Clear All AI Markers", "Weight": 0.5}),
                ui.Button({"ID": "ClearByColor", "Text": "Clear by Color...", "Weight": 0.5}),
            ]),
        ]),
    ])
    
    return win, disp


def create_preview_window(fusion, markers):
    """Create a preview window to review markers before applying."""
    ui = fusion.UIManager
    disp = ui.UIDispatcher(fusion)
    
    # Build marker list items
    marker_items = []
    for i, m in enumerate(markers):
        from analyze import MarkerType
        color_emoji = {"HIGHLIGHT": "🟢", "DEAD_AIR": "🔴", "SHORT_CLIP": "🔵", "REVIEW": "🟡"}
        emoji = color_emoji.get(m.marker_type.name, "⚪")
        time_str = f"{int(m.start_seconds//60)}:{int(m.start_seconds%60):02d}"
        marker_items.append(f"{emoji} [{time_str}] {m.label}")
    
    win = disp.AddWindow({
        "ID": "MarkerPreview",
        "WindowTitle": "Review Markers",
        "Geometry": [150, 150, 500, 400],
    }, [
        ui.VGroup({"Spacing": 10}, [
            ui.Label({
                "Text": f"Found {len(markers)} markers. Review and apply:",
                "Font": ui.Font({"Bold": True}),
            }),
            
            ui.Tree({
                "ID": "MarkerList",
                "Weight": 1.0,
                "HeaderHidden": True,
                "SelectionMode": "ExtendedSelection",
            }),
            
            ui.Label({"Text": "Shift+Click to select multiple. Selected markers will be applied."}),
            
            ui.HGroup([
                ui.Button({"ID": "SelectAll", "Text": "Select All", "Weight": 0.25}),
                ui.Button({"ID": "SelectNone", "Text": "Select None", "Weight": 0.25}),
                ui.Button({"ID": "ApplySelected", "Text": "✅ Apply Selected", "Weight": 0.25}),
                ui.Button({"ID": "CancelPreview", "Text": "Cancel", "Weight": 0.25}),
            ]),
        ]),
    ])
    
    items = win.GetItems()
    
    # Populate tree
    tree = items["MarkerList"]
    header = tree.NewItem()
    header.Text[0] = "Markers"
    tree.SetHeaderItem(header)
    
    tree_items = []
    for i, text in enumerate(marker_items):
        item = tree.NewItem()
        item.Text[0] = text
        tree.AddTopLevelItem(item)
        item.Selected = True  # Select all by default
        tree_items.append(item)
    
    # Result storage
    result = {"selected_indices": list(range(len(markers))), "cancelled": False}
    
    def on_select_all(ev):
        for item in tree_items:
            item.Selected = True
    
    def on_select_none(ev):
        for item in tree_items:
            item.Selected = False
    
    def on_apply(ev):
        result["selected_indices"] = [i for i, item in enumerate(tree_items) if item.Selected]
        disp.ExitLoop()
    
    def on_cancel(ev):
        result["cancelled"] = True
        disp.ExitLoop()
    
    def on_close(ev):
        result["cancelled"] = True
        disp.ExitLoop()
    
    win.On.SelectAll.Clicked = on_select_all
    win.On.SelectNone.Clicked = on_select_none
    win.On.ApplySelected.Clicked = on_apply
    win.On.CancelPreview.Clicked = on_cancel
    win.On.MarkerPreview.Close = on_close
    
    win.Show()
    disp.RunLoop()
    win.Hide()
    
    return result


def on_analyze(resolve, fusion, win, items, state):
    """Handle the Analyze button click."""
    from transcribe import transcribe_timeline_audio, transcribe_video_file
    from analyze import analyze_transcript, analyze_for_silence
    from markers import apply_markers
    import time
    
    project, timeline, err = get_current_timeline(resolve)
    if err:
        items["Status"].Text = f"❌ {err}"
        return
    
    def update_progress(value, status=None, eta=None):
        items["Progress"].Value = value
        items["ProgressPct"].Text = f"{value}%"
        if status:
            items["Status"].Text = status
        if eta:
            items["ETA"].Text = eta
        else:
            items["ETA"].Text = ""
    
    whisper_model = items["WhisperModel"].CurrentText or "base"
    use_cache = items["UseCache"].Checked
    
    try:
        state["analyzing"] = True
        start_time = time.time()
        
        # Check cache first
        cache_key = get_timeline_cache_key(timeline)
        transcript = None
        
        if use_cache:
            transcript = get_cached_transcript(cache_key)
            if transcript:
                update_progress(30, "📋 Using cached transcript...")
        
        if not transcript:
            update_progress(5, "📝 Extracting audio from timeline...")
            
            # Estimate time based on duration
            duration_min = estimate_duration_minutes(timeline)
            # Whisper processes ~10-30x realtime depending on model
            speed_factor = {"tiny": 30, "base": 20, "small": 10, "medium": 5, "large": 2}.get(whisper_model, 10)
            eta_seconds = int((duration_min * 60) / speed_factor)
            eta_str = f"⏱️ Estimated: {eta_seconds//60}m {eta_seconds%60}s"
            
            update_progress(10, f"🎤 Transcribing with {whisper_model} model...", eta_str)
            
            # Transcribe (this takes time)
            transcript = transcribe_timeline_audio(timeline, model_name=whisper_model)
            
            # Cache the result
            save_transcript_cache(cache_key, transcript)
            update_progress(50, "📋 Transcript cached for future use")
        
        # Check if cancelled
        if state.get("cancelled"):
            update_progress(0, "⚠️ Cancelled")
            return
        
        # Analyze with AI
        update_progress(55, "🧠 Analyzing content with AI...")
        
        options = {
            "add_highlights": items["AddHighlights"].Checked,
            "mark_dead_air": items["MarkDeadAir"].Checked,
            "find_shorts": items["FindShorts"].Checked,
        }
        
        markers = []
        
        # Get AI analysis if any options selected
        if any(options.values()):
            try:
                markers = analyze_transcript(transcript, options)
            except Exception as e:
                update_progress(60, f"⚠️ AI analysis failed: {str(e)[:50]}...")
                # Fall back to silence detection only
                if options.get("mark_dead_air"):
                    markers = analyze_for_silence(transcript)
        
        # Also detect silence gaps (fast, no API)
        if options.get("mark_dead_air"):
            silence_markers = analyze_for_silence(transcript)
            # Merge, avoiding duplicates
            existing_ranges = set((m.start_seconds, m.end_seconds) for m in markers)
            for sm in silence_markers:
                if (sm.start_seconds, sm.end_seconds) not in existing_ranges:
                    markers.append(sm)
        
        if state.get("cancelled"):
            update_progress(0, "⚠️ Cancelled")
            return
        
        update_progress(75, f"✅ Found {len(markers)} markers")
        
        if not markers:
            update_progress(100, "✅ Analysis complete - no markers to add")
            return
        
        # Show preview window for user to review
        update_progress(80, "👀 Review markers...")
        preview_result = create_preview_window(fusion, markers)
        
        if preview_result["cancelled"]:
            update_progress(0, "⚠️ Cancelled")
            return
        
        # Filter to selected markers
        selected_indices = preview_result["selected_indices"]
        selected_markers = [markers[i] for i in selected_indices]
        
        if not selected_markers:
            update_progress(100, "✅ No markers selected")
            return
        
        # Apply markers
        update_progress(90, f"🎯 Adding {len(selected_markers)} markers...")
        added = apply_markers(timeline, selected_markers)
        
        # Create shorts timeline if requested
        if items["CreateShortsTimeline"].Checked:
            update_progress(95, "✂️ Creating shorts timeline...")
            from analyze import MarkerType
            shorts = [m for m in selected_markers if m.marker_type == MarkerType.SHORT_CLIP]
            if shorts:
                # TODO: Implement create_subclip_timeline properly
                update_progress(98, f"⚠️ Shorts timeline: {len(shorts)} clips identified (manual extraction needed)")
        
        elapsed = int(time.time() - start_time)
        update_progress(100, f"✅ Done! Added {added} markers in {elapsed}s")
        
    except Exception as e:
        items["Status"].Text = f"❌ Error: {str(e)}"
        items["Progress"].Value = 0
        items["ProgressPct"].Text = "0%"
        items["ETA"].Text = ""
        import traceback
        traceback.print_exc()
    finally:
        state["analyzing"] = False


def on_clear_markers(timeline, color=None):
    """Clear AI-added markers from timeline."""
    from markers import clear_markers
    return clear_markers(timeline, color)


def main():
    """Main entry point."""
    resolve = get_resolve()
    if not resolve:
        print("Error: Could not connect to DaVinci Resolve")
        return
    
    fusion = resolve.Fusion()
    
    # Update timeline name in UI
    project, timeline, err = get_current_timeline(resolve)
    
    win, disp = create_ui(resolve, fusion)
    items = win.GetItems()
    
    # State for cancellation
    state = {"cancelled": False, "analyzing": False}
    
    # Populate whisper model dropdown
    whisper_combo = items["WhisperModel"]
    models = ["tiny", "base", "small", "medium", "large"]
    for m in models:
        whisper_combo.AddItem(m)
    whisper_combo.CurrentIndex = 1  # Default to "base"
    
    if timeline:
        items["TimelineName"].Text = timeline.GetName()
        duration = estimate_duration_minutes(timeline)
        items["Duration"].Text = f"{duration:.1f} min"
        cost = estimate_cost(duration)
        items["EstCost"].Text = f"${cost['estimated_cost_usd']:.3f}"
    else:
        items["TimelineName"].Text = "(no timeline)"
    
    # Event handlers
    def on_close(ev):
        state["cancelled"] = True
        disp.ExitLoop()
    
    def on_analyze_click(ev):
        state["cancelled"] = False
        on_analyze(resolve, fusion, win, items, state)
    
    def on_cancel_click(ev):
        if state["analyzing"]:
            state["cancelled"] = True
            items["Status"].Text = "⏳ Cancelling..."
        else:
            disp.ExitLoop()
    
    def on_clear_all_click(ev):
        _, tl, err = get_current_timeline(resolve)
        if tl:
            removed = on_clear_markers(tl)
            items["Status"].Text = f"🗑️ Cleared {removed} markers"
        else:
            items["Status"].Text = "❌ No timeline"
    
    def on_clear_by_color_click(ev):
        # Simple implementation - clear green, red, or blue based on prompt
        items["Status"].Text = "Use Clear All, or manually delete markers by color in Resolve"
    
    win.On.AIEditAssistant.Close = on_close
    win.On.Analyze.Clicked = on_analyze_click
    win.On.Cancel.Clicked = on_cancel_click
    win.On.ClearAll.Clicked = on_clear_all_click
    win.On.ClearByColor.Clicked = on_clear_by_color_click
    
    win.Show()
    disp.RunLoop()
    win.Hide()


if __name__ == "__main__":
    main()
