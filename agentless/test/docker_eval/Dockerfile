# agentless/test/docker_eval/Dockerfile
FROM python:3.12-slim

# System deps
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    git patch dos2unix ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy entrypoint
COPY entrypoint.sh /workspace/entrypoint.sh
RUN chmod +x /workspace/entrypoint.sh

# Default entrypoint
ENTRYPOINT ["/workspace/entrypoint.sh"]
