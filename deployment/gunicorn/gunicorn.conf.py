# Draft production config. Run: gunicorn config.wsgi -c deployment/gunicorn/gunicorn.conf.py
bind = "127.0.0.1:8000"
workers = 4
timeout = 60
accesslog = "-"
