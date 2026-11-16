FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium \
    && useradd --create-home renderer
COPY cardnews ./cardnews
RUN python -c "from cardnews.design import ensure_fonts; ensure_fonts()"
USER renderer
CMD ["sh", "-c", "test -n \"$CARDNEWS_INTERNAL_API_KEY\" && test -n \"$SUPABASE_URL\" && exec uvicorn cardnews.api:app --host :: --port ${PORT:-8000}"]
