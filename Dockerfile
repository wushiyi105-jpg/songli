FROM python:3.10-slim

LABEL org.opencontainers.image.source="https://github.com/wushiyi105-jpg/songli"
LABEL org.opencontainers.image.description="送礼 · songli:按关系、场合、预算与禁忌出三套方案,预算拆分与禁忌本地算"
LABEL org.opencontainers.image.licenses="MIT"

WORKDIR /app

COPY . .

RUN pip install -e .

EXPOSE 8000

CMD ["python", "-m", "songli", "web", "--host", "0.0.0.0"]
