#!/bin/bash

# Install Resolve AI Assistant to DaVinci Resolve Scripts folder

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect platform
case "$(uname -s)" in
    Darwin)
        RESOLVE_SCRIPTS_DIR="$HOME/Library/Application Support/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Edit"
        ;;
    Linux)
        RESOLVE_SCRIPTS_DIR="$HOME/.local/share/DaVinciResolve/Fusion/Scripts/Edit"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        echo "⚠️  Windows detected. Please install manually:"
        echo ""
        echo "Copy this file:"
        echo "  $SCRIPT_DIR/src/ai_edit_assistant.py"
        echo ""
        echo "To this location:"
        echo "  %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Edit\\AI Edit Assistant.py"
        echo ""
        echo "Then restart DaVinci Resolve."
        exit 0
        ;;
    *)
        echo "❌ Unsupported platform: $(uname -s)"
        echo ""
        echo "Please install manually by copying:"
        echo "  $SCRIPT_DIR/src/ai_edit_assistant.py"
        echo ""
        echo "To your DaVinci Resolve Scripts/Edit folder."
        exit 1
        ;;
esac

# Create directory if it doesn't exist
mkdir -p "$RESOLVE_SCRIPTS_DIR"

# Create symlink to our script
ln -sf "$SCRIPT_DIR/src/ai_edit_assistant.py" "$RESOLVE_SCRIPTS_DIR/AI Edit Assistant.py"

echo "✅ Installed AI Edit Assistant to DaVinci Resolve"
echo ""
echo "📍 Location: $RESOLVE_SCRIPTS_DIR"
echo ""
echo "Next steps:"
echo "  1. Restart DaVinci Resolve"
echo "  2. Enable external scripting: Preferences → System → General"
echo "  3. Find it under: Workspace → Scripts → Edit → AI Edit Assistant"
echo ""
echo "Make sure you have set your API key:"
echo "  export ANTHROPIC_API_KEY=\"your-key-here\""
