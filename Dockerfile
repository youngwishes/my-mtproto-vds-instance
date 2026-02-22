# Dockerfile
FROM python:3.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы с зависимостями
COPY requirements.txt .
# Устанавливаем зависимости через uv
RUN pip install -r requirements.txt

# Копируем исходный код
COPY src/ ./src/
COPY telemt.toml ./

# Открываем порт
EXPOSE 8000

# Запускаем приложение через uv
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]