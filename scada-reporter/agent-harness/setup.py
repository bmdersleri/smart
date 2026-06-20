from setuptools import setup

setup(
    name="scada-reporter-cli",
    version="1.0.0",
    description="EKONT SMART REPORT Agent CLI — coding agent'lar için REST API wrapper",
    long_description="EKONT SMART REPORT sistemini coding agent'lar (Claude Code, OpenCode, "
    "GitHub Copilot, Cursor vb.) tarafından kullanılabilir kılan CLI aracı. "
    "Tüm komutlar --json flag'i ile makine-okunabilir çıktı üretir.",
    author="EKONT SMART REPORT Team",
    package_dir={"": "src"},
    packages=[
        "scada_reporter_cli",
        "scada_reporter_cli.commands",
        "scada_reporter_cli.utils",
    ],
    python_requires=">=3.11",
    install_requires=[
        "click>=8.1",
        "httpx>=0.27",
        "tabulate>=0.10",
        "scada-core",
    ],
    entry_points={
        "console_scripts": [
            "scada-reporter=scada_reporter_cli.cli:main",
            "scada=scada_reporter_cli.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Manufacturing",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Monitoring",
        "Topic :: Scientific/Engineering :: Interface Engine/Protocol Translator",
    ],
)
