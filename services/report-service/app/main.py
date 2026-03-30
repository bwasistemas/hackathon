"""ASGI entrypoint for uvicorn: ``uvicorn app.main:app``."""
from app.bootstrap import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8004, reload=False)
