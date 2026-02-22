# Dockerfile
FROM python:3.13-slim

# Устанавливаем uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы с зависимостями
COPY pyproject.toml uv.lock ./
# Устанавливаем зависимости через uv
RUN uv sync --frozen --no-dev

# Копируем исходный код
COPY src/ ./src/
COPY telemt.toml ./

# Открываем порт
EXPOSE 8000

# Запускаем приложение через uv
CMD ["uv", "run", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]