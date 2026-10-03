# Draft image (gunicorn gets added to production deps in Phase 27)
FROM python:3.13-slim
WORKDIR /app
COPY backend/ /app/
RUN pip install --no-cache-dir . gunicorn
CMD ["gunicorn", "config.wsgi", "-b", "0.0.0.0:8000"]
