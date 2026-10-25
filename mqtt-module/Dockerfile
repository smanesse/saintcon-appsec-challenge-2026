# syntax=docker/dockerfile:1

FROM python:3.12-slim

RUN useradd --create-home --shell /usr/sbin/nologin ctf

WORKDIR /home/ctf/mqb

COPY mqb/ ./mqb/

RUN mkdir -p /home/ctf/mqb/retained /home/ctf/mqb/secret && chown -R ctf:ctf /home/ctf/mqb

USER ctf

ENV MQB_HOST=0.0.0.0
ENV MQB_PORT=1883
ENV MQB_ADMIN_HOST=0.0.0.0
ENV MQB_ADMIN_PORT=8081
ENV MQB_RETAIN_DIR=/home/ctf/mqb/retained
ENV MQB_FLAG_TOPIC=fleet/control/flag
ENV MQB_FLAG_FILE=/home/ctf/mqb/secret/flag.txt
ENV PYTHONUNBUFFERED=1

EXPOSE 1883 8081

CMD ["python3", "-m", "mqb.server"]
