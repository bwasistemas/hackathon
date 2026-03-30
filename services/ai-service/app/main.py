"""ASGI entrypoint for uvicorn: ``uvicorn app.main:app``."""
import logging

# Strands Swarm can log spurious OpenTelemetry detach errors (context token from another
# asyncio context). Upstream: https://github.com/strands-agents/sdk-python/issues/1316
logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)

from app.bootstrap import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8003, reload=False)
