# =====================================================
# 文件名：app.py
# 作用：Flask 主程序入口
# 调试：开发时设置环境变量 FLASK_DEBUG=1（勿在生产环境开启）
# 启动：cd 项目目录后
#   nohup ./venv/bin/python app.py > logs/flask.log 2>&1 &
# 端口：默认 5524，可用环境变量 FLASK_RUN_PORT 覆盖
# =====================================================

import os
from flask import Flask
from config import Config

app = Flask(__name__)
app.config.from_object(Config)


@app.context_processor
def _inject_server_date():
    try:
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo('Asia/Shanghai')
        except ImportError:
            import pytz
            tz = pytz.timezone('Asia/Shanghai')
        now = datetime.now(tz)
        return {
            'server_date_zh': f'{now.strftime("%B")} {now.day}, {now.year}',
            'server_datetime_iso': now.isoformat(),
        }
    except Exception:
        return {'server_date_zh': '', 'server_datetime_iso': ''}


# --------------------------------------------------
# 自定义 Jinja2 Filter
# --------------------------------------------------
import os as _os

@app.template_filter('basename')
def _basename_filter(path):
    return _os.path.basename(path)


# --------------------------------------------------
# 注册蓝图
# --------------------------------------------------
from routes.main import main_bp
app.register_blueprint(main_bp)

from routes.chat import chat_bp
app.register_blueprint(chat_bp)


# --------------------------------------------------
# 启动程序
# --------------------------------------------------
if __name__ == '__main__':
    # 无论从哪个目录执行，都切到 app.py 所在项目根目录
    _root = os.path.dirname(os.path.abspath(__file__))
    os.chdir(_root)

    # 确保 logs 目录存在（nohup 重定向到 logs/flask.log 时需要）
    os.makedirs(os.path.join(_root, 'logs'), exist_ok=True)

    # 环境变量可覆盖：FLASK_DEBUG=1、FLASK_RUN_PORT=5524
    _debug = os.environ.get('FLASK_DEBUG', '').strip().lower() in ('1', 'true', 'yes')
    _port = int(os.environ.get('FLASK_RUN_PORT', '5524'))

    app.run(host='0.0.0.0', port=_port, debug=_debug, threaded=True)