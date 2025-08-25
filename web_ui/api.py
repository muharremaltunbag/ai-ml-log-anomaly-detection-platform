# web_ui\api.py

"""MongoDB Assistant Web API"""
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta 
import asyncio
from typing import Dict, Any, Optional, Union
from src.storage.config import MONGODB_ENABLED, MONGODB_CONFIG
from src.storage.storage_manager import StorageManager
from src.storage.fallback_storage import FileOnlyStorageManager
from uuid import uuid4  

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
from langchain.schema import HumanMessage, SystemMessage
from src.connectors.lcwgpt_connector import LCWGPTConnector

from src.agents.mongodb_agent import MongoDBAgent
from web_ui.config import *
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()


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

# YENİ: Global storage manager instance
storage_manager: Optional[StorageManager] = None
storage_lock = asyncio.Lock()

# Global LCWGPT connector instance
llm_connector: Optional[Any] = None
llm_lock = asyncio.Lock()

# Onay bekleyen parametreleri saklamak için
pending_confirmations: Dict[str, Dict[str, Any]] = {}

# Güvenli session yönetimi
user_sessions: Dict[str, Dict[str, Any]] = {}

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
    session_id: Optional[str] = None

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

# Session yönetimi fonksiyonları
def create_session(api_key: str) -> str:
    """Güvenli session oluştur"""
    session_id = str(uuid4())
    user_sessions[session_id] = {
        'api_key': api_key,
        'created_at': datetime.now(),
        'expires_at': datetime.now() + timedelta(minutes=30)
    }
    return session_id

