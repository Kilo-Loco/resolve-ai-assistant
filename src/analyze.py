#!/usr/bin/env python3
"""
Analysis module using Claude to identify highlights, dead air, and shorts.
"""

import os
import json
from dataclasses import dataclass, asdict
from typing import List, Optional
from enum import Enum


class MarkerType(Enum):
    HIGHLIGHT = "highlight"      # Green - good content, keep
    DEAD_AIR = "dead_air"        # Red - silence, filler, cut
    SHORT_CLIP = "short"         # Blue - potential short/clip
    REVIEW = "review"            # Yellow - needs human review


@dataclass
class EditMarker:
    """A marker to be placed on the timeline."""
    start_seconds: float
    end_seconds: float
    marker_type: MarkerType
    label: str
    note: str = ""
    confidence: float = 1.0


def get_marker_color(marker_type: MarkerType) -> str:
    """Get DaVinci Resolve marker color for marker type."""
    colors = {
        MarkerType.HIGHLIGHT: "Green",
        MarkerType.DEAD_AIR: "Red",
        MarkerType.SHORT_CLIP: "Blue",
        MarkerType.REVIEW: "Yellow",
    }
    return colors.get(marker_type, "Yellow")


def analyze_transcript(transcript, options: dict, max_retries: int = 3) -> List[EditMarker]:
    """
    Analyze transcript using Claude to identify edit points.
    
    Args:
        transcript: Transcript object from transcribe module
        options: Dict with analysis options:
            - add_highlights: bool
            - mark_dead_air: bool  
            - find_shorts: bool
        max_retries: Number of retries on API failure
    
    Returns:
        List of EditMarker objects
    """
    from anthropic import Anthropic, APIError, APIConnectionError, RateLimitError
    import time
    
    client = Anthropic()
    
    # Build the analysis prompt
    prompt = build_analysis_prompt(transcript, options)
    
    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse the response
            content = response.content[0].text
            markers = parse_analysis_response(content)
            
            return markers
            
        except RateLimitError as e:
            last_error = e
            wait_time = (attempt + 1) * 30  # 30s, 60s, 90s
            print(f"Rate limited, waiting {wait_time}s before retry...")
            time.sleep(wait_time)
            
        except APIConnectionError as e:
            last_error = e
            wait_time = (attempt + 1) * 5  # 5s, 10s, 15s
            print(f"Connection error, waiting {wait_time}s before retry...")
            time.sleep(wait_time)
            
        except APIError as e:
            last_error = e
            print(f"API error: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            
        except Exception as e:
            last_error = e
            print(f"Unexpected error: {e}")
            break
    
    # All retries failed
    raise RuntimeError(f"Analysis failed after {max_retries} attempts: {last_error}")


def build_analysis_prompt(transcript, options: dict) -> str:
    """Build the prompt for Claude to analyze the transcript."""
    
    timestamped_text = transcript.to_timestamped_text()
    
    tasks = []
    if options.get("add_highlights"):
        tasks.append("- HIGHLIGHT: Key insights, reactions, memorable moments, quotable lines")
    if options.get("mark_dead_air"):
        tasks.append("- DEAD_AIR: Long pauses, filler words (um, uh), off-topic tangents, technical issues")
    if options.get("find_shorts"):
        tasks.append("- SHORT_CLIP: Self-contained 60-90 second segments that work standalone (reactions, tips, stories)")
    
    tasks_text = "\n".join(tasks)
    
    prompt = f"""Analyze this video transcript and identify edit points.

TRANSCRIPT:
{timestamped_text}

IDENTIFY THE FOLLOWING:
{tasks_text}

For each item, provide:
1. Start timestamp (HH:MM:SS.mmm)
2. End timestamp (HH:MM:SS.mmm)
3. Type (HIGHLIGHT, DEAD_AIR, or SHORT_CLIP)
4. Brief label (5-10 words)
5. Optional note

FORMAT YOUR RESPONSE AS JSON:
```json
[
  {{
    "start": "00:01:23.500",
    "end": "00:01:45.200",
    "type": "HIGHLIGHT",
    "label": "Great reaction to feature",
    "note": "Strong emotional response, good thumbnail potential"
  }},
  ...
]
```

Be selective. Only mark genuinely notable moments, not everything.
For DEAD_AIR, only mark segments longer than 3 seconds.
For SHORT_CLIP, ensure the segment is self-contained and engaging.

Return ONLY the JSON array, no other text."""

    return prompt


def parse_analysis_response(response_text: str) -> List[EditMarker]:
    """Parse Claude's response into EditMarker objects."""
    
    # Extract JSON from response
    json_text = response_text.strip()
    
    # Handle markdown code blocks
    if "```json" in json_text:
        json_text = json_text.split("```json")[1].split("```")[0]
    elif "```" in json_text:
        json_text = json_text.split("```")[1].split("```")[0]
    
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"Failed to parse response: {e}")
        print(f"Response was: {response_text[:500]}")
        return []
    
    markers = []
    for item in data:
        try:
            marker_type = MarkerType[item["type"].upper()]
            
            markers.append(EditMarker(
                start_seconds=parse_timestamp(item["start"]),
                end_seconds=parse_timestamp(item["end"]),
                marker_type=marker_type,
                label=item.get("label", ""),
                note=item.get("note", ""),
                confidence=item.get("confidence", 1.0)
            ))
        except (KeyError, ValueError) as e:
            print(f"Skipping invalid marker: {e}")
            continue
    
    return markers


def parse_timestamp(ts: str) -> float:
    """Parse HH:MM:SS.mmm to seconds."""
    parts = ts.replace(",", ".").split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    else:
        return float(parts[0])


def analyze_for_silence(transcript, threshold_seconds: float = 3.0) -> List[EditMarker]:
    """
    Detect silence/gaps in transcript based on segment timing.
    Doesn't require AI - just looks for gaps between segments.
    """
    markers = []
    
    for i in range(len(transcript.segments) - 1):
        current = transcript.segments[i]
        next_seg = transcript.segments[i + 1]
        
        gap = next_seg.start - current.end
        
        if gap >= threshold_seconds:
            markers.append(EditMarker(
                start_seconds=current.end,
                end_seconds=next_seg.start,
                marker_type=MarkerType.DEAD_AIR,
                label=f"Silence ({gap:.1f}s)",
                note="Detected gap in speech",
                confidence=0.9
            ))
    
    return markers


if __name__ == "__main__":
    # Test with sample data
    from transcribe import Transcript, TranscriptSegment
    
    sample = Transcript(
        segments=[
            TranscriptSegment(0.0, 5.0, "Hey everyone, welcome back to the channel."),
            TranscriptSegment(5.5, 15.0, "Today we're going to talk about something really exciting."),
            TranscriptSegment(20.0, 35.0, "So I just discovered this amazing feature and I can't believe it works."),
            TranscriptSegment(35.5, 50.0, "Let me show you exactly how to use it step by step."),
        ],
        language="en",
        duration=50.0
    )
    
    options = {
        "add_highlights": True,
        "mark_dead_air": True,
        "find_shorts": True,
    }
    
    # Test silence detection (no API needed)
    silence_markers = analyze_for_silence(sample)
    print("Silence markers:", silence_markers)
