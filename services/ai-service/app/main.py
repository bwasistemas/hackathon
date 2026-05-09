"""ASGI entrypoint for uvicorn: ``uvicorn app.main:app``."""
import logging

# Silence noisy OpenTelemetry detach warnings from the underlying async stack.
logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)

from app.bootstrap import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8003, reload=False)
