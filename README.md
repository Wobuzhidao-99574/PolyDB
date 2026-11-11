# PolyDB Flask 版本

从 Streamlit 迁移至 Flask 的 PolyDB 数据库网站。

---

## 目录结构

```
polydb_flask/
├── app.py                  # Flask 主入口
├── config.py               # 配置（数据库连接串等）
├── requirements.txt
├── routes/
│   └── main.py             # 所有页面路由
├── services/
│   ├── db_service.py       # 数据库连接（psycopg2）
│   ├── polydb_service.py   # 业务查询（搜索、下载等）
│   └── chemistry_service.py# RDKit 计算（图片、相似度等）
├── templates/
│   ├── base.html           # 公共导航/页脚
│   ├── index.html          # 首页
│   ├── history.html        # History Updates
│   ├── search_advanced.html# 高级搜索
│   ├── search_similarity.html # 相似搜索
│   ├── search_route.html   # 合成路线搜索
│   ├── download.html       # 下载页
│   └── contact.html        # 联系我们
├── static/
│   ├── video/
│   │   └── cartoon.mp4     # ← 把原来的视频放这里
│   └── img/
│       └── routes/         # ← 把 ours_image/*.png 放这里
└── data/
    └── reaction_conditions.md  # ← 把原来的文件放这里
```

---

## 快速启动（本地开发）

```bash
# 1. 创建虚拟环境（推荐 conda，因为 rdkit）
conda create -n polydb python=3.10
conda activate polydb

# 2. 安装 rdkit（conda 比 pip 稳）
conda install -c conda-forge rdkit

# 3. 安装其他依赖
pip install flask gunicorn psycopg2-binary pandas pillow

# 4. 设置环境变量
export DATABASE_URL="postgresql://用户名:YOUR_DB_PASSWORD@127.0.0.1:5432/polydb"
export SECRET_KEY="YOUR_SECRET_KEY"
export FLASK_DEBUG=1

# 5. 启动
python app.py
```

访问 http://localhost:5000

---

## 静态文件迁移

把原 Streamlit 项目的文件按以下对应关系移动：

| 原路径 | 新路径 |
|--------|--------|
| `./Fig/cartoon.mp4` | `static/video/cartoon.mp4` |
| `ours_image/*.png` | `static/img/routes/*.png` |
| `reaction_conditions.md` | `data/reaction_conditions.md` |

---

## 生产部署（Linux 服务器）

### 1. 安装 nginx

```bash
sudo apt install nginx
```

### 2. 启动 gunicorn

```bash
conda activate polydb
gunicorn -w 4 -b 127.0.0.1:5000 app:app
```

### 3. Nginx 配置

创建 `/etc/nginx/sites-available/polydb`：

```nginx
server {
    listen 80;
    server_name your_domain_or_ip;

    location /static/ {
        alias /home/youruser/polydb_flask/static/;
    }

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/polydb /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 4. systemd 守护进程

创建 `/etc/systemd/system/polydb.service`：

```ini
[Unit]
Description=PolyDB Flask App
After=network.target

[Service]
User=youruser
WorkingDirectory=/home/youruser/polydb_flask
Environment="PATH=/home/youruser/miniconda3/envs/polydb/bin"
Environment="DATABASE_URL=postgresql://user:YOUR_DB_PASSWORD@127.0.0.1:5432/polydb"
Environment="SECRET_KEY=YOUR_SECRET_KEY"
ExecStart=/home/youruser/miniconda3/envs/polydb/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable polydb
sudo systemctl start polydb
sudo systemctl status polydb
```

---

## 迁移到腾讯云

1. 购买腾讯云轻量应用服务器（推荐 2核4G，Ubuntu 22.04）
2. 在安全组开放 80 端口（HTTP）
3. 用 XShell + XFTP 把整个 `polydb_flask/` 上传
4. 按上述步骤安装 conda → rdkit → Flask → gunicorn → nginx
5. 迁移 PostgreSQL 数据库：
   ```bash
   # 原服务器导出
   pg_dump -U postgres polydb > polydb_backup.sql
   
   # 新服务器导入
   psql -U postgres -c "CREATE DATABASE polydb;"
   psql -U postgres polydb < polydb_backup.sql
   ```

---

## 注意事项

1. **SQL 注入**：`extra_cond` 字段目前直接拼接 SQL，生产环境上线前需要加白名单解析器
2. **rdkit 安装**：用 conda 安装，pip 在某些 Linux 版本会失败
3. **视频文件**：`cartoon.mp4` 较大时建议用 nginx 直接提供（`location /static/`）
4. **Ketcher 画板**：第一版暂用纯文本 SMILES 输入，后续可嵌入 Ketcher JS 组件
