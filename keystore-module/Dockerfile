# syntax=docker/dockerfile:1

FROM golang:1.22-bookworm AS builder

WORKDIR /build
COPY go.mod go.sum ./
COPY vendor/ ./vendor/
COPY *.go ./
RUN go build -mod=vendor -o /build/kvs .

FROM debian:bookworm-slim

RUN useradd --create-home --shell /usr/sbin/nologin ctf

WORKDIR /home/ctf/kvs

COPY --from=builder /build/kvs ./kvs

RUN mkdir -p /home/ctf/kvs/data && chown -R ctf:ctf /home/ctf/kvs

USER ctf

ENV KVS_DIR=/home/ctf/kvs/data
ENV KVS_DBFILENAME=dump.kvs

EXPOSE 6379

CMD ["./kvs"]
