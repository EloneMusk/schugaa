#!/bin/bash

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 could not be found."
    echo "If a dialog appeared asking to install 'Command Line Developer Tools', please click Install."
    echo "Once installed, run this script again."
    exit 1
fi

# Check if python3 actually works (handles the xcode-select shim issue)
if ! python3 --version &> /dev/null; then
    echo "Error: Python 3 command exists but is not responding."
    echo "This usually means the 'Command Line Developer Tools' are missing or installing."
    echo "Please complete the installation popup and try again."
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "Failed to create virtual environment."
        exit 1
    fi
fi

source venv/bin/activate

echo "Checking requirements..."
if ! python -c "import rumps" &> /dev/null; then
    echo "Installing requirements..."
    pip install -r requirements.txt
fi

echo "Starting Schugaa..."
python -u main.py
