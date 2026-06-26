"""Quick-search CLI entry point (for global hotkey binding)."""
import sys
from pathlib import Path

SRC = Path(__file__).parent.parent
sys.path.insert(0, str(SRC))

def quick_query(query: str) -> str:
    """Run a quick query against Pixel Assistant.
    Used by the global hotkey quick-search feature."""
    from skills import load_skills
    load_skills()
    
    from main import PixelAssistant
    from core_files.config import Config
    
    config = Config()
    assistant = PixelAssistant(provider=config.provider)
    
    result = assistant.handle_prompt(query)
    
    assistant._printed = False
    
    return result or "(no response)"

if __name__ == "__main__":
    from core_files.tray_enhanced import show_quick_search
    show_quick_search()