def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Session bilgisini getir"""
    if session_id in user_sessions:
        session = user_sessions[session_id]
        if datetime.now() < session['expires_at']:
            return session
        else:
            # Süresi dolmuş session'ı sil
            del user_sessions[session_id]
    return None

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

# LCWGPT Connector'ı singleton olarak al
async def get_llm_connector():
    """Singleton LCWGPT connector instance"""
    global llm_connector
    async with llm_lock:
        if llm_connector is None:
            from src.connectors.lcwgpt_connector import LCWGPTConnector
            logger.info("LCWGPT Connector başlatılıyor...")
            llm_connector = LCWGPTConnector()
            llm_connector.connect()
            if not llm_connector.is_connected():
                logger.error("LCWGPT bağlantısı kurulamadı")
                return None
            logger.info("LCWGPT Connector hazır")
        return llm_connector

# StorageManager başlatma
async def get_storage_manager() -> Union[StorageManager, FileOnlyStorageManager]:
    """Get appropriate storage manager based on configuration"""
    global storage_manager
    async with storage_lock:
        if storage_manager is None:
            if MONGODB_ENABLED:
                logger.info("=" * 50)
                logger.info("🔧 STORAGE MANAGER İNİTİALİZASYON")
                logger.info("=" * 50)
                logger.info("📦 MongoDB StorageManager başlatılıyor...")
                logger.info(f"   📍 MongoDB URI: {MONGODB_CONFIG.get('uri', 'Not configured')[:50]}...")
                logger.info(f"   📍 Database: {MONGODB_CONFIG.get('database', 'Not configured')}")
                
                try:
                    storage_manager = StorageManager()
                    if not await storage_manager.initialize():
                        raise Exception("MongoDB connection failed")
                    logger.info("✅ MongoDB StorageManager HAZIR!")
                    logger.info("=" * 50)
                except Exception as e:
                    logger.error(f"❌ MongoDB bağlantısı başarısız: {e}")
                    logger.info("⚠️ FileOnlyStorageManager'a geçiliyor...")
                    storage_manager = FileOnlyStorageManager()
                    await storage_manager.initialize()
                    logger.info("✅ FileOnlyStorageManager HAZIR!")
                    logger.info("=" * 50)
            else:
                logger.info("=" * 50)
                logger.info("📦 File-only StorageManager başlatılıyor (MongoDB devre dışı)")
                storage_manager = FileOnlyStorageManager()
                await storage_manager.initialize()
                logger.info("✅ FileOnlyStorageManager HAZIR!")
                logger.info("=" * 50)
            
            await storage_manager.initialize()
            logger.info(f"StorageManager ready: {type(storage_manager).__name__}")
        
        return storage_manager

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
        # Güvenli session key yönetimi
        session_key = request.headers.get('X-Session-ID') if hasattr(request, 'headers') else None
        if not session_key:
            session_key = create_session(request.api_key)
            logger.info(f"New session created: {session_key[:8]}...")
        else:
            # Session'ı kontrol et
            session = get_session(session_key)
            if not session or session['api_key'] != request.api_key:
                session_key = create_session(request.api_key)
                logger.info(f"Session renewed: {session_key[:8]}...")
        
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
                # Session key'i güvenli şekilde al veya oluştur
                if not session_key:
                    session_key = create_session(request.api_key)
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
        response = QueryResponse(**result)
        response.session_id = session_key
        return response
        
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
        
        # YENİ: OpenSearch için direkt anomaly tools kullan
        if request.source_type == "opensearch":
            logger.info("OpenSearch için direkt anomaly tools kullanılıyor...")
            from src.anomaly.anomaly_tools import AnomalyDetectionTools
            
            # Anomaly tools instance oluştur
            anomaly_tools = AnomalyDetectionTools(environment='production')
            
            # Direkt analyze_mongodb_logs fonksiyonunu çağır
            tool_result = anomaly_tools.analyze_mongodb_logs({
                "source_type": "opensearch",
                "host_filter": request.host_filter,
                "time_range": request.time_range,
                "last_hours": analysis_params.get("last_hours", 24)
            })
            
            # Tool sonucunu parse et
            import json
            if isinstance(tool_result, str):
                try:
                    parsed_result = json.loads(tool_result)
                    result = parsed_result
                except:
                    result = {
                        "durum": "tamamlandı",
                        "işlem": "anomaly_analysis",
                        "açıklama": "Anomali analizi tamamlandı",
                        "sonuç": {"raw_result": tool_result}
                    }
            else:
                result = tool_result
        else:
            # Diğer source type'lar için MongoDB agent kullan
            result = mongodb_agent.process_query_with_args(query, analysis_params)
        # Tool output'u düzelt
        if result.get('işlem') == 'anomaly_analysis':
            try:
                # Agent executor'dan tool output'u al
                if hasattr(mongodb_agent, 'agent_executor') and mongodb_agent.agent_executor:
                    # Son çalıştırmanın intermediate_steps'ini kontrol et
                    last_result = getattr(mongodb_agent.agent_executor, '_last_result', None)
                    
                    # Eğer _last_result yoksa, memory'den almayı dene
                    if not last_result and hasattr(mongodb_agent, 'memory'):
                        # Memory'deki son mesajları kontrol et
                        messages = mongodb_agent.memory.chat_memory.messages
                        if messages:
                            # Son agent response'unu bul
                            for msg in reversed(messages):
                                if hasattr(msg, 'additional_kwargs'):
                                    last_result = msg.additional_kwargs
                                    break
                    
                    # Result varsa intermediate_steps'i kontrol et
                    if last_result and 'intermediate_steps' in last_result:
                        for step in last_result['intermediate_steps']:
                            if len(step) >= 2 and hasattr(step[0], 'tool') and step[0].tool == 'analyze_mongodb_logs':
                                tool_output = step[1]
                                
                                # String ise JSON olarak parse et
                                if isinstance(tool_output, str):
                                    import json
                                    parsed_output = json.loads(tool_output)
                                    if 'sonuç' in parsed_output:
                                        # ML verilerini ekle
                                        if 'sonuç' not in result:
                                            result['sonuç'] = {}
                                        result['sonuç'].update(parsed_output['sonuç'])
                                        logger.info(f"ML verileri eklendi: {list(parsed_output['sonuç'].keys())}")
            except Exception as e:
                logger.error(f"Tool output çıkarma hatası: {e}")
                for step in mongodb_agent.agent._last_run.get('intermediate_steps', []):
                    if step[0].tool == 'analyze_mongodb_logs':
                        tool_output = step[1]
                        
                        # String ise JSON olarak parse et
                        if isinstance(tool_output, str):
                            try:
                                import json
                                parsed_output = json.loads(tool_output)
                                if 'sonuç' in parsed_output:
                                    # ML verilerini ekle
                                    if 'sonuç' not in result:
                                        result['sonuç'] = {}
                                    result['sonuç'].update(parsed_output['sonuç'])
                                    logger.info(f"ML verileri eklendi: {list(parsed_output['sonuç'].keys())}")
                            except json.JSONDecodeError:
                                logger.error("Tool output JSON parse edilemedi")

        # NEW: Normalize result status for storage flow
        try:
            if result.get('işlem') == 'anomaly_analysis' and result.get('durum') not in ('tamamlandı', 'hata', 'iptal'):
                if result.get('durum') in (None, 'başarılı', 'success', 'ok'):
                    result['durum'] = 'tamamlandı'
        except Exception as _e:
            logger.warning(f"Result status normalization skipped: {_e}")

        # DEBUG: Agent response'u detaylı logla
        logger.info(f"=== AGENT RESPONSE DEBUG ===")
        logger.info(f"Result keys: {list(result.keys())}")
        if 'sonuç' in result:
            logger.info(f"Sonuç type: {type(result['sonuç'])}")
            if isinstance(result['sonuç'], dict):
                logger.info(f"Sonuç keys: {list(result['sonuç'].keys())}")
                if 'ai_explanation' in result['sonuç']:
                    logger.info("✅ AI explanation FOUND in sonuç!")
                    logger.info(f"AI explanation keys: {list(result['sonuç']['ai_explanation'].keys())}")
                else:
                    logger.info("❌ AI explanation NOT found in sonuç")

        logger.info(f"Log analizi tamamlandı - Durum: {result.get('durum', 'unknown')}")
        
        # Sonuçları da logla
        if result.get('koleksiyon'):
            logger.info(f"ANALİZ SONUCU - Kullanılan koleksiyon: {result.get('koleksiyon')}")
        if result.get('sonuç'):
            logger.info(f"ANALİZ SONUCU - Bulunan kayıt sayısı: {len(result.get('sonuç', []))}")
        
        # DEBUG: API response'da critical_anomalies sayısını logla
        if isinstance(result, dict) and 'sonuç' in result:
            if isinstance(result['sonuç'], dict) and 'critical_anomalies' in result['sonuç']:
                logger.info(f"[DEBUG API] API response contains {len(result['sonuç']['critical_anomalies'])} critical_anomalies")
                print(f"[DEBUG API] Returning {len(result['sonuç']['critical_anomalies'])} critical anomalies to frontend")
            else:
                logger.info("[DEBUG API] API response - no critical_anomalies in sonuç")
                print("[DEBUG API] No critical_anomalies found in response")
        
        # YENİ: Auto-save analysis to storage
        if request.source_type == "opensearch" and result.get('durum') in ("tamamlandı", "başarılı", "success"):
            try:
                logger.info("=" * 50)
                logger.info("📊 ANOMALİ ANALİZ SONUCU KAYIT İŞLEMİ BAŞLADI")
                logger.info("=" * 50)
                
                storage = await get_storage_manager()
                
                # Storage tipini logla
                storage_type = type(storage).__name__
                logger.info(f"📦 Storage Manager Tipi: {storage_type}")
                
                if storage_type == "StorageManager":
                    logger.info("✅ MongoDB destekli StorageManager kullanılıyor")
                else:
                    logger.info("⚠️ FileOnlyStorageManager kullanılıyor (MongoDB yok)")
                
                # Anomali sayısını logla
                anomaly_count = 0
                if 'sonuç' in result and isinstance(result['sonuç'], dict):
                    if 'critical_anomalies' in result['sonuç']:
                        anomaly_count = len(result['sonuç']['critical_anomalies'])
                
                logger.info(f"📈 Tespit edilen kritik anomali sayısı: {anomaly_count}")
                
                save_result = await storage.save_anomaly_analysis(
                    analysis_result=result,
                    source_type=request.source_type,
                    host=request.host_filter,
                    time_range=request.time_range
                )
                
                if save_result and save_result.get('analysis_id'):
                    logger.info("=" * 50)
                    logger.info("✅ ANOMALİ ANALİZİ BAŞARIYLA KAYDEDİLDİ!")
                    logger.info(f"   📍 Analysis ID: {save_result.get('analysis_id')}")
                    logger.info(f"   📍 File Path: {save_result.get('file_path')}")
                    logger.info(f"   📍 Host: {request.host_filter}")
                    logger.info(f"   📍 Time Range: {request.time_range}")
                    logger.info(f"   📍 Kritik Anomali: {anomaly_count} adet")
                    logger.info("=" * 50)
                    
                    # Result'a storage bilgisini ekle
                    result['storage_info'] = save_result
                else:
                    logger.warning("⚠️ Anomali analizi kaydedilemedi - save_result boş veya analysis_id yok")
                    
            except Exception as e:
                logger.error("=" * 50)
                logger.error("❌ ANOMALİ ANALİZİ KAYIT HATASI!")
                logger.error(f"   Hata: {str(e)}")
                logger.error("=" * 50)
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

@app.post("/api/get-detailed-anomalies")
async def get_detailed_anomalies(request: Dict[str, Any]):
    """Detaylı anomali listesini getir"""
    try:
        # API key kontrolü
        if not await verify_api_key(request.get('api_key')):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        # Agent'ı al
        mongodb_agent = await get_agent()
        
        # Anomaly tool'u direkt çağır
        from src.anomaly.anomaly_tools import get_detailed_anomalies
        
        result = get_detailed_anomalies(
            source_type=request.get('source_type', 'opensearch'),
            host_filter=request.get('host_filter'),
            time_range=request.get('time_range', 'last_day'),
            limit=request.get('limit', 1000)
        )
        
        return {
            "status": "success",
            "anomalies": result.get('anomalies', []),
            "total_count": result.get('total_count', 0)
        }
        
    except Exception as e:
        logger.error(f"Detaylı anomali verisi hatası: {e}")
        return {
            "status": "error",
            "message": str(e),
            "anomalies": []
        }

# Arka plan görevi - eski onay bekleyen parametreleri temizle
async def cleanup_pending_confirmations():
    """30 dakikadan eski onay bekleyen parametreleri temizle"""
    while True:
        try:
            current_time = datetime.now()
            expired_keys = []
            
            # Pending confirmations temizliği
            for key, data in pending_confirmations.items():
                if 'timestamp' in data:
                    created_time = datetime.fromisoformat(data['timestamp'])
                    if (current_time - created_time).total_seconds() > 1800:  # 30 dakika
                        expired_keys.append(key)
            
            for key in expired_keys:
                pending_confirmations.pop(key, None)
                logger.debug(f"Expired confirmation cleared: {key}")
            
            # Expired session'ları da temizle
            expired_sessions = []
            for session_id, session_data in user_sessions.items():
                if current_time > session_data['expires_at']:
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                del user_sessions[session_id]
                logger.debug(f"Expired session cleared: {session_id[:8]}...")
            
            await asyncio.sleep(300)  # 5 dakikada bir kontrol et
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            await asyncio.sleep(300)

# ============= YENİ STORAGE ENDPOINTS =============

@app.get("/api/anomaly-history")
async def get_anomaly_history(
    api_key: str,
    host: Optional[str] = None,
    source_type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    skip: int = Query(default=0, ge=0)
):
    """Get anomaly analysis history"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        storage = await get_storage_manager()
        
        # Build filters
        filters = {}
        if host:
            filters["host"] = host
        if source_type:
            filters["source"] = source_type
        if start_date:
            filters["start_date"] = datetime.fromisoformat(start_date)
        if end_date:
            filters["end_date"] = datetime.fromisoformat(end_date)
        
        # Get history
        history = await storage.get_anomaly_history(
            filters=filters,
            limit=limit,
            skip=skip,
            include_details=False  # Don't load full details for list
        )
        
        return {
            "status": "success",
            "count": len(history),
            "history": history
        }
        
    except Exception as e:
        logger.error(f"Error getting anomaly history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/anomaly-history/{analysis_id}")
