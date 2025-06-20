# web_ui\api.py

"""MongoDB Assistant Web API"""
import sys
import os
from pathlib import Path
from datetime import datetime
import asyncio
from typing import Dict, Any, Optional

# Proje root'u ekle
sys.path.append(str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import logging

from src.agents.mongodb_agent import MongoDBAgent
from web_ui.config import *

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="MongoDB LangChain Assistant",
    description="LC Waikiki MongoDB Doğal Dil Sorgu Arayüzü",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global agent instance
agent: Optional[MongoDBAgent] = None
agent_lock = asyncio.Lock()

# Request/Response modelleri
class QueryRequest(BaseModel):
    query: str = Field(..., description="MongoDB sorgusu", max_length=MAX_QUERY_LENGTH)
    api_key: str = Field(..., description="API anahtarı")

class QueryResponse(BaseModel):
    durum: str
    işlem: str
    koleksiyon: Optional[str] = None
    açıklama: str
    tahminler: Optional[list] = None
    sonuç: Optional[Dict[str, Any]] = None
    öneriler: Optional[list] = None
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

# Basit API key kontrolü
async def verify_api_key(api_key: str) -> bool:
    """API anahtarını doğrula"""
    return api_key == API_KEY

# Agent başlatma
async def get_agent() -> MongoDBAgent:
    """Singleton agent instance"""
    global agent
    async with agent_lock:
        if agent is None:
            logger.info("MongoDB Agent başlatılıyor...")
            agent = MongoDBAgent()
            if not agent.initialize():
                raise HTTPException(status_code=500, detail="Agent başlatılamadı")
            logger.info("Agent başarıyla başlatıldı")
        return agent

# Static dosyaları servis et
app.mount("/static", StaticFiles(directory="web_ui/static"), name="static")

# Ana sayfa
@app.get("/", response_class=HTMLResponse)
async def home():
    """Ana sayfa"""
    with open("web_ui/static/index.html", "r", encoding="utf-8") as f:
        return f.read()

# API Endpoints
@app.post("/api/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """MongoDB sorgusunu işle"""
    try:
        # API key kontrolü
        if not await verify_api_key(request.api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        # Agent'ı al
        mongodb_agent = await get_agent()
        
        # Sorguyu işle
        logger.info(f"Sorgu alındı: {request.query[:50]}...")
        result = mongodb_agent.process_query(request.query)
        
        # Response oluştur
        return QueryResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sorgu işleme hatası: {e}")
        return QueryResponse(
            durum="hata",
            işlem="api_error",
            açıklama=f"Beklenmeyen hata: {str(e)}",
            öneriler=["Lütfen daha sonra tekrar deneyin"]
        )

@app.get("/api/status")
async def get_status():
    """Sistem durumu"""
    try:
        mongodb_agent = await get_agent()
        status = mongodb_agent.get_status()
        return {
            "status": "online",
            "agent_status": status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/collections")
async def get_collections(api_key: str):
    """Koleksiyon listesi"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        mongodb_agent = await get_agent()
        collections = mongodb_agent.get_available_collections()
        return {"collections": collections}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/schema/{collection_name}")
async def get_schema(collection_name: str, api_key: str, detailed: bool = False):
    """Koleksiyon şeması"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        mongodb_agent = await get_agent()
        schema = mongodb_agent.analyze_collection(collection_name, detailed)
        return schema
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Shutdown
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup"""
    global agent
    if agent:
        logger.info("Agent kapatılıyor...")
        agent.shutdown()
        agent = None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=True,
        log_level="info"
    )