@echo off
echo Installing dependencies...
pip install -r requirements_pos.txt

echo Starting POS App...
streamlit run pos_app.py --server.port 8501 --server.address 0.0.0.0
pause
