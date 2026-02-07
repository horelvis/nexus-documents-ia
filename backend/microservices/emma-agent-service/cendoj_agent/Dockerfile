# CENDOJ Reference Agent — Ephemeral Browser Container
#
# Usage:
#   docker build -t nouxcube-cendoj-agent .
#   docker run --rm nouxcube-cendoj-agent \
#     --query "despido improcedente" --court TS --max-results 10
#
# Output: JSON array of sentence references to stdout
# Logs: stderr
# Container is removed after each run (--rm)

FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /agent

COPY agent.py .

# Install playwright browsers (Chromium only — lighter image)
# httpx: direct PDF downloads (no browser needed for contenidos.action)
# PyPDF2: in-memory text extraction from sentence PDFs
RUN pip install --no-cache-dir playwright==1.49.0 httpx PyPDF2 && \
    playwright install chromium --with-deps

ENTRYPOINT ["python", "agent.py"]
