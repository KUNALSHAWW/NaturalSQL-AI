#!/usr/bin/env python3
"""
Setup script for AI SQL Chat Assistant
Automates the installation and configuration process
"""

import subprocess
import sys
import os
from pathlib import Path

def print_header(text):
    """Print formatted header"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60 + "\n")

def check_python_version():
    """Verify Python version is 3.8 or higher"""
    print_header("Checking Python Version")
    version = sys.version_info
    print(f"Python {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Error: Python 3.8 or higher is required!")
        sys.exit(1)
    print("✅ Python version is compatible!")

def install_requirements():
    """Install required packages"""
    print_header("Installing Requirements")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ All requirements installed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing requirements: {e}")
        sys.exit(1)

def setup_sample_database():
    """Create sample SQLite database"""
    print_header("Setting Up Sample Database")
    try:
        if Path("student.db").exists():
            response = input("student.db already exists. Recreate? (y/N): ")
            if response.lower() != 'y':
                print("⏭️  Skipping database creation")
                return
            os.remove("student.db")
        
        subprocess.check_call([sys.executable, "sqlite.py"])
        print("✅ Sample database created successfully!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error creating database: {e}")
    except FileNotFoundError:
        print("⚠️  sqlite.py not found. Skipping sample database creation.")

def create_env_template():
    """Create .env.example template"""
    print_header("Creating Environment Template")
    env_content = """# AI SQL Chat Assistant - Environment Variables
# Copy this file to .env and fill in your actual values

# Groq API Key (Get it from: https://console.groq.com/)
GROQ_API_KEY=your_groq_api_key_here

# MySQL Configuration (Optional)
MYSQL_HOST=localhost
MYSQL_USER=your_username
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=your_database

# Application Settings
DEFAULT_MODEL=Llama3-8b-8192
DEFAULT_TEMPERATURE=0.1
MAX_ITERATIONS=15
"""
    
    with open(".env.example", "w") as f:
        f.write(env_content)
    print("✅ Created .env.example template")

def print_next_steps():
    """Print instructions for next steps"""
    print_header("Setup Complete! 🎉")
    print("Next steps:")
    print("\n1. Get your Groq API key from: https://console.groq.com/")
    print("2. (Optional) Copy .env.example to .env and add your API key")
    print("3. Run the application:")
    print("   streamlit run app.py")
    print("\n4. Open your browser to: http://localhost:8501")
    print("\nFor more information, check README.md")
    print("\n" + "="*60 + "\n")

def main():
    """Main setup process"""
    print("\n🚀 AI SQL Chat Assistant - Setup Wizard")
    
    try:
        check_python_version()
        install_requirements()
        setup_sample_database()
        create_env_template()
        print_next_steps()
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
