#!/bin/bash
export ARK_MODEL_ID="deepseek-v4-1-flash-260910"
export ARK_API_KEY=$(./venv/bin/python -c "from key_manager import get_key; print(get_key('ark'))")
nohup ./venv/bin/python app.py > app.log 2>&1 &

#chmod +x start.sh
#./start.sh