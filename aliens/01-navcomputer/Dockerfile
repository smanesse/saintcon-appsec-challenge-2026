FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ARG FLAG="SAINTCON{local_navcomputer_flag}"
RUN printf '%s\n\n>> A.L.I.E.N. Navcomputer — local test flag.\n' "$FLAG" > /flag.txt \
    && chmod 644 /flag.txt

RUN useradd --create-home pilot
USER pilot

EXPOSE 8080
CMD ["python", "app.py"]