async def get_anomaly_detail(analysis_id: str, api_key: str):
    """Get detailed anomaly analysis by ID"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        storage = await get_storage_manager()
        
        # Get specific analysis with details
        history = await storage.get_anomaly_history(
            filters={"analysis_id": analysis_id},
            limit=1,
            include_details=True
        )
        
        if not history:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        return {
            "status": "success",
            "analysis": history[0]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting anomaly detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/model-registry")
async def get_model_registry(api_key: str, active_only: bool = False):
    """Get model registry"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        storage = await get_storage_manager()
        models = await storage.mongodb.get_model_registry(active_only=active_only)
        
        return {
            "status": "success",
            "count": len(models),
            "models": models
        }
        
    except Exception as e:
        logger.error(f"Error getting model registry: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/model-registry/{version_id}/activate")
async def activate_model(version_id: str, api_key: str):
    """Activate a specific model version"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        storage = await get_storage_manager()
        success = await storage.mongodb.set_active_model(version_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Model {version_id} activated"
            }
        else:
            raise HTTPException(status_code=404, detail="Model version not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/storage-stats")
async def get_storage_statistics(api_key: str, days: int = Query(default=30, le=365)):
    """Get storage and analysis statistics"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        storage = await get_storage_manager()
        stats = await storage.get_statistics(days=days)
        
        return {
            "status": "success",
            "statistics": stats
        }
        
    except Exception as e:
        logger.error(f"Error getting storage statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/storage-cleanup")
