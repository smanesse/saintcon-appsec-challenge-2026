# --- build the Spring Boot origin ---
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /src
COPY origin/pom.xml .
RUN mvn -q -B dependency:go-offline
COPY origin/src ./src
RUN mvn -q -B -DskipTests package

# --- runtime: Varnish edge + JRE origin + crew bot in one ship ---
FROM varnish:7.5
USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openjdk-17-jre-headless python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /src/target/origin.jar /app/origin.jar
COPY varnish/default.vcl /etc/varnish/default.vcl
COPY crew-bot.py /app/crew-bot.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ARG FLAG="SAINTCON{local_docking_flag}"
ENV FLAG=${FLAG}

RUN useradd --create-home pilot
USER pilot

EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
