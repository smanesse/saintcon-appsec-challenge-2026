FROM node:20-slim

WORKDIR /app
COPY server.js .

RUN mkdir -p manifests \
    && printf 'BAY 1 CARGO\n- 400t deuterium\n- 12 stasis pods\n' > manifests/bay-1.txt \
    && printf 'BAY 2 CARGO\n- xeno-botanicals\n- 3 escape shuttles\n' > manifests/bay-2.txt \
    && printf 'QUARANTINE HOLD\n- specimen 7 (DO NOT OPEN)\n' > manifests/quarantine.txt

ARG FLAG="SAINTCON{local_cargo_flag}"
RUN printf '%s\n\n>> A.L.I.E.N. Cargo Manifests — local test flag.\n' "$FLAG" > /flag.txt \
    && chmod 644 /flag.txt

RUN useradd --create-home crew
USER crew

EXPOSE 8080
CMD ["node", "server.js"]
