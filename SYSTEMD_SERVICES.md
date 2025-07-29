# Systemd Service Files for Production Deployment

## 1. Celery Workers Service
Create: `/etc/systemd/system/doctolib-celery.service`

```ini
[Unit]
Description=Doctolib Celery Workers
After=network.target redis.service

[Service]
Type=forking
User=your-username
Group=your-username
WorkingDirectory=/path/to/doctolib_bot
Environment=PATH=/path/to/venv/bin
ExecStart=/path/to/venv/bin/celery -A celery_tasks worker --loglevel=info --concurrency=4 --detach --pidfile=/var/run/celery/worker.pid --logfile=/var/log/celery/worker.log
ExecStop=/bin/kill -TERM $MAINPID
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 2. Telegram Bot Service
Create: `/etc/systemd/system/doctolib-bot.service`

```ini
[Unit]
Description=Doctolib Telegram Bot
After=network.target doctolib-celery.service

[Service]
Type=simple
User=your-username
Group=your-username
WorkingDirectory=/path/to/doctolib_bot
Environment=PATH=/path/to/venv/bin
ExecStart=/path/to/venv/bin/python telegram_bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## 3. Setup Commands

```bash
# Create log directories
sudo mkdir -p /var/log/celery /var/run/celery
sudo chown your-username:your-username /var/log/celery /var/run/celery

# Install service files
sudo cp doctolib-celery.service /etc/systemd/system/
sudo cp doctolib-bot.service /etc/systemd/system/

# Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable doctolib-celery
sudo systemctl enable doctolib-bot

# Start services
sudo systemctl start doctolib-celery
sudo systemctl start doctolib-bot

# Check status
sudo systemctl status doctolib-celery
sudo systemctl status doctolib-bot

# View logs
sudo journalctl -u doctolib-celery -f
sudo journalctl -u doctolib-bot -f
```

## 4. Management Commands

```bash
# Restart services
sudo systemctl restart doctolib-celery
sudo systemctl restart doctolib-bot

# Stop services
sudo systemctl stop doctolib-celery
sudo systemctl stop doctolib-bot

# Disable services
sudo systemctl disable doctolib-celery
sudo systemctl disable doctolib-bot
```
