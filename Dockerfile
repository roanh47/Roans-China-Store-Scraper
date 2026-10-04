# Playwright-image met Chromium erin: dat is de enige echte afhankelijkheid.
# Versie gelijk aan requirements.txt (playwright==1.52.0) zodat de browser in de
# image en de Python-bibliotheek bij elkaar passen.
FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN mkdir -p /data/image-cache /secrets

EXPOSE 8304

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8304/healthz', timeout=4).status==200 else 1)"

CMD ["python", "-m", "app.main"]
