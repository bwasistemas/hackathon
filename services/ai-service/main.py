"""AI Service - OpenAI/LLM integration for architecture analysis."""
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
from contextlib import asynccontextmanager
import asyncio

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://fiap:fiap@postgres:5432/fiap"
)
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.getenv("RABBITMQ_PORT", "5672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "fiap")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "fiap")

pool = None
rabbit_connection = None

class AnalyzeRequest(BaseModel):
    text: str

class Component(BaseModel):
    name: str
    type: str
    description: str

class Risk(BaseModel):
    severity: str
    description: str
    recommendation: str

class AnalysisResponse(BaseModel):
    components: list[Component]
    risks: list[Risk]
    summary: str

SYSTEM_PROMPT = """You are an expert software architect analyzing architecture diagrams.
Given the extracted text from a diagram, identify:
1. Components/services (databases, APIs, frontends, etc.)
2. Potential architectural risks
3. A brief summary

You MUST return the output strictly as a JSON object matching this exact structure:
{
  "components": [
    {"name": "...", "type": "...", "description": "..."}
  ],
  "risks": [
    {"severity": "...", "description": "...", "recommendation": "..."}
  ],
  "summary": "texto detalhado explicando o diagrama..."
}

Return a structured analysis in Portuguese."""

client: Optional[OpenAI] = None
if OPENAI_API_KEY:
    try:
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    except TypeError:
        client = OpenAI(api_key=OPENAI_API_KEY)

async def process_message(message):
    import json
    from PIL import Image
    import pytesseract
    
    async with message.process():
        data = json.loads(message.body)
        upload_id = data["upload_id"]
        file_path = data.get("file_path", "")
        
        print(f"AI Service processing {upload_id}...")
        
        if pool:
            async with pool.acquire() as conn:
                await conn.execute("UPDATE uploads SET status = 'PROCESSING', updated_at = NOW() WHERE id = $1", upload_id)
        
        try:
            if file_path.lower().endswith('.pdf'):
                from pdf2image import convert_from_path
                images = await asyncio.to_thread(convert_from_path, file_path)
                text_chunks = []
                for img in images:
                    extracted = await asyncio.to_thread(pytesseract.image_to_string, img)
                    if extracted:
                        text_chunks.append(extracted.strip())
                text = "\n".join(text_chunks)
                text = text.strip() if text else "No text found in PDF"
            else:
                img = await asyncio.to_thread(Image.open, file_path)
                extracted_text = await asyncio.to_thread(pytesseract.image_to_string, img)
                text = extracted_text.strip() if extracted_text else "No text found in image"
        except Exception as e:
            text = f"OCR Error: {e}"
            
        req = AnalyzeRequest(text=text)
        try:
            ans = await analyze(req)
            ai_result = ans.model_dump()
        except Exception as e:
            ai_result = {"error": str(e)}
            
        if pool:
            async with pool.acquire() as conn:
                await conn.execute("""
                    UPDATE uploads SET 
                        status = 'DONE',
                        updated_at = NOW(),
                        file_path = $1
                    WHERE id = $2
                """, json.dumps({"text": text, "ai": ai_result}), upload_id)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool, rabbit_connection
    if DATABASE_URL:
        db_url = DATABASE_URL.replace("postgresql+asyncpg://", "")
        user_part, rest = db_url.split("@", 1)
        user = user_part.split(":")[0]
        password = ":".join(user_part.split(":")[1:])
        host_port_db = rest
        host_port, db = host_port_db.rsplit("/", 1)
        host, port = host_port.rsplit(":", 1)
        
        try:
            import asyncpg
            pool = await asyncpg.create_pool(
                host=host, port=int(port),
                user=user, password=password,
                database=db, min_size=2, max_size=10
            )
        except Exception as e:
            print(f"DB Error: {e}")
            pool = None

    try:
        import aio_pika
        rabbit_connection = await aio_pika.connect_robust(
            host=RABBITMQ_HOST, port=RABBITMQ_PORT,
            login=RABBITMQ_USER, password=RABBITMQ_PASSWORD
        )
        channel = await rabbit_connection.channel()
        await channel.set_qos(prefetch_count=1)
        queue = await channel.declare_queue("diagram.upload", durable=True)
        
        async def on_message(msg):
            await process_message(msg)
            
        await queue.consume(on_message)
        print("RabbitMQ Consumer started inside AI Service.")
    except Exception as e:
        print(f"Rabbit Error: {e}")
        rabbit_connection = None

    yield
    
    if pool:
        await pool.close()
    if rabbit_connection:
        await rabbit_connection.close()

from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(
    title="AI Service",
    description="AI-powered architecture analysis",
    version="1.0.0",
    lifespan=lifespan
)

Instrumentator().instrument(app).expose(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




@app.get("/health")
async def health():
    return {"status": "healthy", "service": "ai-service"}


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(request: AnalyzeRequest):
    if not client:
        raise HTTPException(
            status_code=503,
            detail="AI service not configured. Set OPENAI_API_KEY."
        )
    
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this architecture diagram:\n{request.text}"}
            ],
            temperature=0.3,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        import json
        
        try:
            parsed = json.loads(content)
            components = [Component(**c) for c in parsed.get("components", [])]
            risks = [Risk(**r) for r in parsed.get("risks", [])]
            summary = parsed.get("summary", content)
        except json.JSONDecodeError:
            components = []
            risks = []
            summary = "Error parsing AI response: " + content
        
        return AnalysisResponse(
            components=components,
            risks=risks,
            summary=summary
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)