async def cleanup_storage(api_key: str, force: bool = False):
    """Cleanup old storage data"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        storage = await get_storage_manager()
        cleanup_stats = await storage.cleanup_old_data(force=force)
        
        return {
            "status": "success",
            "cleanup_stats": cleanup_stats
        }
        
    except Exception as e:
        logger.error(f"Error during storage cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/export-analysis/{analysis_id}")
async def export_analysis(
    analysis_id: str,
    api_key: str,
    format: str = Query(default="json", regex="^(json|csv)$")
):
    """Export analysis in specified format"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        storage = await get_storage_manager()
        export_path = await storage.export_analysis(analysis_id, format=format)
        
        if export_path:
            return {
                "status": "success",
                "export_path": export_path,
                "format": format
            }
        else:
            raise HTTPException(status_code=404, detail="Analysis not found or export failed")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat-query-anomalies")
async def chat_query_anomalies(request: Dict[str, Any]):
    """Chat üzerinden anomali sorgulama - LCWGPT ile"""
    try:
        # API key kontrolü
        if not await verify_api_key(request.get('api_key')):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        query = request.get("query", "")
        analysis_id = request.get("analysis_id")
        
        logger.info(f"Chat anomaly query received - Query: {query[:50]}...")
        
        # Storage'dan anomalileri al
        storage = await get_storage_manager()
        filters = {"analysis_id": analysis_id} if analysis_id else {}
        analyses = await storage.get_anomaly_history(
            filters=filters,
            limit=1,
            include_details=True
        )
        
        if not analyses:
            return {
                "status": "error",
                "message": "Anomali analizi bulunamadı",
                "total_anomalies": 0
            }
        
        analysis = analyses[0]
        
        # Unfiltered anomalileri al
        all_anomalies = analysis.get("unfiltered_anomalies", [])
        if not all_anomalies:
            all_anomalies = analysis.get("critical_anomalies", [])
        
        logger.info(f"Found {len(all_anomalies)} anomalies for LCWGPT processing")
        
        # LCWGPT ile işle
        llm_connector = await get_llm_connector()

        if not llm_connector:
            logger.error("LCWGPT connection failed")
            return {
                "status": "error",
                "message": "LCWGPT bağlantısı kurulamadı",
                "total_anomalies": len(all_anomalies)
            }
        
        # Token limiti için chunk'lara böl (her chunk 50 anomali)
        chunk_size = 50
        first_chunk = all_anomalies[:chunk_size]
        
        # Component ve severity dağılımı hesapla
        component_dist = {}
        severity_dist = {}
        for a in all_anomalies:
            comp = a.get('component', 'N/A')
            component_dist[comp] = component_dist.get(comp, 0) + 1
            
            sev = a.get('severity_level', 'N/A')
            severity_dist[sev] = severity_dist.get(sev, 0) + 1
        
        # LCWGPT için system prompt
        system_prompt = """Sen MongoDB anomali analizi uzmanısın. Kullanıcının sorusuna göre anomalileri analiz et ve Türkçe yanıt ver.

KURALLAR:
1. Kısa, net ve aksiyona yönelik yanıtlar ver
2. Sayısal verileri ve yüzdeleri kullan
3. En kritik bulguları vurgula
4. Öneriler sun
5. Teknik ama anlaşılır ol

YANIT FORMATI:
- Önce direkt soruya cevap ver
- Sonra detayları ekle
- En sonda öneriler sun"""

        # User prompt hazırla
        user_prompt = f"""
KULLANICI SORUSU: {query}

ANALİZ VERİSİ:
- Toplam Anomali: {len(all_anomalies)}
- Zaman Aralığı: {analysis.get('time_range', 'N/A')}
- Host: {analysis.get('host', 'N/A')}

COMPONENT DAĞILIMI:
{_format_dict_for_prompt(component_dist, limit=10)}

SEVERITY DAĞILIMI:
{_format_dict_for_prompt(severity_dist)}

İLK {len(first_chunk)} ANOMALİ DETAYI:
{_format_anomalies_for_prompt(first_chunk)}

Kullanıcının sorusunu bu veriler ışığında yanıtla."""

        # LCWGPT'ye gönder
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        try:
            response = llm_connector.invoke(messages)
            ai_response = response.content
            logger.info("LCWGPT response received successfully")
        except Exception as e:
            logger.error(f"LCWGPT invoke error: {e}")
            ai_response = f"LCWGPT yanıt veremedi: {str(e)}"
        
        return {
            "status": "success",
            "total_anomalies": len(all_anomalies),
            "ai_response": ai_response,
            "analysis_id": analysis.get("analysis_id"),
            "timestamp": str(analysis.get("timestamp")),
            "chunk_info": f"1/{(len(all_anomalies) + chunk_size - 1) // chunk_size} chunk işlendi"
        }
        
    except Exception as e:
        logger.error(f"Chat anomaly query error: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "total_anomalies": 0
        }

