# syntax=docker/dockerfile:1

FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        g++ \
        make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY fmm.cpp Makefile ./
RUN make

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libstdc++6 \
        curl \
        jq \
        python3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin ctf

WORKDIR /home/ctf/fmm

COPY --from=builder /build/fmm ./fmm
COPY credentials.txt ./credentials.txt
COPY ftproot ./ftproot
COPY ota-agent.sh ./ota-agent.sh

RUN chown -R ctf:ctf /home/ctf/fmm && chmod +x ota-agent.sh

USER ctf

EXPOSE 2121

ENV OTA_SERVER=http://ota:8090
ENV OTA_MODULE=fmm
ENV OTA_INSTALL_DIR=/home/ctf/fmm
ENV OTA_POLL_INTERVAL=5

ENTRYPOINT ["./ota-agent.sh"]
CMD ["./fmm"]
