# syntax=docker/dockerfile:1

FROM golang:1.22-bookworm AS builder

WORKDIR /build
COPY go.mod ./
COPY *.go ./
RUN go build -o /build/ota .

FROM debian:bookworm-slim

RUN useradd --create-home --shell /usr/sbin/nologin ctf

WORKDIR /home/ctf/ota

COPY --from=builder /build/ota ./ota

RUN mkdir -p /home/ctf/ota/data && chown -R ctf:ctf /home/ctf/ota

USER ctf

ENV OTA_DATA_DIR=/home/ctf/ota/data

EXPOSE 8090

CMD ["./ota"]
