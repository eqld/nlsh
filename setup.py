#!/usr/bin/env python3
"""
Setup script for nlsh.
"""

from setuptools import setup, find_packages
import os

# Get version from package
with open(os.path.join("nlsh", "__init__.py"), "r") as f:
    for line in f:
        if line.startswith("__version__"):
            version = line.split("=")[1].strip().strip('"').strip("'")
            break
    else:
        version = "1.0.1"

# Get long description from README
with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name="neural-shell",
    version=version,
    description="Neural Shell - AI-driven command-line assistant",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="eqld",
    author_email="44535024+eqld@users.noreply.github.com",
    url="https://github.com/eqld/nlsh",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "nlsh=nlsh.cli:main",
            "nlgc=nlsh.git_commit:main",
        ],
    },
    install_requires=[
        "openai>=1.0.0",
        "pyyaml>=5.1",
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Utilities",
    ],
    python_requires=">=3.8",
)
