# syntax=docker/dockerfile:1

FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin ctf

WORKDIR /home/ctf/mta

COPY package.json ./
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY entrypoint.sh ./entrypoint.sh

RUN mkdir -p /home/ctf/mta/queue/new /home/ctf/mta/queue/cur /home/ctf/mta/queue/tmp \
             /home/ctf/mta/data /home/ctf/mta/certs /home/ctf/mta/secret \
    && chmod +x /home/ctf/mta/scripts/*.sh /home/ctf/mta/entrypoint.sh \
    && openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
         -keyout /home/ctf/mta/certs/dev-key.pem \
         -out /home/ctf/mta/certs/dev-cert.pem \
         -subj "/CN=mta.local" \
    && chown -R ctf:ctf /home/ctf/mta

USER ctf

ENV MTA_QUEUE_DIR=/home/ctf/mta/queue
ENV MTA_DOMAIN=mta.local
ENV MTA_SECRET=/home/ctf/mta/secret/flag.txt

EXPOSE 2525 8081

ENTRYPOINT ["./entrypoint.sh"]
CMD ["node", "src/server.js"]
