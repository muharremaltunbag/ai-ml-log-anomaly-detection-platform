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

from fastapi import FastAPI, HTTPException, Request, Depends, File, UploadFile, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import logging
import shutil
import tempfile

from src.agents.mongodb_agent import MongoDBAgent
from web_ui.config import *

# Logging - Console handler eklendi
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Console handler ekle
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

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

# Onay bekleyen parametreleri saklamak için
pending_confirmations: Dict[str, Dict[str, Any]] = {}

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

class LogUploadResponse(BaseModel):
    status: str
    filename: str
    file_path: str
    size_mb: float
    format: str
    message: str

class AnalyzeLogsRequest(BaseModel):
    file_path: str = Field(..., description="Analiz edilecek log dosyası yolu")
    api_key: str = Field(..., description="API anahtarı")
    time_range: Optional[str] = Field("last_24h", description="Zaman aralığı")
    source_type: Optional[str] = Field("upload", description="Veri kaynağı: file/upload/mongodb_direct/test_servers/opensearch")
    connection_string: Optional[str] = Field(None, description="MongoDB connection string (mongodb_direct için)")
    server_name: Optional[str] = Field(None, description="Test sunucu adı (test_servers için)")
    host_filter: Optional[str] = Field(None, description="Belirli bir MongoDB sunucusu (OpenSearch için)")

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
            logger.info("MongoDBAgent instance oluşturuldu, initialize() çağrılıyor...")
            if not agent.initialize():
                logger.error("Agent initialize() başarısız oldu")
                raise HTTPException(status_code=500, detail="Agent başlatılamadı")
            logger.info("Agent başarıyla başlatıldı")
        else:
            logger.debug("Mevcut agent instance kullanılıyor")
        return agent

# Geçici dosya dizini
UPLOAD_DIR = Path("temp_logs")
UPLOAD_DIR.mkdir(exist_ok=True)

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
        logger.info(f"Query endpoint çağrıldı - Query uzunluğu: {len(request.query)}")
        
        # API key kontrolü
        if not await verify_api_key(request.api_key):
            logger.warning("Geçersiz API anahtarı ile query denemesi")
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        # Agent'ı al
        logger.info("Agent alınıyor...")
        mongodb_agent = await get_agent()
        
        # YENİ: Anomali sorgusu tespiti
        is_anomaly_query = any(keyword in request.query.lower() for keyword in [
            'anomali', 'anomaly', 'log', 'analiz'
        ])
        
        # YENİ: Onay yanıtı kontrolü
        user_response = request.query.lower().strip()
        session_key = request.api_key  # Basit session key olarak API key kullan
        
        if user_response in ['evet', 'onay', 'başlat', 'yes'] and session_key in pending_confirmations:
            # Onaylanmış parametreleri al
            logger.info("Kullanıcı onayı alındı, anomali analizi başlatılıyor")
            saved_params = pending_confirmations.pop(session_key)
            
            # Anomali analizi başlat
            result = mongodb_agent.process_query_with_args(
                "MongoDB loglarında anomali analizi yap",
                {
                    'source_type': 'opensearch',
                    'detected_server': saved_params['server'],
                    'detected_time_range': saved_params['time_range'],
                    'host_filter': saved_params['server'],
                    'confirmation_required': False,
                    'params_extracted': True
                }
            )
            
            # ✅ YENİ: Anomali analizi tamamlandığında özel durum ve işlem tipi ayarla
            if result.get('durum') == 'başarılı' and (
                result.get('işlem') == 'anomaly_analysis' or
                'summary' in result.get('sonuç', {}) or 
                'ai_explanation' in result.get('sonuç', {})
            ):
                result['durum'] = 'tamamlandı'
                result['işlem'] = 'anomaly_analysis'
                logger.info("Anomaly analysis completed - status updated to 'tamamlandı'")
            
            logger.info(f"Anomaly analysis result - işlem: {result.get('işlem')}")
            logger.info(f"Anomaly analysis result - durum: {result.get('durum')}")
            
        elif user_response in ['hayır', 'iptal', 'dur', 'no'] and session_key in pending_confirmations:
            # İptal edildi
            logger.info("Kullanıcı analizi iptal etti")
            pending_confirmations.pop(session_key, None)
            result = {
                "durum": "iptal",
                "işlem": "anomali_analizi",
                "açıklama": "Anomali analizi iptal edildi. Yeni bir sorgu girebilirsiniz.",
                "sonuç": None
            }
            
        elif is_anomaly_query:
            # YENİ: Anomali sorgusu için özel işlem
            logger.info("Anomali sorgusu tespit edildi, parametreler çıkarılıyor...")
            
            # Agent'a parametreleri çıkarması için gönder
            result = mongodb_agent.process_query_with_args(
                request.query,
                {
                    'source_type': 'opensearch',
                    'confirmation_required': False,
                    'params_extracted': False
                }
            )
            
            # Onay bekliyorsa parametreleri sakla
            if result.get('durum') == 'onay_bekliyor':
                session_key = request.api_key
                pending_confirmations[session_key] = {
                    'server': result['sonuç']['server'],
                    'time_range': result['sonuç']['time_range'],
                    'timestamp': datetime.now().isoformat()
                }
                logger.info(f"Onay için parametreler saklandı: {pending_confirmations[session_key]}")
            
        else:
            # Normal sorgu işleme
            logger.info(f"Normal sorgu işleniyor: {request.query[:50]}...")
            result = mongodb_agent.process_query(request.query)
        
        logger.info(f"Query işlendi - Sonuç durumu: {result.get('durum', 'unknown')}")
        
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
    logger.info("Collections endpoint çağrıldı")
    
    if not await verify_api_key(api_key):
        logger.warning("Geçersiz API anahtarı ile collections denemesi")
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        logger.info("Agent alınıyor...")
        mongodb_agent = await get_agent()
        logger.info("get_available_collections() çağrılıyor...")
        collections = mongodb_agent.get_available_collections()
        logger.info(f"Collections alındı - Sayı: {len(collections) if collections else 0}")
        return {"collections": collections}
    except Exception as e:
        logger.error(f"Collections alınırken hata: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/schema/{collection_name}")