# Helper fonksiyonlar (aynı dosyaya ekleyin)
def _format_dict_for_prompt(data: dict, limit: int = None) -> str:
    """Dictionary'yi prompt için formatla"""
    sorted_items = sorted(data.items(), key=lambda x: x[1], reverse=True)
    if limit:
        sorted_items = sorted_items[:limit]
    
    result = []
    for key, value in sorted_items:
        result.append(f"- {key}: {value} adet")
    return "\n".join(result)

def _format_anomalies_for_prompt(anomalies: list) -> str:
    """Anomalileri prompt için formatla"""
    result = []
    for i, a in enumerate(anomalies[:20], 1):  # İlk 20 anomali
        result.append(f"{i}. [{a.get('component', 'N/A')}] Score: {a.get('severity_score', 0):.1f} - {a.get('message', '')[:80]}...")
    return "\n".join(result)


# Startup event'e ekle
@app.on_event("startup")
async def startup_event():
    """Uygulama başlatıldığında"""
    # Cleanup task'ı başlat
    asyncio.create_task(cleanup_pending_confirmations())
    logger.info("Cleanup task başlatıldı")
    
    # YENİ: StorageManager'ı başlat
    try:
        storage = await get_storage_manager()
        logger.info("StorageManager initialized at startup")
    except Exception as e:
        logger.error(f"Failed to initialize StorageManager: {e}")

# Shutdown
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup"""
    global agent, storage_manager
    
    if agent:
        logger.info("Agent kapatılıyor...")
        agent.shutdown()
        agent = None
    
    # YENİ: StorageManager cleanup
    if storage_manager:
        logger.info("StorageManager kapatılıyor...")
        await storage_manager.shutdown()
        storage_manager = None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=True,
        log_level="info"
    )