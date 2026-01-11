FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/root/.cargo/bin:/root/.local/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        libbz2-dev \
        libffi-dev \
        libjpeg-dev \
        liblzma-dev \
        libncurses5-dev \
        libncursesw5-dev \
        libreadline-dev \
        libsqlite3-dev \
        libssl-dev \
        libxml2-dev \
        libxslt1-dev \
        python3 \
        python3-dev \
        python3-venv \
        zlib1g-dev \
        libglib2.0-0 \
        libcairo2 \
        libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN uv venv .venv --python 3.12 --clear
RUN ls .venv/bin
RUN uv pip install -r requirements.txt
RUN ./.venv/bin/buildout
RUN ./bin/instance run /app/scripts/init_plone.py

CMD ["./bin/instance", "fg"]
