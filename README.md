# Resolve AI Assistant

AI-powered editing assistant for DaVinci Resolve. Analyzes your timeline, adds markers for highlights and cuts, extracts shorts, and generates rough cuts.

## Features

- **Auto-markers**: Transcribes video, identifies highlights and dead air, adds color-coded markers to timeline
- **Shorts extraction**: Finds the best 60-90 second clips for vertical video
- **Preview before apply**: Review and approve/reject markers before they're added
- **Transcript caching**: Re-runs are instant (no re-transcription needed)
- **In-app UI**: Runs directly from Resolve's Scripts menu

## Marker Colors

| Color | Meaning |
|-------|---------|
| 🟢 Green | Highlight - keep this |
| 🔴 Red | Dead air - cut this |
| 🔵 Blue | Potential short clip |

## Requirements

### Software
- **DaVinci Resolve 18+** (Free or Studio)
- **Python 3.10+**
- **ffmpeg** (for audio extraction)

### API Key
- **Anthropic API key** (for AI analysis)

## Installation

### 1. Install ffmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update && sudo apt install ffmpeg
```

**Windows:**
```bash
# Using Chocolatey
choco install ffmpeg

# Or download from https://ffmpeg.org/download.html
# Add to PATH
```

### 2. Clone and install dependencies

```bash
git clone https://github.com/Kilo-Loco/resolve-ai-assistant.git
cd resolve-ai-assistant

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Set up Anthropic API key

Get your API key from [console.anthropic.com](https://console.anthropic.com)

**Option A: Environment variable (recommended)**
```bash
# Add to your shell profile (~/.zshrc, ~/.bashrc, etc.)
export ANTHROPIC_API_KEY="your-api-key-here"
```

**Option B: Create .env file**
```bash
cp .env.example .env
# Edit .env and add your key
```

### 4. Install to DaVinci Resolve

**macOS:**
```bash
./install.sh
```

**Windows (manual):**
```
Copy src/ai_edit_assistant.py to:
%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Edit\AI Edit Assistant.py
```

**Linux (manual):**
```
Copy src/ai_edit_assistant.py to:
~/.local/share/DaVinciResolve/Fusion/Scripts/Edit/AI Edit Assistant.py
```

### 5. Enable external scripting in Resolve

1. Open DaVinci Resolve
2. Go to **Preferences** → **System** → **General**
3. Set **External scripting using** to **Local** (or Network if needed)
4. Restart DaVinci Resolve

## Usage

1. Open DaVinci Resolve
2. Import your video and create a timeline
3. Go to **Workspace → Scripts → Edit → AI Edit Assistant**
4. Select your options:
   - Whisper model (tiny=fast, large=accurate)
   - What to find (highlights, dead air, shorts)
5. Click **Analyze**
6. Review markers in the preview window
7. Click **Apply Selected**

## CLI Usage

You can also use the command-line interface:

```bash
# Activate virtual environment
source venv/bin/activate

# Transcribe a video
python src/cli.py transcribe video.mp4 --model base

# Analyze and generate markers
python src/cli.py analyze -v video.mp4 -o markers.json

# Apply markers to Resolve (Resolve must be open)
python src/cli.py apply markers.json
```

## Troubleshooting

### "No module named 'anthropic'"
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### "ANTHROPIC_API_KEY not set"
```bash
export ANTHROPIC_API_KEY="your-key-here"
```

### Script not appearing in Resolve
- Make sure you ran `./install.sh` (macOS) or copied the file manually
- Restart DaVinci Resolve completely
- Check that external scripting is enabled in Preferences

### First run is slow
- Whisper downloads the model on first use (~150MB for "base")
- Subsequent runs use the cached model
- Use "tiny" model for faster (less accurate) transcription

### ffmpeg errors
```bash
# Verify ffmpeg is installed
ffmpeg -version

# If not found, install it (see Installation section)
```

## Known Limitations

- **"Generate rough cut"** is not yet implemented (button is disabled)
- **"Create shorts timeline"** identifies clips but requires manual extraction
- Cache invalidation is based on clip count (reordering clips won't trigger re-transcription)

## License

MIT
