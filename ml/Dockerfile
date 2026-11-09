FROM python:3.12-slim

# libgomp : requis par XGBoost
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/ml
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    FORMS_DIR=/app/shared/forms MODELS_DIR=/app/ml/models

COPY ml/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ml/cancerscan_ml ./cancerscan_ml
COPY shared/ /app/shared/

EXPOSE 8001
CMD ["uvicorn", "cancerscan_ml.engine:app", "--host", "0.0.0.0", "--port", "8001"]