async def get_schema(collection_name: str, api_key: str, detailed: bool = False):
    """Koleksiyon şeması"""
    logger.info(f"Schema endpoint çağrıldı - Collection: {collection_name}, Detailed: {detailed}")
    
    if not await verify_api_key(api_key):
        logger.warning("Geçersiz API anahtarı ile schema denemesi")
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        logger.info("Agent alınıyor...")
        mongodb_agent = await get_agent()
        logger.info(f"analyze_collection() çağrılıyor - Collection: {collection_name}")
        schema = mongodb_agent.analyze_collection(collection_name, detailed)
        logger.info(f"Schema analizi tamamlandı - Collection: {collection_name}")
        return schema
    except Exception as e:
        logger.error(f"Schema analizi hatası - Collection: {collection_name}, Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/mongodb/hosts")
async def get_mongodb_hosts(api_key: str):
    """OpenSearch'teki MongoDB sunucularını listele"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        from src.anomaly.log_reader import get_available_mongodb_hosts
        hosts = get_available_mongodb_hosts()
        return {"hosts": hosts, "count": len(hosts)}
    except Exception as e:
        logger.error(f"MongoDB hosts alınırken hata: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload-log", response_model=LogUploadResponse)
async def upload_log_file(
    file: UploadFile = File(...),
    api_key: str = Query(...)
):
    """MongoDB log dosyası yükle"""
    try:
        logger.info(f"Log upload başlatıldı - Dosya: {file.filename}")
        
        # API key kontrolü
        if not await verify_api_key(api_key):
            logger.warning("Geçersiz API anahtarı ile upload denemesi")
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        # Dosya uzantısı kontrolü
        if not file.filename.endswith(('.log', '.txt', '.json')):
            logger.error(f"Geçersiz dosya uzantısı: {file.filename}")
            raise HTTPException(
                status_code=400, 
                detail="Sadece .log, .txt veya .json dosyaları kabul edilir"
            )
        
        # Dosya boyutu kontrolü (max 100MB)
        file_size = 0
        temp_file = tempfile.NamedTemporaryFile(delete=False, dir=UPLOAD_DIR, suffix='.log')
        logger.info(f"Geçici dosya oluşturuldu: {temp_file.name}")
        
        try:
            # Dosyayı kaydet
            with temp_file as buffer:
                shutil.copyfileobj(file.file, buffer)
                file_size = buffer.tell()
            
            # Boyut kontrolü
            size_mb = file_size / (1024 * 1024)
            logger.info(f"Dosya kaydedildi - Boyut: {size_mb:.2f}MB")
            
            if size_mb > 100:
                logger.error(f"Dosya çok büyük: {size_mb:.2f}MB")
                os.unlink(temp_file.name)
                raise HTTPException(status_code=400, detail="Dosya boyutu 100MB'dan büyük olamaz")
            
            # Log formatını tespit et
            logger.info("Log formatı tespit ediliyor...")
            from src.anomaly.log_reader import MongoDBLogReader
            reader = MongoDBLogReader(log_path=temp_file.name, format="auto")
            detected_format = reader.format
            logger.info(f"Log formatı tespit edildi: {detected_format}")
            
            return LogUploadResponse(
                status="success",
                filename=file.filename,
                file_path=temp_file.name,
                size_mb=round(size_mb, 2),
                format=detected_format,
                message=f"Log dosyası başarıyla yüklendi: {detected_format} format"
            )
            
        except Exception as e:
            logger.error(f"Dosya işleme hatası: {e}")
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            raise HTTPException(status_code=500, detail=f"Dosya işleme hatası: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Log yükleme hatası: {e}")
        raise HTTPException(status_code=500, detail=f"Beklenmeyen hata: {str(e)}")

@app.post("/api/analyze-uploaded-log")
async def analyze_uploaded_log(request: AnalyzeLogsRequest):
    """Yüklenen log dosyasını analiz et"""
    try:
        logger.info(f"Log analizi başlatıldı - Source: {request.source_type}, Time Range: {request.time_range}")
        
        # API key kontrolü
        if not await verify_api_key(request.api_key):
            logger.warning("Geçersiz API anahtarı ile log analizi denemesi")
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        # YENİ: Source type'a göre kontrol
        if request.source_type == "upload":
            logger.info(f"Upload modu - Dosya kontrol ediliyor: {request.file_path}")
            # Dosya varlığı kontrolü
            if not os.path.exists(request.file_path):
                logger.error(f"Log dosyası bulunamadı: {request.file_path}")
                raise HTTPException(status_code=404, detail="Log dosyası bulunamadı")
        elif request.source_type == "mongodb_direct" and not request.connection_string:
            logger.info("MongoDB direct modu - Default connection string kullanılıyor")
            # Default connection string kullan
            request.connection_string = API_KEY  # .env'den alınabilir
        elif request.source_type == "test_servers" and not request.server_name:
            logger.error("Test servers modu - Sunucu adı belirtilmedi")
            raise HTTPException(status_code=400, detail="Test sunucu adı belirtilmeli")
        elif request.source_type == "opensearch" and not request.host_filter:
            logger.error("OpenSearch modu - Host filter belirtilmedi")
            raise HTTPException(status_code=400, detail="OpenSearch için host filter belirtilmeli")
        
        # Seçilen sunucu bilgilerini logla
        if request.source_type == "test_servers":
            logger.info(f"SEÇİLEN SUNUCU - Test Server: {request.server_name}")
            print(f"DEBUG: Test sunucu seçildi - {request.server_name}")
        elif request.source_type == "opensearch":
            logger.info(f"SEÇİLEN SUNUCU - OpenSearch Host: {request.host_filter}")
            print(f"DEBUG: OpenSearch host seçildi - {request.host_filter}")
        elif request.source_type == "mongodb_direct":
            logger.info(f"SEÇİLEN SUNUCU - MongoDB Direct: {request.connection_string[:50]}...")
            print(f"DEBUG: MongoDB direct bağlantı - {request.connection_string[:50]}...")
        
        # Agent'ı al
        logger.info("MongoDB Agent alınıyor...")
        mongodb_agent = await get_agent()
        logger.info("MongoDB Agent başarıyla alındı")
        
        # Analiz sorgusunu oluştur - OpenSearch için özel
        if request.source_type == "opensearch" and request.host_filter:
            query = f"{request.host_filter} sunucusu için MongoDB loglarında anomali analizi yap"
        else:
            query = f"MongoDB loglarında anomali analizi yap"
        
        logger.info(f"Agent'a sorgu gönderiliyor - Query: {query}")
        
        # Agent'a gönderilecek parametreleri hazırla
        analysis_params = {
            "uploaded_file_path": request.file_path if request.source_type == "upload" else None,
            "file_path": request.file_path, 
            "time_range": request.time_range,
            "source_type": request.source_type,
            "connection_string": request.connection_string,
            "server_name": request.server_name,
            "host_filter": request.host_filter
        }

        # OpenSearch için özel parametreler ekle
        if request.source_type == "opensearch":
            analysis_params.update({
                "confirmation_required": False,     # Onay gerektirme
                "params_extracted": True,          # Parametreler zaten extract edildi
                "skip_confirmation": True,         # Onay adımını atla
                "detected_server": request.host_filter,    # Server bilgisi
                "detected_time_range": request.time_range  # Zaman aralığı
            })
            logger.info(f"OpenSearch analizi için özel parametreler eklendi - Host: {request.host_filter}")
            
        # Parametreleri detaylı logla
        logger.info("AGENT PARAMETRELERI:")
        for key, value in analysis_params.items():
            if value is not None:
                if key == "connection_string" and value:
                    logger.info(f"  {key}: {str(value)[:50]}...")
                else:
                    logger.info(f"  {key}: {value}")
        
        print(f"DEBUG: Agent'a gönderilen parametreler - {analysis_params}")
        
        # MongoDB agent'a özel argümanlarla gönder
        result = mongodb_agent.process_query_with_args(query, analysis_params)
        
        logger.info(f"Log analizi tamamlandı - Durum: {result.get('durum', 'unknown')}")
        
        # Sonuçları da logla
        if result.get('koleksiyon'):
            logger.info(f"ANALİZ SONUCU - Kullanılan koleksiyon: {result.get('koleksiyon')}")
        if result.get('sonuç'):
            logger.info(f"ANALİZ SONUCU - Bulunan kayıt sayısı: {len(result.get('sonuç', []))}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Log analiz hatası: {e}")
        print(f"DEBUG ERROR: Log analiz hatası - {e}")
        return {
            "durum": "hata",
            "işlem": "log_analysis",
            "açıklama": f"Log analizi sırasında hata: {str(e)}",
            "öneriler": ["Veri kaynağını kontrol edin", "Parametreleri doğrulayın"]
        }

@app.get("/api/uploaded-logs")
async def list_uploaded_logs(api_key: str):
    """Yüklenen log dosyalarını listele"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        logs = []
        for file_path in UPLOAD_DIR.glob("*.log"):
            stat = file_path.stat()
            logs.append({
                "filename": file_path.name,
                "path": str(file_path),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "uploaded_at": datetime.fromtimestamp(stat.st_ctime).isoformat()
            })
        
        return {"logs": logs, "count": len(logs)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/uploaded-log/{filename}")
async def delete_uploaded_log(filename: str, api_key: str):
    """Yüklenen log dosyasını sil"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        file_path = UPLOAD_DIR / filename
        if file_path.exists():
            os.unlink(file_path)
            return {"status": "success", "message": f"{filename} silindi"}
        else:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Arka plan görevi - eski onay bekleyen parametreleri temizle
async def cleanup_pending_confirmations():
    """30 dakikadan eski onay bekleyen parametreleri temizle"""
    while True:
        try:
            current_time = datetime.now()
            expired_keys = []
            
            for key, data in pending_confirmations.items():
                if 'timestamp' in data:
                    created_time = datetime.fromisoformat(data['timestamp'])
                    if (current_time - created_time).total_seconds() > 1800:  # 30 dakika
                        expired_keys.append(key)
            
            for key in expired_keys:
                pending_confirmations.pop(key, None)
                logger.debug(f"Expired confirmation cleared: {key}")
            
            await asyncio.sleep(300)  # 5 dakikada bir kontrol et
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            await asyncio.sleep(300)

# Startup event'e ekle
@app.on_event("startup")
async def startup_event():
    """Uygulama başlatıldığında"""
    # Cleanup task'ı başlat
    asyncio.create_task(cleanup_pending_confirmations())
    logger.info("Cleanup task başlatıldı")

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