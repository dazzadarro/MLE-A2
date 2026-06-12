FROM python:3.11-slim

WORKDIR /app
COPY dashboard/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY dashboard /app/dashboard
COPY datamart /app/datamart
COPY model_bank /app/model_bank

ENV PROJECT_ROOT=/app
ENV PORT=8050
EXPOSE 8050

CMD ["python", "/app/dashboard/server.py"]
