FROM python:3.13-slim
WORKDIR /app
COPY cloud/health_exam/requirements.lock.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY cloud /app/cloud
RUN useradd --create-home appuser && mkdir /app/data && chown appuser /app/data
USER appuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "cloud.health_exam.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
