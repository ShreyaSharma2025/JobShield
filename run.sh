#!/usr/bin/env bash
cd "$(dirname "$0")"

echo "============================================================"
echo "  JobShield: Multi-Agent Scam Risk Screening System"
echo "============================================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] python3 is not installed or not in PATH!"
    exit 1
fi

# Create virtual environment if missing
if [ ! -d ".venv" ]; then
    echo "[*] Creating isolated virtual environment in .venv..."
    python3 -m venv .venv
fi

# Install dependencies
echo "[*] Checking and installing dependencies..."
.venv/bin/python -m pip install -r requirements.txt --quiet

# Launch Streamlit
echo ""
echo "============================================================"
echo "  Launching JobShield Web App on http://localhost:8501"
echo "============================================================"
echo ""
.venv/bin/streamlit run app.py
