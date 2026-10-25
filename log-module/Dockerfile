# syntax=docker/dockerfile:1
FROM eclipse-temurin:21-jdk-jammy AS builder

ARG SBT_VERSION=1.10.7

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL "https://github.com/sbt/sbt/releases/download/v${SBT_VERSION}/sbt-${SBT_VERSION}.tgz" \
        -o /tmp/sbt.tgz \
 && tar -xzf /tmp/sbt.tgz -C /opt \
 && rm /tmp/sbt.tgz
ENV PATH="/opt/sbt/bin:${PATH}"

WORKDIR /build

COPY build.sbt ./
COPY project ./project
RUN sbt -batch update

COPY src ./src
RUN sbt -batch assembly

FROM eclipse-temurin:21-jre-jammy

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        jq \
        python3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin ctf

WORKDIR /home/ctf/log

COPY --from=builder /build/target/scala-2.13/app.jar ./app.jar
COPY ota-agent.sh ./ota-agent.sh
COPY entrypoint.sh ./entrypoint.sh

RUN mkdir -p /home/ctf/log/logs /home/ctf/log/secret \
 && chown -R ctf:ctf /home/ctf/log \
 && chmod +x ota-agent.sh entrypoint.sh

USER ctf

ENV LOG_ROOT=/home/ctf/log/logs
ENV LOG_SECRET=/home/ctf/log/secret/flag.txt

ENV OTA_SERVER=http://ota:8090
ENV OTA_MODULE=log
ENV OTA_INSTALL_DIR=/home/ctf/log
ENV OTA_POLL_INTERVAL=5

EXPOSE 8080

ENTRYPOINT ["./entrypoint.sh"]
CMD ["java", "-jar", "app.jar"]
