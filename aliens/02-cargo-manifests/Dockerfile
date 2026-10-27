FROM node:20-slim

WORKDIR /app
COPY server.js .

RUN mkdir -p manifests \
    && printf 'BAY 1 CARGO\n- 400t deuterium\n- 12 stasis pods\n' > manifests/bay-1.txt \
    && printf 'BAY 2 CARGO\n- xeno-botanicals\n- 3 escape shuttles\n' > manifests/bay-2.txt \
    && printf 'QUARANTINE HOLD\n- specimen 7 (DO NOT OPEN)\n' > manifests/quarantine.txt

<<<<<<<< HEAD:aliens/02-cargo-manifests/Dockerfile
ARG FLAG="SAINTCON{local_cargo_flag}"
RUN printf '%s\n\n>> A.L.I.E.N. Cargo Manifests — local test flag.\n' "$FLAG" > /flag.txt \
========
ARG ENTRY_CODE="SAINTCON{th3_m0th3rsh1p_h4s_b33n_b04rd3d}"
ENV ENTRY_CODE=${ENTRY_CODE}

ARG FLAG="SAINTCON{gh0st_dr1ft_1n_th3_c4rg0_h0ld}"
RUN printf '%s\n\n>> NAV LOG: The REACTOR CORE ship idles at port 8093.\n>> Her engineering console rejects unknown crew. Board with THIS access code.\n' "$FLAG" > /flag.txt \
>>>>>>>> eb86a9a (more cleaning):aliens/02-cargo-manifest/Dockerfile
    && chmod 644 /flag.txt

RUN useradd --create-home crew
USER crew

EXPOSE 8080
CMD ["node", "server.js"]
