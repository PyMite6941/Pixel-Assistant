"""First-run setup wizard for Pixel Assistant."""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

def main():
    print("=" * 50)
    print("  Pixel Assistant — First Run Setup")
    print("=" * 50)
    print()
    
    if ENV_FILE.exists():
        resp = input(".env file exists. Overwrite? (y/N): ").strip().lower()
        if resp != "y":
            print("Setup cancelled.")
            return
    
    env_vars = {}
    
    print("\n1. AI Provider (choose one):")
    print("   You need at least one API key. Groq is free and fastest.")
    print()
    
    groq_key = input("   Groq API Key (leave blank to skip): ").strip()
    if groq_key:
        env_vars["GROQ_KEY"] = groq_key
    
    gemini_key = input("   Gemini API Key (leave blank to skip): ").strip()
    if gemini_key:
        env_vars["GEMINI_KEY"] = gemini_key
    
    mistral_key = input("   Mistral API Key (leave blank to skip): ").strip()
    if mistral_key:
        env_vars["MISTRAL_KEY"] = mistral_key
    
    print("\n2. Self-hosted LLM (optional):")
    ollama_url = input("   Ollama URL [http://localhost:11434]: ").strip()
    if ollama_url:
        env_vars["OLLAMA_URL"] = ollama_url
    
    openai_key = input("   OpenAI Key (leave blank to skip): ").strip()
    if openai_key:
        env_vars["OPENAI_KEY"] = openai_key
        openai_base = input("   OpenAI Base URL [https://api.openai.com/v1]: ").strip()
        if openai_base:
            env_vars["OPENAI_BASE_URL"] = openai_base
    
    print("\n3. Preferences:")
    default_provider = "groq" if groq_key else ("gemini" if gemini_key else ("ollama" if ollama_url else ""))
    if default_provider:
        provider = input(f"   Default provider [{default_provider}]: ").strip()
        env_vars["PROVIDER"] = provider or default_provider
    
    # Write .env
    ENV_FILE.write_text(
        "\n".join(f"{k}={v}" for k, v in env_vars.items()) + "\n",
        encoding="utf-8"
    )
    
    print(f"\n✅ .env file created at {ENV_FILE}")
    print("Run 'python src/run.py' to start!")
    print("Or 'uvicorn src.api.app:app' for the web UI.")

if __name__ == "__main__":
    main()
