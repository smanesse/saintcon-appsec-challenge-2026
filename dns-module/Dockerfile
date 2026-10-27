# syntax=docker/dockerfile:1

FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        make \
        libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY dnsm.c Makefile ./
RUN make

FROM debian:bookworm-slim

RUN useradd --create-home --shell /usr/sbin/nologin ctf

WORKDIR /home/ctf/dnsm

COPY --from=builder /build/dnsm ./dnsm
COPY zones ./zones
COPY entrypoint.sh ./entrypoint.sh

RUN mkdir -p /home/ctf/dnsm/secret \
 && chown -R ctf:ctf /home/ctf/dnsm && chmod +x entrypoint.sh dnsm

USER ctf

EXPOSE 8053/udp
EXPOSE 8053/tcp
EXPOSE 8080/tcp

ENV DNSM_PORT=8053
ENV DNSM_ADMIN_PORT=8080
ENV DNSM_FORWARD_PORT=8054
ENV DNSM_ZONE_FILE=./zones/example.zone
ENV DNSM_ZONE_DIR=./zones

ENTRYPOINT ["./entrypoint.sh"]
