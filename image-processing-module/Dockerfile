# syntax=docker/dockerfile:1
FROM debian:bookworm-slim AS imagemagick-builder

ARG IM_VERSION=7.1.0-48

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    curl \
    pkg-config \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    libtiff-dev \
    libltdl-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp

RUN curl -fsSL \
    https://github.com/ImageMagick/ImageMagick/archive/refs/tags/${IM_VERSION}.tar.gz \
    -o imagemagick.tar.gz \
 && tar -xzf imagemagick.tar.gz

WORKDIR /tmp/ImageMagick-${IM_VERSION}

RUN ./configure \
      --prefix=/opt/imagemagick \
      --disable-static \
      --disable-hdri \
      --with-quantum-depth=8 \
      --with-modules \
      --without-perl \
      --without-x \
 && make -j"$(nproc)" \
 && make install

RUN /opt/imagemagick/bin/identify -version

FROM maven:3-eclipse-temurin-21 AS app-builder

WORKDIR /build
COPY pom.xml ./
RUN mvn -q -DskipTests dependency:go-offline
COPY src ./src
RUN mvn -q -DskipTests package

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        libpng16-16 \
        libwebp7 \
        libwebpdemux2 \
        libtiff6 \
        libltdl7 \
        libgomp1 \
        zlib1g \
        ghostscript \
        inkscape \
        curl \
        jq \
        python3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin ctf

COPY --from=eclipse-temurin:21-jre /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="/opt/java/openjdk/bin:${PATH}"

COPY --from=imagemagick-builder /opt/imagemagick /opt/imagemagick

ENV LD_LIBRARY_PATH=/opt/imagemagick/lib
RUN echo "/opt/imagemagick/lib" > /etc/ld.so.conf.d/imagemagick.conf && ldconfig

RUN /opt/imagemagick/bin/magick -version

WORKDIR /home/ctf/ipm
COPY --from=app-builder /build/target/app.jar ./app.jar
COPY ota-agent.sh ./ota-agent.sh
COPY entrypoint.sh ./entrypoint.sh

RUN mkdir -p /home/ctf/ipm/secret \
 && chown -R ctf:ctf /home/ctf/ipm \
 && chmod +x ota-agent.sh entrypoint.sh

USER ctf

EXPOSE 8080

ENV OTA_SERVER=http://ota:8090
ENV OTA_MODULE=ipm
ENV OTA_INSTALL_DIR=/home/ctf/ipm
ENV OTA_POLL_INTERVAL=5

ENV IPM_SECRET=/home/ctf/ipm/secret/flag.txt

ENV JAVA_TOOL_OPTIONS="-Djdk.xml.entityExpansionLimit=0 -Djdk.xml.totalEntitySizeLimit=0 -XX:+ExitOnOutOfMemoryError"

ENTRYPOINT ["./entrypoint.sh"]
CMD ["java", "-jar", "app.jar"]