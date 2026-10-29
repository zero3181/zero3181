# AI debate runner for an always-on box (Synology NAS Container Manager, any Docker host).
# Build context: the meeting-board folder. Works on x86-64 and ARM64.

# Stage 1: install Claude Code with npm. Its postinstall leaves one native executable.
FROM node:22-bookworm-slim AS claude
ARG CLAUDE_CODE_VERSION=2.1.312
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Stage 2: Python runtime + that executable (Node.js is not needed at run time).
FROM python:3.12-slim-bookworm
COPY --from=claude /usr/local/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe /usr/local/bin/claude

WORKDIR /app
COPY board ./board
COPY seats ./seats
COPY tools ./tools
COPY mb.py runner.py quick_test.py ./

# Run as a non-root user. /data holds the board database and debate results.
RUN useradd --create-home app && mkdir -p /data && chown app:app /data
USER app
ENV MB_DATA=/data PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8790
CMD ["python", "runner.py", "--port", "8790"]
