FROM php:8.3-cli

WORKDIR /app
COPY index.php .

ARG FLAG="SAINTCON{local_reactor_flag}"
RUN printf '%s\n\n>> A.L.I.E.N. Reactor Core — local test flag.\n' "$FLAG" > /flag.txt \
    && chmod 644 /flag.txt

RUN useradd --create-home engineer
USER engineer

EXPOSE 8080
CMD ["php", "-S", "0.0.0.0:8080", "-t", "/app"]
