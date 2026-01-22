"""
Smart Investment Strategy - 驗證環境設定
Verify environment setup for Claude, Aider, and Python
"""

import sys
import os
from dotenv import load_dotenv

def check_environment():
    """Check if the environment is properly configured"""
    
    print("=" * 60)
    print("Smart Investment Strategy - Environment Check")
    print("=" * 60)
    print()
    
    # Check Python version
    python_version = sys.version.split()[0]
    print(f"✓ Python Version: {python_version}")
    
    # Check if .env exists
    env_file_exists = os.path.exists('.env')
    if env_file_exists:
        print("✓ .env file found")
        load_dotenv()
    else:
        print("⚠ .env file not found (using .env.example as template)")
        print("  Run: cp .env.example .env")
    
    # Check for essential packages
    try:
        import pandas as pd
        print(f"✓ Pandas {pd.__version__} installed")
    except ImportError:
        print("✗ Pandas not installed")
    
    try:
        import numpy as np
        print(f"✓ NumPy {np.__version__} installed")
    except ImportError:
        print("✗ NumPy not installed")
    
    try:
        import matplotlib
        print(f"✓ Matplotlib {matplotlib.__version__} installed")
    except ImportError:
        print("✗ Matplotlib not installed")
    
    try:
        import seaborn as sns
        print(f"✓ Seaborn {sns.__version__} installed")
    except ImportError:
        print("✗ Seaborn not installed")
    
    # Check API keys
    print()
    print("API Key Status:")
    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    if anthropic_key and anthropic_key != 'your_anthropic_api_key_here':
        print(f"✓ ANTHROPIC_API_KEY configured (length: {len(anthropic_key)})")
    else:
        print("⚠ ANTHROPIC_API_KEY not configured")
    
    openai_key = os.getenv('OPENAI_API_KEY')
    if openai_key and openai_key != 'your_openai_api_key_here':
        print(f"✓ OPENAI_API_KEY configured (length: {len(openai_key)})")
    else:
        print("⚠ OPENAI_API_KEY not configured (optional for Aider)")
    
    print()
    print("=" * 60)
    print("Environment check complete!")
    print("=" * 60)

if __name__ == "__main__":
    check_environment()
