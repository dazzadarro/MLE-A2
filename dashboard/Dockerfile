FROM python:3.11-slim

WORKDIR /app
COPY dashboard/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY dashboard /app/dashboard
COPY model_bank /app/model_bank
RUN mkdir -p /app/datamart

ENV PROJECT_ROOT=/app
ENV PORT=8050
EXPOSE 8050

CMD ["python", "/app/dashboard/server.py"]
