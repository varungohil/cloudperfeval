FROM docker:29-cli AS docker-cli

FROM node:22-bookworm-slim

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        jq \
        python3 \
        python3-pip \
    && ln -s /usr/bin/python3 /usr/local/bin/python \
    && rm -rf /var/lib/apt/lists/*

COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
RUN pip3 install --break-system-packages --no-cache-dir requests pyyaml \
    && npm install --global @anthropic-ai/claude-code @openai/codex \
    && rm -rf /root/.cache

# The harness chooses a host UID/GID and supplies the only writable mounts
# (/scratch and a private /tmp). No CloudPerfEval tool code is in this image.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/scratch/home
WORKDIR /scratch
