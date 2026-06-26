from setuptools import setup, find_packages

setup(
    name="pixel-assistant",
    version="1.0.0",
    description="Autonomous AI Assistant with agents, web UI, and self-improvement",
    author="Pixel Assistant Team",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=[
        "rich>=13.0",
        "requests>=2.28",
        "pyyaml>=6.0",
        "groq>=0.12",
        "fastapi>=0.100",
        "uvicorn>=0.23",
        "pydantic>=2.0",
    ],
    extras_require={
        "voice": ["speechrecognition", "pyttsx3", "pyaudio"],
        "images": ["diffusers", "torch", "transformers"],
        "calendar": ["google-api-python-client", "google-auth-httplib2", "google-auth-oauthlib"],
        "all": ["speechrecognition", "pyttsx3", "pyaudio", "diffusers", "torch",
                "transformers", "google-api-python-client", "google-auth-httplib2",
                "google-auth-oauthlib", "pyperclip", "qrcode[pil]", "pyfiglet"],
    },
    entry_points={
        "console_scripts": [
            "pixel=run:main",
        ],
    },
    python_requires=">=3.10",
)
