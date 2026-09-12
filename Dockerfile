FROM python:3.8-slim
WORKDIR /app
COPY app/gateway.py /app/gateway.py
ENV PYTHONUNBUFFERED=1 BDG_PORT=6789
EXPOSE 6789
USER 65534:65534
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6789/healthz',timeout=3)"
ENTRYPOINT ["python3", "/app/gateway.py"]
