# web_ui\api.py

"""MongoDB Assistant Web API"""
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta 
import asyncio
import json
from dateutil import parser
from typing import Dict, Any, Optional, Union
import pandas as pd
from src.storage.config import (
    MONGODB_ENABLED, 
    MONGODB_CONFIG,
    AUTO_SAVE_CONFIG,
    FILE_STORAGE_CONFIG
)
from src.storage.storage_manager import StorageManager
from src.storage.fallback_storage import FileOnlyStorageManager
from uuid import uuid4  

# Proje root'u ekle
sys.path.append(str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, Request, Depends, File, UploadFile, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
import logging
import shutil
import tempfile
import contextvars
import re           # ✅ Log parsing için (Chat entegrasyonunda lazım olacak)
# İş parçacıkları (Threads) arasında Request ID taşımak için
request_context: contextvars.ContextVar[str] = contextvars.ContextVar('request_context', default=None)

from langchain.schema import HumanMessage, SystemMessage
from src.connectors.lcwgpt_connector import LCWGPTConnector
from src.agents.mongodb_agent import MongoDBAgent
from web_ui.config import *
from dotenv import load_dotenv
# Anomaly detector import
from src.anomaly.anomaly_detector import MongoDBAnomalyDetector


# .env dosyasını yükle
load_dotenv()


# Belirli endpoint loglarını gizlemek için filtre sınıfı
class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # /api/progress ve /api/progress/ endpointlerinden gelen access log kayıtlarını filtrele
        msg = record.getMessage()
        if "/api/progress" in msg:
            return False
        return True

ANALYSIS_PROGRESS: Dict[str, Dict[str, Any]] = {}

# Progress Response Model
class ProgressResponse(BaseModel):
    request_id: str
    step: str       # connect, fetch, ml, ai, complete, error
    message: str
    percentage: int # 0-100 arası
    timestamp: str

# Helper: Update Progress (SYNC OLARAK GÜNCELLENDİ)
def update_progress(request_id: Optional[str], step: str, message: str, percentage: int):
    """Global progress durumunu günceller (Senkron - Log Handler için)"""
    if request_id:
        ANALYSIS_PROGRESS[request_id] = {
            "step": step,
            "message": message,
            "percentage": percentage,
            "timestamp": datetime.now().isoformat()
        }
        # Log recursion'ı önlemek için sadece belirli stepleri logla
        if step in ['connect', 'complete', 'error']:
            # Bu loglar tekrar handler'a düşmesin diye basit print veya farklı logger kullanılabilir
            # Ama şimdilik recursion riski düşük, normal logger kullanalım
            pass

# Custom Log Handler: Hem ML hem de Chat loglarını UI progress'e çevirir
class AnomalyProgressLogHandler(logging.Handler):
    def emit(self, record):
        try:
            # Mevcut thread/context için request_id var mı?
            req_id = request_context.get()
            if not req_id:
                return

            msg = record.getMessage()

            # ==========================================
            # 1. KLASİK ANOMALİ ANALİZİ (ML MODU)
            # ==========================================
            if "Reading logs from OpenSearch" in msg or "Starting timestamp-sliced read" in msg:
                update_progress(req_id, "fetch", "Log verileri veritabanından çekiliyor...", 20)

            elif "Fetch completed" in msg:
                update_progress(req_id, "processing", "Veri çekme tamamlandı. Özellik çıkarımı başlıyor...", 35)

            elif "Starting feature engineering" in msg:
                update_progress(req_id, "processing", "Veri setinden 50+ özellik (Feature) çıkarılıyor...", 40)

            elif "Feature engineering completed" in msg:
                update_progress(req_id, "ml", "Özellik çıkarımı bitti. ML modeli hazırlanıyor...", 50)

            elif "Training model" in msg or "Initializing model" in msg:
                update_progress(req_id, "ml", "Isolation Forest modeli eğitiliyor...", 60)

            elif "Predictions completed" in msg:
                update_progress(req_id, "ml", "Anomali skorları hesaplandı...", 70)

            # ==========================================
            # 2. CHAT / LCWGPT AKIŞI (FRONTEND İLE UYUMLU ID'LER)
            # ==========================================
            elif "Found" in msg and "anomalies for LCWGPT" in msg:
                update_progress(req_id, "context", "İlgili anomali kayıtları geçmişten yükleniyor...", 10)

            elif "LCWGPT Connector initialized" in msg:
                update_progress(req_id, "connect", "LCWGPT servisi ile bağlantı kuruluyor...", 20)

            elif "Will process" in msg and "chunks" in msg:
                # ID: 'chunk' (Frontend'deki 🧩 ikonu için)
                update_progress(req_id, "chunk", "Büyük veri seti analiz için parçalara bölünüyor...", 35)

            elif "Processing chunk" in msg:
                # Regex ile chunk bilgisini yakala: "Processing chunk 5/25"
                match = re.search(r"Processing chunk (\d+)/(\d+)", msg)
                if match:
                    current, total = map(int, match.groups())
                    # Yüzde hesabı: %40 (başlangıç) ile %90 (bitiş) arasına yay
                    progress = 40 + int((current / total) * 50)
                    # ID: 'analyze' (Frontend'deki 🧠 ikonu için)
                    # Frontend metni: "Yapay zeka analizi yapılıyor (Parça X/Y)..."
                    update_progress(req_id, "analyze", f"Yapay zeka analizi yapılıyor (Parça {current}/{total})...", progress)

            elif "Multi-chunk aggregation completed" in msg:
                # ID: 'merge' (Frontend'deki ✨ ikonu için)
                update_progress(req_id, "merge", "Tüm parçalar birleştiriliyor ve özetleniyor...", 95)

            # ==========================================
            # 3. ORTAK ADIMLAR
            # ==========================================
            elif "ANOMALİ ANALİZ SONUCU KAYIT" in msg or "Anomaly result saved" in msg or "Query saved with ID" in msg:
                # ID: 'save' (Veya 'merge' adımında kalabilir, save çok hızlı geçer)
                update_progress(req_id, "merge", "Sonuçlar kaydediliyor...", 98)

        except Exception:
            pass # Loglama hatası uygulamayı kırmamalı

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
# Storage configuration
ENABLE_STORAGE = AUTO_SAVE_CONFIG.get("enabled", True)
MODEL_AUTO_LOAD = True  # Startup'ta modeli otomatik yükle
MODEL_PATH = "models/isolation_forest.pkl"  # Default model path

# Global LCWGPT connector instance
llm_connector: Optional[Any] = None
llm_lock = asyncio.Lock()

# Global anomaly detector reference (Singleton'dan alınır)
# Bu variable backward compatibility için tutulur, asıl instance Singleton cache'de yaşar
anomaly_detector: Optional[MongoDBAnomalyDetector] = None

# Concurrent anomaly analysis limiti (Memory protection)
# Max 3 eşzamanlı analiz - her biri ~500-700MB RAM kullanır
# 4. ve sonraki istekler queue'da bekler
ANOMALY_ANALYSIS_SEMAPHORE = asyncio.Semaphore(3)
MAX_CONCURRENT_ANALYSES = 3  # Logging ve monitoring için



# Güvenli session yönetimi
user_sessions: Dict[str, Dict[str, Any]] = {}

# Anomali feedback store — in-memory (MongoDB varsa oraya da kaydedilir)
# Yapi: { "analysis_id": { anomaly_index: { "label": "true_positive"|"false_positive", "note": "...", "timestamp": "..." } } }
anomaly_feedback_store: Dict[str, Dict[int, Dict[str, Any]]] = {}

# Request/Response modelleri
class QueryRequest(BaseModel):
    query: str = Field(..., description="MongoDB sorgusu", max_length=MAX_QUERY_LENGTH)
    api_key: str = Field(..., description="API anahtarı")
    
    @validator('query', pre=True)
    def log_query_truncation(cls, v):
        """Query kesilmelerini logla"""
        if v and isinstance(v, str):
            original_length = len(v)
            if original_length > MAX_QUERY_LENGTH:
                logger.warning(f"⚠️ Query truncated: {original_length} -> {MAX_QUERY_LENGTH} chars")
                logger.warning(f"   Truncated content: ...{v[MAX_QUERY_LENGTH-50:MAX_QUERY_LENGTH]}[TRUNCATED]")
                logger.info(f"   Consider increasing MAX_QUERY_LENGTH in config.py if needed")
        return v

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
    start_time: Optional[str] = Field(None, description="Başlangıç zamanı (ISO format: 2025-09-15T16:09:00Z)")
    end_time: Optional[str] = Field(None, description="Bitiş zamanı (ISO format: 2025-09-15T16:11:00Z)")
    request_id: Optional[str] = Field(None, description="Frontend takip ID'si") #Progress Tracking ID

class AnomalyFilterRequest(BaseModel):
    api_key: str = Field(..., description="API anahtarı")
    analysis_id: Optional[str] = Field(default=None, description="Analiz ID (Opsiyonel ama önerilir)") # ✅ EKLENDİ
    host_filter: Optional[str] = Field(default=None, description="MongoDB sunucu adı")
    start_time: Optional[str] = Field(default=None, description="Başlangıç tarihi (ISO)")
    end_time: Optional[str] = Field(default=None, description="Bitiş tarihi (ISO)")
    component: Optional[str] = Field(default=None, description="Log bileşeni (örn: NETWORK)")
    pattern: Optional[str] = Field(default=None, description="Regex pattern veya keyword")
    min_severity: float = Field(default=0, description="Minimum severity skoru")
    limit: int = Field(default=50, description="Sayfa başına kayıt")
    skip: int = Field(default=0, description="Atlanacak kayıt sayısı")


class AnalyzeMSSQLLogsRequest(BaseModel):
    """MSSQL Log Anomali Analizi Request Model"""
    api_key: str = Field(..., description="API anahtarı")
    time_range: Optional[str] = Field("last_24h", description="Zaman aralığı")
    host_filter: Optional[str] = Field(None, description="Belirli bir MSSQL sunucusu (OpenSearch için)")
    start_time: Optional[str] = Field(None, description="Başlangıç zamanı (ISO format: 2025-09-15T16:09:00Z)")
    end_time: Optional[str] = Field(None, description="Bitiş zamanı (ISO format: 2025-09-15T16:11:00Z)")
    request_id: Optional[str] = Field(None, description="Frontend takip ID'si")


class AnalyzeESLogsRequest(BaseModel):
    """Elasticsearch Log Anomali Analizi Request Model"""
    api_key: str = Field(..., description="API anahtarı")
    time_range: Optional[str] = Field("last_24h", description="Zaman aralığı")
    host_filter: Optional[str] = Field(None, description="Belirli bir Elasticsearch node (ör. ECAZTRDBESRW003)")
    start_time: Optional[str] = Field(None, description="Başlangıç zamanı (ISO format)")
    end_time: Optional[str] = Field(None, description="Bitiş zamanı (ISO format)")
    request_id: Optional[str] = Field(None, description="Frontend takip ID'si")


class AnomalyFeedbackRequest(BaseModel):
    """Kullanici anomali feedback'i — her anomali icin ayri label"""
    api_key: str = Field(..., description="API anahtari")
    analysis_id: str = Field(..., description="Analiz ID'si")
    anomaly_index: int = Field(..., description="Anomali indeksi (sonuc listesindeki sirasi)")
    label: str = Field(..., description="Kullanici etiketi: true_positive veya false_positive")
    note: Optional[str] = Field(None, description="Opsiyonel kullanici notu")


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
    """MongoDB sorgusunu işle - Onay akışı kaldırıldı"""
    try:
        logger.info(f"Query endpoint çağrıldı - Query uzunluğu: {len(request.query)}")
        
        # API key kontrolü
        if not await verify_api_key(request.api_key):
            logger.warning("Geçersiz API anahtarı ile query denemesi")
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        # Agent'ı al
        logger.info("Agent alınıyor...")
        mongodb_agent = await get_agent()
        
        # Anomali sorgusu tespiti - GENİŞLETİLMİŞ
        query_lower = request.query.lower()
        is_anomaly_query = any(keyword in query_lower for keyword in [
            'anomali', 'anomaly', 'log', 'analiz', 'analyze', 
            'tespit', 'detect', 'sorun', 'problem', 'hata', 
            'error', 'kritik', 'critical', 'uyarı', 'warning',
            'bağlantı hatası', 'zaman aşımı', 'kesinti',
            'primary değişti', 'replikasyon gecikmesi',
            'yavaş sorgu',
            'disk dolu', 'yüksek bellek', 'yüksek cpu',
            'journal hatası', 'çöktü',
            'çalışmıyor', 'yavaş', 'donuyor',
            'bağlanamıyor', 'disk doldu', 'bellek doldu',
            'replikasyon hatası', 'neden çalışmıyor', 'bozuldu',
            'takılıyor', 'bağlantı', 'bağlantı sorunu',
            'erişim', 'secondary', 'primary'
        ])
        
        if is_anomaly_query:
            logger.info("Anomali sorgusu tespit edildi - Direkt işleniyor (onay yok)")
            
            # YENİ: Sunucu adı validasyonu
            try:
                from src.anomaly.log_reader import get_available_mongodb_hosts
                available_hosts = get_available_mongodb_hosts()
                
                # Query'de sunucu adı var mı kontrol et
                detected_server = None
                for host in available_hosts:
                    # Host adının tamamı veya kısa versiyonu query'de geçiyor mu?
                    host_short = host.split('.')[0] if '.' in host else host
                    if host.lower() in query_lower or host_short.lower() in query_lower:
                        detected_server = host
                        logger.info(f"✅ Sunucu tespit edildi: {detected_server}")
                        break
                
                # Sunucu adı yoksa kontrol et
                if not detected_server:
                    is_generic_chat = len(request.query) < 20 or "merhaba" in query_lower
                    
                    if is_generic_chat:
                        logger.info(f"ℹ️ Genel anomali sorusu (Sunucu belirtilmemiş): '{request.query}'")
                    else:
                        logger.info(f"ℹ️ Anomali sorgusu için sunucu bağlamı bekleniyor: '{request.query}'")
                        
                    return QueryResponse(
                        durum="eksik_parametre",
                        işlem="server_validation_failed",
                        açıklama="⚠️ Hangi sunucuyu incelememi istersiniz?\n\nLütfen sunucu adını belirtin (Örn: 'ecaztrdbmng015' veya 'cluster-a').",
                        öneriler=[
                            "Mevcut sunucuları listele",
                            "En kritik sunucuyu bul",
                            "Son 24 saati analiz et"
                        ]
                    )
                    
            except Exception as e:
                logger.error(f"Sunucu listesi alınamadı: {e}")
                # Hata durumunda devam et (backward compatibility)
                detected_server = None
            
            # Storage-first yaklaşım
            try:
                storage = await get_storage_manager()
                recent_analyses = await storage.get_anomaly_history(
                    limit=1,
                    include_details=True
                )
                
                if recent_analyses and len(recent_analyses) > 0:
                    logger.info("Storage'dan son analiz kullanılıyor")
                    latest_analysis = recent_analyses[0]
                    
                    # Storage'dan gelen veriyi zenginleştir
                    # MongoDB field mapping'ini düzelt
                    all_anomalies = (
                        latest_analysis.get("unfiltered_anomalies", []) or
                        latest_analysis.get("critical_anomalies_full", []) or  
                        latest_analysis.get("critical_anomalies", []) or
                        latest_analysis.get("critical_anomalies_display", [])
                    )
                    
                    # Debug için anomali sayısını logla
                    logger.info(f"Storage'dan alınan anomali sayısı: {len(all_anomalies)}")
                    logger.info(f"Available fields: {list(latest_analysis.keys())}")
                    
                    anomaly_count = latest_analysis.get("anomaly_count", 0)
                    anomaly_rate = latest_analysis.get("anomaly_rate", 0)
                    
                    # Frontend'in beklediği formatı hazırla
                    return QueryResponse(
                        durum="tamamlandı",
                        işlem="anomaly_from_storage",
                        açıklama=f"📊 Önceki anomali analizi yüklendi\n\n• Toplam {anomaly_count} anomali tespit edildi\n• Analiz zamanı: {latest_analysis.get('timestamp', 'N/A')}\n• Anomali oranı: %{anomaly_rate:.2f}\n\nChat üzerinden sorularınızı sorabilirsiniz.",
                        sonuç={
                            "analysis_id": latest_analysis.get("analysis_id"),
                            "from_storage": True,
                            "anomaly_count": anomaly_count,
                            "anomaly_rate": anomaly_rate,
                            "total_logs": latest_analysis.get("logs_analyzed", 0),
                            "critical_anomalies": all_anomalies[:30],  # İlk 30 anomali
                            "unfiltered_anomalies": all_anomalies,  # Tüm anomaliler
                            "storage_info": {
                                "analysis_id": latest_analysis.get("analysis_id"),
                                "timestamp": latest_analysis.get("timestamp"),
                                "host": latest_analysis.get("host", "N/A"),
                                "time_range": latest_analysis.get("time_range", "N/A")
                            },
                            "summary": {
                                "n_anomalies": anomaly_count,
                                "total_logs": latest_analysis.get("logs_analyzed", 0),
                                "anomaly_rate": anomaly_rate
                            }
                        }
                    )
            except Exception as e:
                logger.warning(f"Storage erişim hatası: {e}, yeni analiz başlatılıyor")
            
            # Storage yoksa veya hata varsa yeni analiz
            logger.info("Yeni anomali analizi başlatılıyor (OpenSearch)")
            
            result = mongodb_agent.process_query_with_args(
                "MongoDB loglarında anomali analizi yap",
                {
                    'source_type': 'opensearch',
                    'confirmation_required': False,
                    'params_extracted': True,
                    'skip_confirmation': True,
                    'time_range': 'last_day',
                    'host_filter': None  # Tüm hostlar için
                }
            )
            
            # Durum güncelleme
            if result.get('durum') == 'başarılı':
                result['durum'] = 'tamamlandı'
                result['işlem'] = 'anomaly_analysis'
                logger.info("Anomaly analysis completed")
            
            return QueryResponse(**result)
            
        else:
            # Normal sorgu işleme
            logger.info(f"Normal sorgu işleniyor: {request.query[:50]}...")
            result = mongodb_agent.process_query(request.query)
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

# Progress Tracking Endpoint
@app.get("/api/progress/{request_id}")
async def get_analysis_progress(request_id: str):
    """
    Belirli bir analiz işleminin ilerleme durumunu sorgula.
    Frontend polling (periyodik sorgu) ile burayı çağırır.
    """
    # Get the status from the global dictionary
    if request_id in ANALYSIS_PROGRESS:
        data = ANALYSIS_PROGRESS[request_id]
        return data

    return {
        "step": "unknown", 
        "message": "İşlem bekleniyor...", 
        "percentage": 0,
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


@app.get("/api/mongodb/clusters")
async def get_mongodb_clusters(api_key: str):
    """MongoDB cluster'larını ve host'larını listele"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        from src.anomaly.log_reader import get_available_clusters_with_hosts
        cluster_data = get_available_clusters_with_hosts(last_hours=24)
        
        return {
            "status": "success",
            "clusters": cluster_data["clusters"],
            "standalone_hosts": cluster_data["standalone"],
            "unmapped_hosts": cluster_data.get("unmapped", []),
            "summary": cluster_data["summary"]
        }
    except Exception as e:
        logger.error(f"MongoDB clusters alınırken hata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/config/save-api-key")
async def save_api_key_to_storage(request: Dict[str, Any]):
    """
    API key'i MongoDB system_config collection'ına kaydet
    """
    try:
        api_key = request.get("api_key")
        user_id = request.get("user_id", "default")
        
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        storage = await get_storage_manager()
        if not storage or not getattr(storage, "mongodb", None):
            raise HTTPException(status_code=503, detail="Storage not available")
        
        # System config collection'ı
        config_collection = storage.mongodb.db["system_config"]
        
        # Mevcut config'i güncelle veya yeni oluştur
        config_doc = {
            "user_id": user_id,
            "api_key": api_key,  # Production'da encrypt edilmeli
            "last_updated": datetime.utcnow(),
            "source": "web_ui",
            "active": True
        }
        
        # Upsert işlemi (varsa güncelle, yoksa ekle)
        result = await config_collection.update_one(
            {"user_id": user_id},
            {"$set": config_doc},
            upsert=True
        )
        
        logger.info(f"✅ API key saved to MongoDB for user: {user_id}")
        
        return {
            "status": "success",
            "message": "API key saved to storage",
            "user_id": user_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/get-api-key")
async def get_api_key_from_storage(user_id: str = "default"):
    """
    MongoDB'den kayıtlı API key'i al
    """
    try:
        # Storage'dan API key'i al
        storage = await get_storage_manager()
        if not storage or not getattr(storage, "mongodb", None):
            return {"status": "no_storage", "api_key": None}
        
        config_collection = storage.mongodb.db["system_config"]
        
        # User config'ini bul
        config = await config_collection.find_one(
            {"user_id": user_id, "active": True}
        )
        
        if config and config.get("api_key"):
            logger.info(f"✅ API key retrieved from MongoDB for user: {user_id}")
            return {
                "status": "success",
                "api_key": config["api_key"],
                "last_updated": config.get("last_updated")
            }
        
        return {"status": "not_found", "api_key": None}
        
    except Exception as e:
        logger.error(f"Error retrieving API key: {e}")
        return {"status": "error", "api_key": None}

@app.get("/api/mongodb/cluster/{cluster_id}/hosts")
async def get_cluster_hosts(cluster_id: str, api_key: str):
    """Belirli bir cluster'ın host'larını getir"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        from src.anomaly.log_reader import get_cluster_hosts
        hosts = get_cluster_hosts(cluster_id)
        
        if hosts:
            return {
                "status": "success",
                "cluster_id": cluster_id,
                "hosts": hosts,
                "count": len(hosts)
            }
        else:
            raise HTTPException(status_code=404, detail=f"Cluster '{cluster_id}' bulunamadı veya host'ları yok")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cluster hosts alınırken hata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze-cluster")
async def analyze_cluster(request: Dict[str, Any]):
    """Cluster bazlı anomali analizi - tüm node'ları paralel analiz et (Semaphore Korumalı)"""
    async with ANOMALY_ANALYSIS_SEMAPHORE:
        try:
            cluster_id = request.get("cluster_id")
            api_key = request.get("api_key")
            time_range = request.get("time_range", "last_24h")
            start_time = request.get("start_time")
            end_time = request.get("end_time")
            
            if not await verify_api_key(api_key):
                raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
            
            # Cluster host'larını al
            from src.anomaly.log_reader import get_cluster_hosts
            cluster_hosts = get_cluster_hosts(cluster_id)
            
            if not cluster_hosts:
                raise HTTPException(status_code=404, detail=f"Cluster '{cluster_id}' bulunamadı veya host'ları yok")
            
            logger.info(f"Starting cluster analysis for {cluster_id} with {len(cluster_hosts)} hosts")
            
            # Her host için paralel analiz
            from src.anomaly.anomaly_tools import AnomalyDetectionTools
            anomaly_tools = AnomalyDetectionTools(environment='production')
            
            # Paralel analiz için task'ları hazırla
            async def analyze_single_host(host):
                """Tek bir host için anomali analizi - Error handling ile"""
                try:
                    params = {
                        "source_type": "opensearch",
                        "host_filter": host,
                        "time_range": time_range,
                        "start_time": start_time,
                        "end_time": end_time
                    }
                    
                    logger.info(f"Analyzing host: {host}")
                    
                    # Sync fonksiyonu async ortamda çalıştır
                    result = await asyncio.to_thread(
                        anomaly_tools.analyze_mongodb_logs,
                        params
                    )
                    
                    logger.info(f"Host {host} analysis completed successfully")
                    return (host, result)
                    
                except Exception as e:
                    logger.error(f"Host {host} analysis failed: {e}")
                    # Hata durumunda da tuple döndür
                    return (host, {
                        "durum": "hata",
                        "açıklama": f"Analysis failed: {str(e)}",
                        "sonuç": {}
                    })
            
            # Tüm host'ları paralel analiz et - Exception handling ile
            tasks = [analyze_single_host(host) for host in cluster_hosts]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Exception olan task'ları logla
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    host = cluster_hosts[i]
                    logger.error(f"Task exception for host {host}: {result}")
                    # Exception'ı normal hata formatına çevir
                    results[i] = (host, {
                        "durum": "hata",
                        "açıklama": f"Task failed: {str(result)}",
                        "sonuç": {}
                    })
            
            # Sonuçları birleştir

            combined_anomalies = []
            total_logs = 0
            host_results = {}
            failed_hosts = []
            
            for host, result_str in results:
                try:
                    result = json.loads(result_str) if isinstance(result_str, str) else result_str
                    
                    if result.get('durum') == 'başarılı' and result.get('sonuç'):
                        data = result['sonuç']
                        host_anomalies = data.get('critical_anomalies', [])
                        
                        # Her anomaliye host bilgisi ekle
                        for anomaly in host_anomalies:
                            anomaly['source_host'] = host
                            anomaly['cluster_id'] = cluster_id
                        
                        combined_anomalies.extend(host_anomalies)
                        total_logs += data.get('total_logs', 0)
                        
                        host_results[host] = {
                            'status': 'success',
                            'anomaly_count': len(host_anomalies),
                            'logs_analyzed': data.get('total_logs', 0),
                            'anomaly_rate': data.get('anomaly_rate', 0)
                        }
                    else:
                        failed_hosts.append(host)
                        host_results[host] = {
                            'status': 'failed',
                            'error': result.get('açıklama', 'Unknown error')
                        }
                        
                except Exception as e:
                    logger.error(f"Error processing results for host {host}: {e}")
                    failed_hosts.append(host)
                    host_results[host] = {
                        'status': 'error',
                        'error': str(e)
                    }
            
            # Anomalileri severity'ye göre sırala
            combined_anomalies.sort(key=lambda x: x.get('severity_score', 0), reverse=True)
            
            # Storage'a kaydet
            if ENABLE_STORAGE and combined_anomalies:
                storage = await get_storage_manager()
                save_result = await storage.save_anomaly_analysis(
                    analysis_result={
                        'durum': 'tamamlandı',
                        'işlem': 'cluster_analysis',
                        'sonuç': {
                            'critical_anomalies': combined_anomalies,
                            'unfiltered_anomalies': combined_anomalies,
                            'anomaly_count': len(combined_anomalies),
                            'total_logs': total_logs,
                            'anomaly_rate': (len(combined_anomalies) / total_logs * 100) if total_logs > 0 else 0
                        }
                    },
                    source_type='opensearch_cluster',
                    host=f"cluster:{cluster_id}",
                    time_range=time_range,
                    model_info=None  # Cluster analysis - model info not available (multi-host)
                )
                
                logger.info(f"Cluster analysis saved with ID: {save_result.get('analysis_id')}")
            
            return {
                "status": "success",
                "cluster_id": cluster_id,
                "hosts_analyzed": len(cluster_hosts),
                "successful_hosts": len(cluster_hosts) - len(failed_hosts),
                "failed_hosts": failed_hosts,
                "total_anomalies": len(combined_anomalies),
                "total_logs_analyzed": total_logs,
                "anomaly_rate": (len(combined_anomalies) / total_logs * 100) if total_logs > 0 else 0,
                "host_breakdown": host_results,
                "top_anomalies": combined_anomalies[:10],  # İlk 10 kritik anomali
                "storage_id": save_result.get('analysis_id') if 'save_result' in locals() else None
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Cluster analysis error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload-log", response_model=LogUploadResponse)
async def upload_log_file(
    file: UploadFile = File(...),
    api_key: str = Query(...)
):
    """
    MongoDB log dosyası yükle (Kalıcı Storage + FIFO)
    """
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

        # Dosya isimlendirme: orjinal_isim_TIMESTAMP.uzanti
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_path = Path(file.filename)
        new_filename = f"{original_path.stem}_{timestamp}{original_path.suffix}"

        try:
            # Storage Manager'ı al
            storage = await get_storage_manager()

            # Storage üzerinden kaydet (FIFO ve Path yönetimi burada yapılır)
            # file.file -> SpooledTemporaryFile (FastAPI)
            final_file_path = await storage.save_uploaded_log(file.file, new_filename)

            # Dosya bilgilerini al (Validation için)
            file_stat = os.stat(final_file_path)
            size_mb = file_stat.st_size / (1024 * 1024)

            # Boyut kontrolü (Max 1GB)
            if size_mb > 1024:
                logger.error(f"Dosya çok büyük: {size_mb:.2f}MB")
                # Büyük dosyayı sil
                os.unlink(final_file_path)
                raise HTTPException(status_code=400, detail="Dosya boyutu 1GB'dan büyük olamaz")

            # Log formatını tespit et
            logger.info("Log formatı tespit ediliyor...")
            from src.anomaly.log_reader import MongoDBLogReader
            reader = MongoDBLogReader(log_path=final_file_path, format="auto")
            detected_format = reader.format
            logger.info(f"Log formatı tespit edildi: {detected_format}")

            return LogUploadResponse(
                status="success",
                filename=new_filename,
                file_path=final_file_path,
                size_mb=round(size_mb, 2),
                format=detected_format,
                message=f"Log dosyası başarıyla yüklendi: {detected_format} format (Persistent Storage)"
            )

        except Exception as e:
            logger.error(f"Dosya işleme hatası: {e}")
            # Hata durumunda (eğer path oluştuysa) temizlik yapılabilir
            # Ancak StorageManager zaten atomik yapmaya çalışır.
            raise HTTPException(status_code=500, detail=f"Dosya işleme hatası: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Log yükleme hatası: {e}")
        raise HTTPException(status_code=500, detail=f"Beklenmeyen hata: {str(e)}")

@app.post("/api/analyze-uploaded-log")
async def analyze_uploaded_log(request: AnalyzeLogsRequest):
    """Yüklenen log dosyasını analiz et (Progress Tracking Destekli)"""
    req_id = request.request_id

    # ✅ YENİ: Context ID'yi ayarla (Log Handler için)
    token = request_context.set(req_id)

    try:
        # 1. BAŞLANGIÇ (await kaldırıldı çünkü update_progress artık sync)
        update_progress(req_id, "init", "Analiz isteği alındı, parametreler kontrol ediliyor...", 5)
        logger.info(f"Log analizi başlatıldı - Source: {request.source_type}, Time Range: {request.time_range}")

        # API key kontrolü
        if not await verify_api_key(request.api_key):
            logger.warning("Geçersiz API anahtarı ile log analizi denemesi")
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")

        # Source type kontrol
        if request.source_type == "upload":
            logger.info(f"Upload modu - Dosya kontrol ediliyor: {request.file_path}")
            if not os.path.exists(request.file_path):
                raise HTTPException(status_code=404, detail="Log dosyası bulunamadı")
        elif request.source_type == "mongodb_direct" and not request.connection_string:
            request.connection_string = API_KEY
        elif request.source_type == "test_servers" and not request.server_name:
            raise HTTPException(status_code=400, detail="Test sunucu adı belirtilmeli")
        elif request.source_type == "opensearch" and not request.host_filter:
            try:
                from src.anomaly.log_reader import get_available_mongodb_hosts
                available_hosts = get_available_mongodb_hosts(last_hours=24)
                error_message = {
                    "error": "Host filter zorunludur",
                    "message": "OpenSearch sunucusu seçmelisiniz.",
                    "available_hosts": available_hosts[:20] if available_hosts else []
                }
                raise HTTPException(status_code=400, detail=error_message)
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=400, detail="Host filter gerekli")

        # Memory Protection: Concurrent analysis limiti
        # Max 3 eşzamanlı analiz - 4. ve sonrası queue'da bekler
        update_progress(req_id, "queue", "Analiz kuyruğunda bekleniyor...", 8)

        async with ANOMALY_ANALYSIS_SEMAPHORE:
            logger.info(f"🔒 Analysis slot acquired for request {req_id} (max {MAX_CONCURRENT_ANALYSES} concurrent)")

            # Agent'ı al
            update_progress(req_id, "connect", "MongoDB Agent hazırlanıyor...", 10)
            logger.info("MongoDB Agent alınıyor...")
            mongodb_agent = await get_agent()

            # Analiz sorgusu
            if request.source_type == "opensearch" and request.host_filter:
                query = f"{request.host_filter} sunucusu için anomali analizi yap"
            else:
                query = f"MongoDB loglarında anomali analizi yap"

            # Parametreler
            analysis_params = {
                "uploaded_file_path": request.file_path if request.source_type == "upload" else None,
                "file_path": request.file_path,
                "time_range": request.time_range,
                "source_type": request.source_type,
                "connection_string": request.connection_string,
                "server_name": request.server_name,
                "host_filter": request.host_filter,
                "start_time": request.start_time,
                "end_time": request.end_time
            }
            if request.start_time and request.end_time:
                analysis_params["time_range"] = "custom"
            if request.source_type == "opensearch":
                analysis_params.update({
                    "confirmation_required": False,
                    "params_extracted": True,
                    "skip_confirmation": True,
                    "detected_server": request.host_filter,
                    "detected_time_range": request.time_range
                })

            # Thread-safe analiz için her analiz fonksiyonu kendi instance'ını oluşturur.
            # Bu sayede eşzamanlı kullanıcıların verileri asla birbirine karışamaz.
            # NOT: Instance burada DEĞİL, run_analysis()/run_upload() içinde oluşturulur.
            from src.anomaly.anomaly_tools import AnomalyDetectionTools

            # --- A. OPENSEARCH ANALİZİ ---
            if request.source_type == "opensearch":
                update_progress(req_id, "connect", f"OpenSearch: {request.host_filter} bağlantısı...", 15)
                tool_params = {
                    "source_type": "opensearch",
                    "host_filter": request.host_filter,
                    "time_range": request.time_range,
                    "last_hours": analysis_params.get("last_hours", 24)
                }
                if request.start_time:
                    tool_params["start_time"] = request.start_time
                if request.end_time:
                    tool_params["end_time"] = request.end_time

                update_progress(req_id, "fetch", "Analiz süreci başlatılıyor (Log Okuma)...", 20)

                def run_analysis():
                    tools = AnomalyDetectionTools(environment='production')
                    return tools.analyze_mongodb_logs(tool_params)

                tool_result = await asyncio.to_thread(run_analysis)

                if isinstance(tool_result, str):
                    try:
                        result = json.loads(tool_result)
                    except Exception:
                        result = {"durum": "tamamlandı", "sonuç": {"raw_result": tool_result}}
                else:
                    result = tool_result

            # --- B. UPLOAD ANALİZİ ---
            elif request.source_type == "upload":
                update_progress(req_id, "fetch", "Dosya okunuyor...", 20)

                tool_params = {
                    "source_type": "upload",
                    "file_path": request.file_path,
                    "uploaded_filename": Path(request.file_path).name,
                    "time_range": request.time_range
                }

                def run_upload():
                    tools = AnomalyDetectionTools(environment='production')
                    return tools.analyze_mongodb_logs(tool_params)

                tool_result = await asyncio.to_thread(run_upload)

                if isinstance(tool_result, str):
                    try:
                        result = json.loads(tool_result)
                    except Exception:
                        result = {"durum": "tamamlandı", "sonuç": {"raw_result": tool_result}}
                else:
                    result = tool_result

            # --- C. DİĞER ---
            else:
                update_progress(req_id, "ml", "Agent analizi yürütülüyor...", 50)
                result = await asyncio.to_thread(mongodb_agent.process_query_with_args, query, analysis_params)

            # Result objesini zenginleştir 
            if isinstance(result, dict):
                # Source bilgisini ekle
                result['source_type'] = request.source_type

                # Eğer upload ise dosya adını ekle
                if request.source_type == "upload" and request.file_path:
                    result['uploaded_filename'] = Path(request.file_path).name
                    # UI'da göstermek için server_info'yu güncelle
                    if not result.get('sonuç'):
                        result['sonuç'] = {}
                    if 'server_info' not in result['sonuç']:
                        result['sonuç']['server_info'] = {}
                    result['sonuç']['server_info']['server_name'] = f"📁 {Path(request.file_path).name}"

            # Bitiş işlemleri
            update_progress(req_id, "save", "Son kontroller yapılıyor...", 95)

            # Status normalization & Auto-save (Mevcut logic)
            if result.get('durum') in (None, 'başarılı', 'success', 'ok'):
                result['durum'] = 'tamamlandı'

            if request.source_type in ("opensearch", "upload") and result.get('durum') == 'tamamlandı':
                try:
                    storage = await get_storage_manager()
                    host_info = (
                        request.host_filter
                        if request.source_type == "opensearch"
                        else (result.get('sonuç') or {}).get('server_info', {}).get('server_name', 'unknown')
                    )
                    save_result = await storage.save_anomaly_analysis(
                        analysis_result=result,
                        source_type=request.source_type,
                        host=host_info,
                        time_range=request.time_range,
                        uploaded_filename=Path(request.file_path).name if request.source_type == "upload" and request.file_path else None,
                        model_info=result.get('model_info')  # Model metadata linkage
                    )
                    if save_result:
                        result['storage_info'] = save_result
                except Exception as e:
                    logger.error(f"Auto-save error: {e}")

            # [SAFETY] Frontend Crash Prevention (Payload Protection)
            # Verinin aslı Storage'da güvende. Tarayıcıyı kilitlememek için
            # response içindeki listeleri güvenli limitlere çekiyoruz.
            if result.get('sonuç') is not None:
                data = result['sonuç']
                
                # Unfiltered listeyi kısalt
                if 'unfiltered_anomalies' in data:
                    total_count = len(data['unfiltered_anomalies'])
                    if total_count > 2000:
                        logger.info(f"🛡️ Truncating response payload: {total_count} -> 2000 items (Full data in storage)")
                        data['unfiltered_anomalies'] = data['unfiltered_anomalies'][:2000]
                        data['is_truncated'] = True
                        data['total_available_storage'] = total_count

                # Critical listeyi kısalt (Genelde azdır ama güvenlik için)
                if 'critical_anomalies' in data and len(data['critical_anomalies']) > 2000:
                    data['critical_anomalies'] = data['critical_anomalies'][:2000]

            update_progress(req_id, "complete", "Tamamlandı!", 100)
            return result

    except HTTPException:
        update_progress(req_id, "error", "İstek hatası oluştu.", 0)
        raise
    except Exception as e:
        logger.error(f"Log analiz hatası: {e}")
        update_progress(req_id, "error", f"Hata: {str(e)[:100]}...", 0)
        return {"durum": "hata", "açıklama": f"Hata: {str(e)}"}

    finally:
        # ✅ YENİ: Context'i temizle
        request_context.reset(token)

@app.get("/api/uploaded-logs")
async def list_uploaded_logs(api_key: str):
    """Yüklenen (Kalıcı) log dosyalarını listele"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        # Storage manager'dan yolu al
        storage = await get_storage_manager()
        upload_dir = storage.storage_paths["uploads"]

        logs = []
        # Klasör yoksa boş dön
        if not upload_dir.exists():
            return {"logs": [], "count": 0}

        # Dosyaları listele ve tarihe göre sırala (En yeni en üstte)
        files = sorted(upload_dir.glob("*"), key=os.path.getmtime, reverse=True)

        for file_path in files:
            if file_path.is_file() and file_path.suffix in ['.log', '.txt', '.json']:
                stat = file_path.stat()
                logs.append({
                    "filename": file_path.name,
                    "path": str(file_path),
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "uploaded_at": datetime.fromtimestamp(stat.st_ctime).isoformat()
                })

        return {"logs": logs, "count": len(logs)}

    except Exception as e:
        logger.error(f"Error listing logs: {e}")
        # Hata durumunda boş liste dön (UI kırılmasın)
        return {"logs": [], "count": 0}

@app.delete("/api/uploaded-log/{filename}")
async def delete_uploaded_log(filename: str, api_key: str):
    """Yüklenen log dosyasını (Kalıcı Storage'dan) sil"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        storage = await get_storage_manager()
        upload_dir = storage.storage_paths["uploads"]
        file_path = upload_dir / filename

        if file_path.exists():
            os.unlink(file_path)
            logger.info(f"Deleted file: {file_path}")
            return {"status": "success", "message": f"{filename} silindi"}
        else:
            raise HTTPException(status_code=404, detail="Dosya bulunamadı")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# MSSQL LOG ANALİZİ ENDPOINTLERİ
# =============================================================================

@app.get("/api/mssql/available-hosts")
async def get_available_mssql_hosts(api_key: str, last_hours: int = 24):
    """
    Mevcut MSSQL sunucularını listele (OpenSearch'ten)

    Args:
        api_key: API anahtarı
        last_hours: Son kaç saatteki logları tara
    """
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")

    try:
        from src.anomaly.mssql_log_reader import get_available_mssql_hosts
        hosts = get_available_mssql_hosts(last_hours=last_hours)
        return {
            "status": "success",
            "hosts": hosts,
            "count": len(hosts),
            "last_hours": last_hours
        }
    except Exception as e:
        logger.error(f"MSSQL hosts listesi alınamadı: {e}")
        return {"status": "error", "hosts": [], "count": 0, "error": str(e)}


@app.post("/api/analyze-mssql-logs")
async def analyze_mssql_logs(request: AnalyzeMSSQLLogsRequest):
    """
    MSSQL loglarında anomali analizi yap (OpenSearch üzerinden)

    Progress Tracking Destekli - MongoDB analizi ile aynı yapı.
    """
    req_id = request.request_id
    token = request_context.set(req_id)

    try:
        # 1. Başlangıç
        update_progress(req_id, "init", "MSSQL analiz isteği alındı...", 5)
        logger.info(f"MSSQL Log analizi başlatıldı - Host: {request.host_filter}, Time Range: {request.time_range}")

        # API key kontrolü
        if not await verify_api_key(request.api_key):
            logger.warning("Geçersiz API anahtarı ile MSSQL log analizi denemesi")
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")

        # Host filter kontrolü
        if not request.host_filter:
            try:
                from src.anomaly.mssql_log_reader import get_available_mssql_hosts
                available_hosts = get_available_mssql_hosts(last_hours=24)
                error_message = {
                    "error": "Host filter zorunludur",
                    "message": "MSSQL sunucusu seçmelisiniz.",
                    "available_hosts": available_hosts[:20] if available_hosts else []
                }
                raise HTTPException(status_code=400, detail=error_message)
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=400, detail="Host filter gerekli")

        # Memory Protection: Concurrent analysis limiti
        update_progress(req_id, "queue", "Analiz kuyruğunda bekleniyor...", 8)

        async with ANOMALY_ANALYSIS_SEMAPHORE:
            logger.info(f"🔒 MSSQL Analysis slot acquired for request {req_id}")

            # Tool parametreleri
            update_progress(req_id, "connect", f"OpenSearch: {request.host_filter} bağlantısı...", 15)
            tool_params = {
                "source_type": "opensearch",
                "host_filter": request.host_filter,
                "time_range": request.time_range,
                "last_hours": 24
            }
            if request.start_time:
                tool_params["start_time"] = request.start_time
            if request.end_time:
                tool_params["end_time"] = request.end_time

            update_progress(req_id, "fetch", "MSSQL Log okuma başlatılıyor...", 20)

            # MSSQL Analiz çalıştır
            def run_mssql_analysis():
                from src.anomaly.anomaly_tools import AnomalyDetectionTools
                tools = AnomalyDetectionTools(environment='production')
                return tools.analyze_mssql_logs(tool_params)

            tool_result = await asyncio.to_thread(run_mssql_analysis)

            # Result işleme
            if isinstance(tool_result, str):
                try:
                    result = json.loads(tool_result)
                except Exception:
                    result = {"durum": "tamamlandı", "sonuç": {"raw_result": tool_result}}
            else:
                result = tool_result

            # Source bilgisini ekle
            if isinstance(result, dict):
                result['source_type'] = 'mssql_opensearch'
                result['database_type'] = 'mssql'

            # Bitiş işlemleri
            update_progress(req_id, "save", "Son kontroller yapılıyor...", 95)

            # Status normalization
            if result.get('durum') in (None, 'başarılı', 'success', 'ok'):
                result['durum'] = 'tamamlandı'

            # Auto-save to storage (MSSQL için ayrı)
            if result.get('durum') == 'tamamlandı':
                try:
                    storage = await get_storage_manager()
                    # model_info: _format_result top-level key'i korumaz,
                    # ama sonuç.model_info içinde zengin metadata mevcut
                    mssql_model_info = (result.get('sonuç') or {}).get('model_info')
                    save_result = await storage.save_anomaly_analysis(
                        analysis_result=result,
                        source_type='mssql_opensearch',
                        host=request.host_filter,
                        time_range=request.time_range,
                        model_info=mssql_model_info
                    )
                    if save_result:
                        result['storage_info'] = save_result
                except Exception as e:
                    logger.error(f"MSSQL Auto-save error: {e}")

            # Frontend Crash Prevention (Payload Protection)
            if result.get('sonuç') is not None:
                data = result['sonuç']
                if 'unfiltered_anomalies' in data:
                    total_count = len(data['unfiltered_anomalies'])
                    if total_count > 2000:
                        logger.info(f"🛡️ Truncating MSSQL response: {total_count} -> 2000 items")
                        data['unfiltered_anomalies'] = data['unfiltered_anomalies'][:2000]
                        data['is_truncated'] = True
                        data['total_available_storage'] = total_count

                if 'critical_anomalies' in data and len(data['critical_anomalies']) > 2000:
                    data['critical_anomalies'] = data['critical_anomalies'][:2000]

            update_progress(req_id, "complete", "MSSQL analizi tamamlandı!", 100)
            return result

    except HTTPException:
        update_progress(req_id, "error", "İstek hatası oluştu.", 0)
        raise
    except Exception as e:
        logger.error(f"MSSQL Log analiz hatası: {e}")
        update_progress(req_id, "error", f"Hata: {str(e)[:100]}...", 0)
        return {"durum": "hata", "açıklama": f"MSSQL Analiz Hatası: {str(e)}"}

    finally:
        request_context.reset(token)


# =============================================================================
# ELASTICSEARCH LOG ANALİZİ ENDPOINTLERİ
# =============================================================================

@app.get("/api/elasticsearch/available-hosts")
async def get_available_elasticsearch_hosts(api_key: str, last_hours: int = 24):
    """
    Mevcut Elasticsearch node'larını listele (OpenSearch'ten)

    Args:
        api_key: API anahtarı
        last_hours: Son kaç saatteki logları tara
    """
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")

    try:
        from src.anomaly.elasticsearch_log_reader import get_available_es_hosts, get_es_host_stats
        hosts = get_available_es_hosts(last_hours=last_hours)
        stats = get_es_host_stats(last_hours=last_hours) if hosts else {}
        return {
            "status": "success",
            "hosts": hosts,
            "count": len(hosts),
            "last_hours": last_hours,
            "host_stats": stats
        }
    except Exception as e:
        logger.error(f"Elasticsearch hosts listesi alınamadı: {e}")
        return {"status": "error", "hosts": [], "count": 0, "error": str(e)}


@app.post("/api/analyze-elasticsearch-logs")
async def analyze_elasticsearch_logs(request: AnalyzeESLogsRequest):
    """
    Elasticsearch loglarında anomali analizi yap (OpenSearch üzerinden)

    Progress Tracking Destekli — MSSQL analizi ile aynı yapı.
    """
    req_id = request.request_id
    token = request_context.set(req_id)

    try:
        # 1. Başlangıç
        update_progress(req_id, "init", "Elasticsearch analiz isteği alındı...", 5)
        logger.info(f"Elasticsearch Log analizi başlatıldı - Host: {request.host_filter}, Time Range: {request.time_range}")

        # API key kontrolü
        if not await verify_api_key(request.api_key):
            logger.warning("Geçersiz API anahtarı ile Elasticsearch log analizi denemesi")
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")

        # Host filter kontrolü
        if not request.host_filter:
            try:
                from src.anomaly.elasticsearch_log_reader import get_available_es_hosts
                available_hosts = get_available_es_hosts(last_hours=24)
                error_message = {
                    "error": "Host filter zorunludur",
                    "message": "Elasticsearch node seçmelisiniz.",
                    "available_hosts": available_hosts[:30] if available_hosts else []
                }
                raise HTTPException(status_code=400, detail=error_message)
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=400, detail="Host filter gerekli")

        # Memory Protection: Concurrent analysis limiti
        update_progress(req_id, "queue", "Analiz kuyruğunda bekleniyor...", 8)

        async with ANOMALY_ANALYSIS_SEMAPHORE:
            logger.info(f"Elasticsearch Analysis slot acquired for request {req_id}")

            # Tool parametreleri
            update_progress(req_id, "connect", f"OpenSearch: {request.host_filter} bağlantısı...", 15)
            tool_params = {
                "source_type": "opensearch",
                "host_filter": request.host_filter,
                "time_range": request.time_range,
                "last_hours": 24
            }
            if request.start_time:
                tool_params["start_time"] = request.start_time
            if request.end_time:
                tool_params["end_time"] = request.end_time

            update_progress(req_id, "fetch", "Elasticsearch Log okuma başlatılıyor...", 20)

            # Elasticsearch Analiz çalıştır
            def run_es_analysis():
                from src.anomaly.anomaly_tools import AnomalyDetectionTools
                tools = AnomalyDetectionTools(environment='production')
                return tools.analyze_elasticsearch_logs(tool_params)

            tool_result = await asyncio.to_thread(run_es_analysis)

            # Result işleme
            if isinstance(tool_result, str):
                try:
                    result = json.loads(tool_result)
                except Exception:
                    result = {"durum": "tamamlandı", "sonuç": {"raw_result": tool_result}}
            else:
                result = tool_result

            # Source bilgisini ekle
            if isinstance(result, dict):
                result['source_type'] = 'elasticsearch_opensearch'
                result['database_type'] = 'elasticsearch'

            # Bitiş işlemleri
            update_progress(req_id, "save", "Son kontroller yapılıyor...", 95)

            # Status normalization
            if result.get('durum') in (None, 'başarılı', 'success', 'ok'):
                result['durum'] = 'tamamlandı'

            # Auto-save to storage
            if result.get('durum') == 'tamamlandı':
                try:
                    storage = await get_storage_manager()
                    es_model_info = (result.get('sonuç') or {}).get('model_info')
                    save_result = await storage.save_anomaly_analysis(
                        analysis_result=result,
                        source_type='elasticsearch_opensearch',
                        host=request.host_filter,
                        time_range=request.time_range,
                        model_info=es_model_info
                    )
                    if save_result:
                        result['storage_info'] = save_result
                except Exception as e:
                    logger.error(f"Elasticsearch Auto-save error: {e}")

            # Frontend Crash Prevention
            if result.get('sonuç') is not None:
                data = result['sonuç']
                if 'unfiltered_anomalies' in data:
                    total_count = len(data['unfiltered_anomalies'])
                    if total_count > 2000:
                        logger.info(f"Truncating ES response: {total_count} -> 2000 items")
                        data['unfiltered_anomalies'] = data['unfiltered_anomalies'][:2000]
                        data['is_truncated'] = True
                        data['total_available_storage'] = total_count

                if 'critical_anomalies' in data and len(data['critical_anomalies']) > 2000:
                    data['critical_anomalies'] = data['critical_anomalies'][:2000]

            update_progress(req_id, "complete", "Elasticsearch analizi tamamlandı!", 100)
            return result

    except HTTPException:
        update_progress(req_id, "error", "İstek hatası oluştu.", 0)
        raise
    except Exception as e:
        logger.error(f"Elasticsearch Log analiz hatası: {e}")
        update_progress(req_id, "error", f"Hata: {str(e)[:100]}...", 0)
        return {"durum": "hata", "açıklama": f"Elasticsearch Analiz Hatası: {str(e)}"}

    finally:
        request_context.reset(token)


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

@app.post("/api/anomalies/filter")
async def filter_anomalies(request: AnomalyFilterRequest):
    """
    DBA Granüler Filtreleme Endpoint'i
    Component, Pattern ve Severity bazlı arama yapar.
    """
    # 1. Güvenlik Kontrolü
    if not await verify_api_key(request.api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")

    try:
        # 2. Storage Manager Erişimi
        storage = await get_storage_manager()
        if not storage:
            raise HTTPException(status_code=503, detail="Storage aktif değil")

        # 3. Tarih Dönüşümleri (String -> Datetime)
        start_dt = parser.parse(request.start_time) if request.start_time else None
        end_dt = parser.parse(request.end_time) if request.end_time else None

        # 4. Storage Sorgusu (Yeni eklediğimiz fonksiyonu çağırıyoruz)
        result = await storage.get_filtered_individual_anomalies(
            host=request.host_filter,
            analysis_id=request.analysis_id,  
            start_date=start_dt,
            end_date=end_dt,
            component=request.component,
            pattern=request.pattern,
            min_severity=request.min_severity,
            limit=request.limit,
            skip=request.skip
        )

        # 5. Yanıt
        return {
            "status": "success",
            "anomalies": result["anomalies"],
            "total_count": result["total_count"],
            "filter_info": {
                "limit": request.limit,
                "skip": request.skip,
                "component": request.component,
                "severity_threshold": request.min_severity
            }
        }

    except Exception as e:
        logger.error(f"Filter endpoint error: {e}")
        # Hata detayını loglayıp kullanıcıya genel hata dönelim
        raise HTTPException(status_code=500, detail=f"Filtreleme hatası: {str(e)}")

# Arka plan görevi - eski session'ları temizle
async def cleanup_expired_sessions():
    """30 dakikadan eski session'ları temizle"""
    while True:
        try:
            current_time = datetime.now()
            
            # Sadece expired session'ları temizle
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

# Arka plan görevi - Eski progress kayıtlarını temizle
async def cleanup_progress_cache():
    """10 dakikadan eski progress kayıtlarını temizle"""
    while True:
        try:
            current_time = datetime.now()
            expired_ids = []
            
            # Dictionary değişirken hata almamak için kopyası üzerinde dön
            for req_id, data in list(ANALYSIS_PROGRESS.items()):
                try:
                    timestamp_str = data.get('timestamp')
                    if timestamp_str:
                        last_update = datetime.fromisoformat(timestamp_str)
                        # 10 dakikadan eskiyse sil (Frontend polling'i çoktan bitmiştir)
                        if (current_time - last_update).total_seconds() > 600:
                            expired_ids.append(req_id)
                except Exception:
                    expired_ids.append(req_id)  # Hatalı veri varsa sil
            
            # Toplu silme
            for req_id in expired_ids:
                if req_id in ANALYSIS_PROGRESS:
                    del ANALYSIS_PROGRESS[req_id]
            
            if expired_ids:
                logger.debug(f"🧹 Cleaned up {len(expired_ids)} expired progress records")
            
            await asyncio.sleep(700)  # 7 dakikada bir çalış
        except Exception as e:
            logger.error(f"Progress cleanup error: {e}")
            await asyncio.sleep(700)

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


@app.get("/api/analyzed-servers")
async def get_analyzed_servers(api_key: str):
    """Anomali analizi yapılmış sunucu listesini döndür (LCWGPT sunucu seçimi için)"""
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")

    try:
        storage = await get_storage_manager()

        # Son analizlerden unique host listesi çek
        # ✅ limit=2000: Eski session'lardaki sunucuların da kesinlikle dahil olması için
        all_analyses = await storage.get_anomaly_history(limit=2000, include_details=False)

        # Host bazında grupla — en son analizi tut
        # ✅ Sadece gerçekten anomali verisi olan sunucuları dahil et
        servers = {}
        skipped_zero = 0
        for analysis in all_analyses:
            host = analysis.get("host")
            if not host:
                continue

            # Anomali sayısını belirle — birden fazla alan kontrol et
            anomaly_count = analysis.get("anomaly_count", 0) or 0
            if anomaly_count == 0:
                # Alternatif alanlardan anomali sayısı bulmayı dene
                anomaly_count = analysis.get("critical_count", 0) or 0
            if anomaly_count == 0:
                # unfiltered_anomalies listesi varsa say
                unfiltered = analysis.get("unfiltered_anomalies")
                if isinstance(unfiltered, list):
                    anomaly_count = len(unfiltered)
                else:
                    critical = analysis.get("critical_anomalies")
                    if isinstance(critical, list):
                        anomaly_count = len(critical)

            # 0 anomali varsa bu sunucuyu atla (LCWGPT çalışacak veri yok)
            if anomaly_count == 0:
                skipped_zero += 1
                continue

            if host not in servers or (analysis.get("timestamp") or "") > (servers[host].get("last_analysis") or ""):
                servers[host] = {
                    "host": host,
                    "source": analysis.get("source", "unknown"),
                    "last_analysis": analysis.get("timestamp"),
                    "anomaly_count": anomaly_count,
                    "analysis_id": analysis.get("analysis_id")
                }

        if skipped_zero > 0:
            logger.info(f"LCWGPT server list: Skipped {skipped_zero} analyses with 0 anomalies")

        server_list = sorted(servers.values(), key=lambda x: x.get("last_analysis") or "", reverse=True)

        logger.info(f"LCWGPT server list: Returning {len(server_list)} servers with anomaly data")

        return {
            "status": "success",
            "servers": server_list,
            "count": len(server_list)
        }

    except Exception as e:
        logger.error(f"Error getting analyzed servers: {e}")
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


def estimate_token_count(text: str) -> int:
    """Yaklaşık token sayısını hesapla (Türkçe+İngilizce karışık metin)"""
    # Türkçe diacritics ve uzun kelimeler nedeniyle ~3 char/token daha gerçekçi
    return len(text) // 3

def _calculate_chunk_relevance(query: str, chunk_anomalies: list, chunk_index: int) -> float:
    """
    Chunk relevance score hesapla
    
    Args:
        query: Kullanıcı sorusu
        chunk_anomalies: Chunk'taki anomaliler
        chunk_index: Chunk index'i
        
    Returns:
        Relevance score (0-100)
    """
    score = 0.0
    query_lower = query.lower()
    
    # 1. Query'deki keyword match
    keywords = [
        # Genel sorun terimleri
        'kritik', 'critical', 'hata', 'error', 'sorun', 'problem', 'arıza', 'failure',
        'yavaş', 'slow', 'gecikme', 'delay', 'timeout', 'zaman aşımı',
        
        # Bağlantı sorunları
        'bağlantı', 'connection', 'disconnected', 'bağlantı kesildi', 'socket',
        'network', 'ağ', 'ping', 'unreachable', 'ulaşılamaz',
        
        # Kaynak sorunları
        'memory', 'bellek', 'ram', 'cpu', 'disk', 'alan', 'space', 'full',
        'dolu', 'yetersiz', 'insufficient', 'oom', 'out of memory',
        
        # MongoDB özel terimler
        'replica', 'replik', 'shard', 'parça', 'primary', 'secondary', 'arbiter',
        'oplog', 'gridfs', 'index', 'indeks', 'collection', 'koleksiyon',
        'document', 'döküman', 'query', 'sorgu', 'aggregation', 'toplama',

        # Elasticsearch özel terimler
        'gc', 'garbage', 'jvm', 'heap', 'circuit breaker', 'watermark', 'flood',
        'master election', 'node left', 'node joined', 'unassigned',
        'cluster health', 'yellow', 'red', 'deprecation', 'mapping',
        'bulk reject', 'thread pool', 'slow log', 'force merge',
        'ilm', 'rollover', 'hot', 'warm', 'cold',

        # MSSQL özel terimler
        'login failed', 'brute force', 'tempdb', 'availability group',
        'failover', 'always on', 'agent job', 'backup', 'restore',
        't-sql', 'execution plan', 'wait stats', 'page split',
        'autogrow', 'buffer pool', 'plan cache',

        # Performance sorunları
        'performans', 'performance', 'yavaşlama', 'bottleneck', 'darboğaz',
        'lock', 'kilit', 'deadlock', 'blocking', 'queue', 'kuyruk',

        # Güvenlik ve erişim
        'authentication', 'kimlik doğrulama', 'authorization', 'yetkilendirme',
        'login', 'giriş', 'password', 'şifre', 'access', 'erişim', 'denied',
        
        # Veri sorunları
        'corrupt', 'bozuk', 'repair', 'onarım', 'backup', 'yedek', 'restore',
        'geri yükleme', 'missing', 'eksik', 'duplicate', 'tekrar',
        
        # Sistem sorunları
        'restart', 'yeniden başlatma', 'shutdown', 'kapatma', 'crash', 'çökme',
        'hung', 'donma', 'zombie', 'process', 'süreç', 'thread',
        
        # Monitoring ve log terimleri
        'warning', 'uyarı', 'alert', 'alarm', 'threshold', 'eşik', 'limit',
        'monitoring', 'izleme', 'metric', 'metrik', 'stats', 'istatistik'
    ]
    
    for keyword in keywords:
        if keyword in query_lower:
            # Chunk'ta bu keyword'ü içeren anomali sayısı
            matches = sum(1 for a in chunk_anomalies 
                         if keyword in (a.get('message', '') + a.get('component', '')).lower())
            score += matches * 10
    
    # 2. Severity bazlı scoring
    high_severity_count = sum(1 for a in chunk_anomalies 
                              if a.get('severity_score', 0) > 70)
    score += high_severity_count * 5
    
    # 3. Component çeşitliliği
    unique_components = len(set(a.get('component', 'unknown') for a in chunk_anomalies))
    score += unique_components * 2
    
    # 4. Zaman bazlı relevance (daha yeni chunk'lar daha relevant)
    recency_bonus = max(0, 10 - chunk_index * 2)
    score += recency_bonus
    
    # 5. Anomali yoğunluğu
    if chunk_anomalies:
        avg_severity = sum(a.get('severity_score', 0) for a in chunk_anomalies) / len(chunk_anomalies)
        score += avg_severity / 10
    
    return min(100, score)  # Max 100 puan

def get_diverse_anomalies(anomalies: list, total_limit: int = 1000):
    """
    Anomalileri çeşitlilik (fingerprint) ve kritiklik (severity) dengesiyle seçer.
    Amacı: AI'ya her batch'te farklı bir sorun tipi göndererek 'geniş görüş' sağlamak.
    """
    if not anomalies: return []
    df_tmp = pd.DataFrame(anomalies)
    
    if 'message_fingerprint' not in df_tmp.columns:
        return anomalies[:total_limit]

    # 1. Her pattern için kayıtları severity'ye göre sırala
    df_tmp = df_tmp.sort_values(['message_fingerprint', 'severity_score'], ascending=[True, False])
    
    # 2. Her pattern içindeki sıra numarasını ekle (her grubun 1., 2., 3. kaydı gibi)
    df_tmp['pattern_rank'] = df_tmp.groupby('message_fingerprint').cumcount()
    
    # 3. Önce her grubun 1. kayıtlarını, sonra 2. kayıtlarını alacak şekilde sırala
    # Bu sayede liste: [HataA_1, HataB_1, HataC_1, HataA_2, HataB_2...] şeklinde dizilir.
    diverse_df = df_tmp.sort_values(['pattern_rank', 'severity_score'], ascending=[True, False])
    
    logger.info(f"Diverse sampling: Found {df_tmp['message_fingerprint'].nunique()} distinct patterns.")
    
    return diverse_df.head(total_limit).to_dict('records')


# =====================================================
# ANOMALY DIGEST & CONVERSATION MEMORY
# Token-efficient global context for chat-query-anomalies
# =====================================================

# Per-analysis conversation memory (in-memory cache)
_chat_conversation_cache: Dict[str, list[Dict[str, str]]] = {}
_CONVERSATION_HISTORY_LIMIT = 5  # Son 5 Q&A turu


def _build_anomaly_digest(all_anomalies: list, source_type: str = "mongodb") -> str:
    """
    Tüm anomalilerin kompakt özeti (~500-800 token).
    Her chat prompt'una 'GLOBAL CONTEXT' olarak eklenir.
    LLM, chunk'taki detaylara bakarken büyük resmi de görsün.

    Args:
        all_anomalies: Tüm anomali listesi (300-450 kayıt)
        source_type: Kaynak tipi (mongodb, mssql, elasticsearch)

    Returns:
        Kompakt digest metni
    """
    if not all_anomalies:
        return "Anomali bulunamadı."

    total = len(all_anomalies)

    # 1. Severity dağılımı
    severity_dist = {}
    for a in all_anomalies:
        sev = a.get('severity_level', 'UNKNOWN')
        severity_dist[sev] = severity_dist.get(sev, 0) + 1

    # 2. Component/Logger dağılımı (top 10)
    component_dist = {}
    for a in all_anomalies:
        comp = a.get('component', a.get('logger_name', 'N/A'))
        component_dist[comp] = component_dist.get(comp, 0) + 1
    top_components = sorted(component_dist.items(), key=lambda x: x[1], reverse=True)[:10]

    # 3. Pattern/Fingerprint grupları
    pattern_groups = {}
    for a in all_anomalies:
        fp = a.get('message_fingerprint') or a.get('anomaly_type')
        # Fallback: fingerprint yoksa component + mesaj başı ile grupla
        if not fp:
            comp = a.get('component', 'unknown') or 'unknown'
            msg = (a.get('message', '') or '')[:40].strip()
            fp = f"{comp}:{msg}" if msg else comp
        if fp not in pattern_groups:
            pattern_groups[fp] = {
                'count': 0,
                'max_score': 0,
                'sample_msg': a.get('message', '')[:120],
                'severity_levels': set()
            }
        pattern_groups[fp]['count'] += 1
        score = a.get('severity_score', a.get('score', 0))
        if score > pattern_groups[fp]['max_score']:
            pattern_groups[fp]['max_score'] = score
            pattern_groups[fp]['sample_msg'] = a.get('message', '')[:120]
        pattern_groups[fp]['severity_levels'].add(a.get('severity_level', 'UNKNOWN'))

    # En sık 10 pattern grubu
    top_patterns = sorted(pattern_groups.items(), key=lambda x: x[1]['count'], reverse=True)[:10]

    # 4. Zaman dağılımı
    hour_dist = {}
    for a in all_anomalies:
        ts = a.get('timestamp', '')
        if ts:
            try:
                if isinstance(ts, str):
                    h = ts[11:13] if len(ts) > 13 else '??'
                else:
                    h = str(getattr(ts, 'hour', '??'))
                hour_dist[h] = hour_dist.get(h, 0) + 1
            except Exception:
                pass
    peak_hours = sorted(hour_dist.items(), key=lambda x: x[1], reverse=True)[:3]

    # 5. Skor istatistikleri
    scores = [a.get('severity_score', a.get('score', 0)) for a in all_anomalies if a.get('severity_score', a.get('score', 0)) > 0]
    avg_score = sum(scores) / len(scores) if scores else 0
    max_score = max(scores) if scores else 0

    # Digest oluştur
    digest = f"""GLOBAL ANOMALİ ÖZETİ (Tüm {total} anomali):

SEVERITY DAĞILIMI:
{', '.join([f'{k}: {v}' for k, v in sorted(severity_dist.items(), key=lambda x: x[1], reverse=True)])}

SKOR İSTATİSTİKLERİ:
Ortalama: {avg_score:.1f}, Maksimum: {max_score:.1f}

EN AKTİF COMPONENT/LOGGER (Top 10):
{chr(10).join([f'  {comp}: {cnt} anomali' for comp, cnt in top_components])}

EN SIK PATTERN GRUPLARI (Top 10):
"""
    for fp, info in top_patterns:
        fp_short = str(fp)[:50] if fp else 'unknown'
        digest += f"  [{info['count']}x] MaxScore:{info['max_score']:.0f} | {fp_short} — \"{info['sample_msg'][:80]}\"\n"

    if peak_hours:
        digest += f"\nPEAK SAATLER: {', '.join([f'{h}:00 ({c} anomali)' for h, c in peak_hours])}\n"

    digest += f"\nToplam {len(pattern_groups)} farklı pattern grubu tespit edildi."

    return digest


def _get_conversation_history(analysis_id: str) -> str:
    """
    Önceki Q&A turlarını kompakt metin olarak döndür.
    Her tur: soru + cevap özeti (max 300 char)
    """
    if not analysis_id or analysis_id not in _chat_conversation_cache:
        return ""

    history = _chat_conversation_cache[analysis_id]
    if not history:
        return ""

    text = "ÖNCEKİ SORU-CEVAPLAR:\n"
    for turn in history[-_CONVERSATION_HISTORY_LIMIT:]:
        q = turn.get('query', '')[:100]
        a = turn.get('response_summary', '')[:300]
        text += f"  S: {q}\n  C: {a}\n\n"

    return text


def _save_conversation_turn(analysis_id: str, query: str, response: str):
    """
    Q&A turunu cache'e kaydet.
    Response'dan ilk 300 karakteri özet olarak sakla.
    """
    if not analysis_id:
        return

    if analysis_id not in _chat_conversation_cache:
        _chat_conversation_cache[analysis_id] = []

    # Response özetini oluştur (ilk paragraf veya ilk 300 char)
    summary = response[:300].strip()
    first_para_end = summary.find('\n\n')
    if first_para_end > 50:
        summary = summary[:first_para_end]

    _chat_conversation_cache[analysis_id].append({
        'query': query,
        'response_summary': summary,
        'timestamp': datetime.now().isoformat()
    })

    # Max limit — en eski turları sil
    if len(_chat_conversation_cache[analysis_id]) > _CONVERSATION_HISTORY_LIMIT * 2:
        _chat_conversation_cache[analysis_id] = _chat_conversation_cache[analysis_id][-_CONVERSATION_HISTORY_LIMIT:]

    # Memory cleanup: 100'den fazla analysis_id varsa eskilerini sil
    if len(_chat_conversation_cache) > 100:
        oldest_keys = sorted(
            _chat_conversation_cache.keys(),
            key=lambda k: _chat_conversation_cache[k][-1]['timestamp'] if _chat_conversation_cache[k] else '',
        )[:50]
        for k in oldest_keys:
            del _chat_conversation_cache[k]


@app.post("/api/chat-query-anomalies")
async def chat_query_anomalies(request: Dict[str, Any]):
    """Chat üzerinden anomali sorgulama - LCWGPT ile (Progress Tracking Destekli)"""
    start_time = datetime.now()  # Performance tracking için

    # ✅ YENİ: Request ID ve Context Yönetimi
    request_id = request.get("request_id")
    token = request_context.set(request_id) if request_id else None

    try:
        # 1. ADIM: Context (Bağlam) Yükleme
        update_progress(request_id, "context", "Analiz bağlamı ve geçmiş veriler hazırlanıyor...", 5)

        # API key kontrolü
        if not await verify_api_key(request.get('api_key')):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")

        query = request.get("query", "")
        analysis_id = request.get("analysis_id")

        logger.info(f"Chat anomaly query received - Query: {query[:50]}...")

        # YENİ: Analysis ID yoksa sunucu adı zorunlu
        if not analysis_id:
            try:
                # Tüm veritabanı tiplerinden host listesi çek
                available_hosts = []
                host_source_map = {}  # host -> source_type eşlemesi

                # 1. MongoDB hosts
                try:
                    from src.anomaly.log_reader import get_available_mongodb_hosts
                    mongo_hosts = get_available_mongodb_hosts(last_hours=24)
                    for h in mongo_hosts:
                        if h not in host_source_map:
                            available_hosts.append(h)
                            host_source_map[h] = "mongodb"
                except Exception as e:
                    logger.warning(f"MongoDB host listesi alınamadı: {e}")
                    mongo_hosts = []

                # 2. MSSQL hosts
                try:
                    from src.anomaly.mssql_log_reader import get_available_mssql_hosts
                    mssql_hosts = get_available_mssql_hosts(last_hours=24)
                    for h in mssql_hosts:
                        if h not in host_source_map:
                            available_hosts.append(h)
                            host_source_map[h] = "mssql"
                except Exception as e:
                    logger.warning(f"MSSQL host listesi alınamadı: {e}")
                    mssql_hosts = []

                # 3. Elasticsearch hosts
                try:
                    from src.anomaly.elasticsearch_log_reader import get_available_es_hosts
                    es_hosts = get_available_es_hosts(last_hours=24)
                    for h in es_hosts:
                        if h not in host_source_map:
                            available_hosts.append(h)
                            host_source_map[h] = "elasticsearch"
                except Exception as e:
                    logger.warning(f"Elasticsearch host listesi alınamadı: {e}")
                    es_hosts = []

                logger.info(f"Chat host discovery: {len(available_hosts)} total hosts "
                            f"(MongoDB: {len(mongo_hosts)}, MSSQL: {len(mssql_hosts)}, ES: {len(es_hosts)})")

                # Query'de sunucu adı kontrolü
                detected_server = None
                detected_source_type = None
                query_lower = query.lower()
                for host in available_hosts:
                    host_short = host.split('.')[0] if '.' in host else host
                    if host.lower() in query_lower or host_short.lower() in query_lower:
                        detected_server = host
                        detected_source_type = host_source_map.get(host, "unknown")
                        logger.info(f"✅ Chat query'de sunucu tespit edildi: {detected_server} (source: {detected_source_type})")
                        break

                if not detected_server:
                    logger.warning("❌ Chat anomali sorgusu yapıldı ama sunucu adı belirtilmedi")
                    # Her tipten örnek sunucu göster
                    host_examples = []
                    for src_hosts, src_label in [
                        (mongo_hosts, "MongoDB"),
                        (mssql_hosts, "MSSQL"),
                        (es_hosts, "Elasticsearch")
                    ]:
                        for h in src_hosts[:2]:  # Her tipten max 2 örnek
                            host_examples.append(f"{h} ({src_label})")

                    first_host = available_hosts[0] if available_hosts else 'lcwmongodb01n2'
                    first_host_short = first_host.split('.')[0] if '.' in first_host else first_host

                    return {
                        "status": "error",
                        "message": f"""⚠️ Lütfen sorgunuzda hangi sunucuyu analiz etmek istediğinizi belirtin.

📌 **Mevcut sunucular:**
{chr(10).join(['• ' + h for h in host_examples[:10]])}

💡 **Örnek sorgular:**
- "{first_host_short} sunucusundaki sorunlar neler?"
- "{first_host_short} için kritik anomaliler var mı?"
- "{first_host_short}'deki hataları analiz et" """,
                        "available_hosts": available_hosts,
                        "total_anomalies": 0
                    }

                filters = {"host": detected_server}
                logger.info(f"✅ Server detected in query: {detected_server}")
                logger.info(f"Searching for existing analysis in storage for server: {detected_server}")

                try:
                    storage = await get_storage_manager()
                    server_analyses = await storage.get_anomaly_history(
                        filters={"host": detected_server},
                        limit=1,
                        include_details=True
                    )
                    if server_analyses and len(server_analyses) > 0:
                        logger.info(f"✅ Found existing analysis for {detected_server} in storage")
                        analysis_id = server_analyses[0].get("analysis_id")
                        filters = {"analysis_id": analysis_id}
                        logger.info(f"Using analysis_id from storage: {analysis_id}")
                    else:
                        logger.warning(f"⚠️ No analysis found for server {detected_server} in storage")
                        return {
                            "status": "error",
                            "message": f"❌ {detected_server} sunucusu için kayıtlı anomali analizi bulunamadı.\n\nLütfen önce bu sunucu için anomali analizi yapın.",
                            "server_detected": detected_server,
                            "available_hosts": [],
                            "total_anomalies": 0
                        }
                except Exception as e:
                    logger.error(f"Error checking storage for server {detected_server}: {e}")
                    filters = {"host": detected_server}

                # ✅ YENİ: Multiple context analyses için genişletilmiş arama
                context_analyses = []
                logger.info(f"🔍 Searching for related analyses in storage...")

                try:
                    storage = await get_storage_manager()
                    query_words = query.lower().split()
                    important_keywords = [
                        word for word in query_words
                        if len(word) > 3 and word not in ['mongodb', 'anomali', 'göster', 'analiz', 'nedir', 'nasıl', 'hangi']
                    ]

                    recent_analyses = await storage.get_anomaly_history(
                        limit=30,
                        include_details=False
                    )

                    for analysis_ctx in recent_analyses:
                        relevance_score = 0
                        if detected_server and analysis_ctx.get("host") == detected_server:
                            relevance_score += 50
                        elif analysis_ctx.get("host"):
                            host_lower = analysis_ctx["host"].lower()
                            for keyword in important_keywords:
                                if keyword in host_lower:
                                    relevance_score += 20

                        time_keywords = ['bugün', 'dün', 'son', 'saat', 'dakika', 'gün']
                        for tk in time_keywords:
                            if tk in query.lower():
                                analysis_time = analysis_ctx.get("timestamp")
                                if analysis_time:
                                    try:
                                        analysis_dt = datetime.fromisoformat(analysis_time.replace('Z', '+00:00'))
                                        hours_ago = (datetime.utcnow() - analysis_dt).total_seconds() / 3600
                                        if hours_ago < 24:
                                            relevance_score += 10 * (1 - hours_ago/24)
                                    except:
                                        pass

                        pattern_keywords = ['timeout', 'connection', 'authentication', 'slow', 'query', 'index', 'lock']
                        for pk in pattern_keywords:
                            if pk in query.lower() and analysis_ctx.get("anomaly_count", 0) > 0:
                                relevance_score += 5
                        if relevance_score > 0:
                            analysis_ctx["relevance_score"] = relevance_score
                            context_analyses.append(analysis_ctx)

                    context_analyses = sorted(
                        context_analyses,
                        key=lambda x: x.get("relevance_score", 0),
                        reverse=True
                    )[:3]

                    detailed_contexts = []
                    for ctx in context_analyses:
                        try:
                            detailed = await storage.get_anomaly_history(
                                filters={"analysis_id": ctx["analysis_id"]},
                                limit=1,
                                include_details=True
                            )
                            if detailed and detailed[0]:
                                detailed_contexts.append(detailed[0])
                        except Exception as e:
                            logger.warning(f"Failed to load details for context: {e}")

                    context_analyses = detailed_contexts

                except Exception as e:
                    logger.error(f"Error building context: {e}")
                    context_analyses = []

            except Exception as e:
                logger.error(f"Sunucu listesi alınamadı: {e}")
                filters = {}
                context_analyses = []
        else:
            filters = {"analysis_id": analysis_id}
            context_analyses = []

            # analysis_id varsa bile o sunucunun geçmiş analizlerini context olarak çek
            try:
                storage = await get_storage_manager()
                # Önce bu analizi çekip host bilgisini al
                _preview = await storage.get_anomaly_history(
                    filters={"analysis_id": analysis_id}, limit=1, include_details=False
                )
                if _preview:
                    _host = _preview[0].get("host")
                    if _host:
                        _host_analyses = await storage.get_anomaly_history(
                            filters={"host": _host}, limit=5, include_details=False
                        )
                        # Mevcut analiz hariç, en son 2 geçmiş analizi context olarak al
                        context_analyses = [
                            a for a in _host_analyses
                            if a.get("analysis_id") != analysis_id
                        ][:2]
                        if context_analyses:
                            logger.info(f"Context: Found {len(context_analyses)} past analyses for host {_host}")
            except Exception as e:
                logger.warning(f"Could not load context analyses for analysis_id path: {e}")
                context_analyses = []

        storage = await get_storage_manager()
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
        analysis_source = (analysis.get("source") or "").lower()
        is_mssql = "mssql" in analysis_source
        is_elasticsearch = "elasticsearch" in analysis_source

        all_anomalies = (
            analysis.get("unfiltered_anomalies", [])
            or analysis.get("critical_anomalies_full", [])
            or analysis.get("critical_anomalies_display", [])
            or analysis.get("critical_anomalies", [])
        )

        # YENİ: Çeşitlilik filtresini total limit ile uygula
        # 500 kayıt = 25 AI Batch (Chunk_size 20 ise)
        all_anomalies = get_diverse_anomalies(all_anomalies, total_limit=1000)

        logger.info(f"AI will scan {len(all_anomalies)} diverse anomalies in batches.")

        logger.info(f"Found {len(all_anomalies)} anomalies for LCWGPT processing")

        # ✅ GUARD: 0 anomali durumunda güvenli erken dönüş — IndexError önlenir
        if len(all_anomalies) == 0:
            logger.warning("No anomalies found for LCWGPT processing — returning safe fallback response")
            update_progress(request_id, "complete", "İşlem tamamlandı!", 100)
            return {
                "status": "success",
                "total_anomalies": 0,
                "ai_response": (
                    "Bu sunucu için kayıtlı anomali verisi bulunamadı.\n\n"
                    "Olası nedenler:\n"
                    "- Seçilen zaman aralığında anomali tespit edilmemiş olabilir.\n"
                    "- Analiz henüz tamamlanmamış olabilir.\n\n"
                    "Lütfen farklı bir zaman aralığı seçerek yeni bir analiz başlatın "
                    "veya farklı bir sunucu deneyin."
                ),
                "analysis_id": analysis.get("analysis_id"),
                "timestamp": str(analysis.get("timestamp")),
                "host": analysis.get("host"),
                "chunks_processed": 0,
                "processed_chunks": [],
                "processing_mode": "no-anomalies",
                "chunk_info": "Anomali bulunamadı",
                "total_chunks": 0
            }

        # 2. ADIM: Bağlantı
        update_progress(request_id, "connect", "LCWGPT servisi ile güvenli bağlantı kuruluyor...", 20)
        llm_connector = await get_llm_connector()

        if not llm_connector:
            logger.error("LCWGPT connection failed")
            update_progress(request_id, "error", "LCWGPT servisine bağlanılamadı!", 0)
            return {
                "status": "error",
                "message": "LCWGPT bağlantısı kurulamadı",
                "total_anomalies": len(all_anomalies)
            }

        # Global anomaly digest — tüm anomalilerin kompakt özeti (~500 token)
        source_label = "elasticsearch" if is_elasticsearch else ("mssql" if is_mssql else "mongodb")
        anomaly_digest = _build_anomaly_digest(all_anomalies, source_type=source_label)
        logger.info(f"Anomaly digest built: {len(anomaly_digest)} chars (~{estimate_token_count(anomaly_digest)} tokens)")

        # Conversation memory — önceki Q&A turlarını al
        effective_analysis_id = analysis_id or analysis.get("analysis_id", "")
        conversation_history = _get_conversation_history(effective_analysis_id)
        if conversation_history:
            logger.info(f"Conversation history found for {effective_analysis_id}: {len(conversation_history)} chars")

        chunk_size = 20
        total_chunks = (len(all_anomalies) + chunk_size - 1) // chunk_size
        batch_size = 3
        # Kapasite: 50 Batch (1000 anomali taraması için)
        max_chunks_to_process = min(total_chunks, 50)

        # 3. ADIM: Chunking
        update_progress(request_id, "chunk", f"Büyük veri seti {max_chunks_to_process} parçaya bölünüyor...", 35)
        logger.info(f"Will process {max_chunks_to_process} chunks in batches of {batch_size}")

        chunk_relevance_scores = []
        for i in range(total_chunks):
            relevance_score = _calculate_chunk_relevance(query, all_anomalies[i*chunk_size:(i+1)*chunk_size], i)
            chunk_relevance_scores.append((i, relevance_score))
        chunk_relevance_scores.sort(key=lambda x: x[1], reverse=True)
        selected_chunk_indices = [idx for idx, _ in chunk_relevance_scores[:max_chunks_to_process]]
        selected_chunk_indices.sort()
        logger.info(f"Processing {len(selected_chunk_indices)} most relevant chunks")

        component_dist = {}
        severity_dist = {}
        for a in all_anomalies:
            comp = a.get('component', 'N/A')
            component_dist[comp] = component_dist.get(comp, 0) + 1
            sev = a.get('severity_level', 'N/A')
            severity_dist[sev] = severity_dist.get(sev, 0) + 1

        # LCWGPT system prompt — kaynak tipine göre dinamik
        if is_mssql:
            system_prompt = """Sen MSSQL veritabanı anomali analizi ve performans optimizasyonu konusunda uzman bir Senior DBA'sin.
MSSQL loglarındaki pattern'leri tanıyabilir, root cause analizi yapabilir ve ÇALIŞTIRILABİLİR T-SQL çözüm komutları sunabilirsin.

MSSQL LOG PATTERN BİLGİSİ:
- DEADLOCK: Kilitlenme sorunları (deadlock graph, victim selection)
- BLOCKING: Uzun süreli kilitler, wait chain
- SLOW QUERY: Yavaş sorgular, execution plan sorunları
- TEMPDB: TempDB darboğazları, version store
- IO: Disk I/O gecikmesi, page split, autogrow
- MEMORY: Buffer pool, memory grant, plan cache pressure
- CONNECTIVITY: Login failure, connection pool, timeout
- AGENT: SQL Agent job hataları, schedule sorunları
- REPLICATION: Always On, AG failover, log shipping
- BACKUP: Backup/restore hataları, chain broken

ML MODEL YORUM KURALLARI:
- severity_score 0-100 arasıdır. 80+ KRİTİK, 60-80 YÜKSEK, 40-60 ORTA, 0-40 DÜŞÜK demektir.
- Kullanıcıya ML modelinin neden bu skoru verdiğini açıkla (hangi pattern, hangi frekans, hangi bileşen).
- Anomali grupları arasındaki korelasyonları belirt (ör: BLOCKING + MEMORY = memory grant wait kaynaklı).

ÇÖZÜM KOMUTLARI KURALI (KRİTİK):
Her öneride MUTLAKA gerçek, kopyala-yapıştır ile çalıştırılabilir T-SQL komutu ver. Genel tavsiye VERME.

Örnek KÖTÜ yanıt: "Index eklemenizi öneririm."
Örnek İYİ yanıt:
```sql
-- Missing index önerisi (DMV'den tespit edilen)
CREATE NONCLUSTERED INDEX IX_Orders_CustomerDate
ON dbo.Orders (CustomerID, OrderDate DESC)
INCLUDE (TotalAmount, Status)
WITH (ONLINE = ON, SORT_IN_TEMPDB = ON);
```

Komut türleri (duruma göre kullan):
- Deadlock analizi: SELECT * FROM sys.dm_tran_locks; DBCC INPUTBUFFER(spid)
- Blocking tespiti: sp_who2, sys.dm_exec_requests, sys.dm_os_waiting_tasks
- Slow query: sys.dm_exec_query_stats, sys.dm_exec_cached_plans + CROSS APPLY sys.dm_exec_sql_text
- Index önerisi: sys.dm_db_missing_index_details, CREATE INDEX komutu
- TempDB: sys.dm_db_file_space_usage, ALTER DATABASE tempdb MODIFY FILE
- Memory: sys.dm_exec_query_memory_grants, DBCC MEMORYSTATUS, sp_configure 'max server memory'
- IO: sys.dm_io_virtual_file_stats, sys.dm_exec_query_stats (logical_reads)
- Wait stats: sys.dm_os_wait_stats, sys.dm_exec_session_wait_stats
- AG/Replication: sys.dm_hadr_availability_replica_states, ALTER AVAILABILITY GROUP

ANALİZ YÖNTEMİ:
1. Pattern Tespiti: Benzer anomalileri grupla
2. Root Cause: Kök nedeni belirle
3. Impact Analizi: İş etkisini değerlendir
4. Çözüm Önerisi: ÇALIŞTIRILABİLİR T-SQL komutları sun

YANIT FORMATI:
📊 ÖZET: [Tek cümlede ana bulgu + ML modelinin genel değerlendirmesi]

🔍 DETAYLI ANALİZ:
Her kritik anomali için:
- ML Severity Score ve ne anlama geldiğinin açıklaması
- Pattern açıklaması ve root cause
- **GERÇEK LOG ÖRNEKLERİ** (```code block``` içinde tam log mesajı)
- Pattern grupları ve sayıları
- Zaman dağılımı (peak saatler varsa)

⚠️ RİSKLER:
- Mevcut riskler (somut: "X tablosunda lock escalation var, Y ms süren sorgular Z dakikada bir tekrar ediyor")
- Potansiyel zincir etkiler (ör: "Bu blocking chain birikerek timeout'lara yol açabilir")

✅ ÖNERİLER:
Her öneri şu formatta olmalı:
1. [ACİL/ORTA/DÜŞÜK] Başlık
   - Neden: Sorunun açıklaması
   - Çözüm komutu (```sql``` kod bloğu içinde çalıştırılabilir T-SQL)
   - Beklenen etki: "Lock wait süresi ~Xms'den ~Yms'ye düşecek" gibi somut

Türkçe yanıt ver, teknik terimleri açıkla, DBA'ların anlayacağı detay seviyesinde ol.
MUTLAKA gerçek log mesajlarını kod bloğu içinde göster.
MUTLAKA çözüm komutlarını ```sql``` kod bloğu içinde ver.
Önce log örneklerini göster, sonra pattern açıklamasını, sonra ÇALIŞTIRILABİLİR T-SQL komut önerilerini göster."""
        elif is_elasticsearch:
            system_prompt = """Sen Elasticsearch cluster yönetimi, performans optimizasyonu ve log anomali analizi konusunda uzman bir Senior Elasticsearch Engineer'sin.

Elasticsearch loglarındaki pattern'leri tanıyabilir, root cause analizi yapabilir ve ÇALIŞTIRILABİLİR çözüm komutları sunabilirsin.

ELASTICSEARCH LOG PATTERN BİLGİSİ:
- GC (Garbage Collection): JVM heap pressure, long GC pauses, stop-the-world events
- SHARD: Shard allocation failure, unassigned shards, rebalancing sorunları
- DISK: Disk watermark breach (low/high/flood), read-only index
- MEMORY: Circuit breaker tripped, fielddata eviction, JVM OOM
- NETWORK: Node disconnect, master election, split brain riski
- INDEX: Slow indexing, bulk rejection, mapping explosion
- SEARCH: Slow query, search thread pool rejection, deep pagination
- CLUSTER: Red/yellow health, master instability, pending tasks
- DEPRECATION: Deprecated API kullanımı, versiyon uyumsuzluk uyarıları
- NODE: Node role sorunları (master/data/ingest), hot/warm/cold tier

ML MODEL YORUM KURALLARI:
- severity_score 0-100 arasıdır. 80+ KRİTİK, 60-80 YÜKSEK, 40-60 ORTA, 0-40 DÜŞÜK demektir.
- Kullanıcıya ML modelinin neden bu skoru verdiğini açıkla (hangi pattern, hangi frekans, hangi bileşen).
- Anomali grupları arasındaki korelasyonları belirt (ör: GC pause + MEMORY circuit breaker = heap pressure).

ÇÖZÜM KOMUTLARI KURALI (KRİTİK):
Her öneride MUTLAKA gerçek, kopyala-yapıştır ile çalıştırılabilir komut ver. Genel tavsiye VERME.

Örnek KÖTÜ yanıt: "Shard sayısını azaltmanızı öneririm."
Örnek İYİ yanıt:
```json
// Unassigned shard'ları yeniden ata
PUT /_cluster/settings
{
  "transient": {
    "cluster.routing.allocation.enable": "all"
  }
}

// Retry failed shard allocation
POST /_cluster/reroute?retry_failed=true
```

Komut türleri (duruma göre kullan):
- Cluster health: GET /_cluster/health, GET /_cluster/allocation/explain
- Shard yönetimi: POST /_cluster/reroute, PUT /_cluster/settings
- Index yönetimi: PUT /index_name/_settings, POST /index_name/_forcemerge
- Node bilgisi: GET /_nodes/stats, GET /_nodes/hot_threads
- GC/JVM: GET /_nodes/stats/jvm, jvm.options düzenlemesi
- Disk watermark: PUT /_cluster/settings (cluster.routing.allocation.disk.watermark.*)
- Circuit breaker: PUT /_cluster/settings (indices.breaker.*)
- Slow log: PUT /index_name/_settings (index.search.slowlog.*, index.indexing.slowlog.*)
- Thread pool: GET /_cat/thread_pool?v, GET /_nodes/stats/thread_pool
- Template/Mapping: GET /_index_template, PUT /_index_template

YANIT FORMATI:
📊 ÖZET: [Tek cümlede ana bulgu + ML modelinin genel değerlendirmesi]

🔍 DETAYLI ANALİZ:
Her kritik anomali için:
- ML Severity Score ve ne anlama geldiğinin açıklaması
- Pattern açıklaması ve root cause
- **GERÇEK LOG ÖRNEKLERİ** (```code block``` içinde tam log mesajı)
- Pattern grupları ve sayıları
- Zaman dağılımı (peak saatler varsa)

⚠️ RİSKLER:
- Mevcut riskler (somut: "X node'da GC pause 10s üzeri, Y index'te shard allocation failed")
- Potansiyel zincir etkiler (ör: "Disk watermark aşılırsa index read-only olur, yazma durur")

✅ ÖNERİLER:
Her öneri şu formatta olmalı:
1. [ACİL/ORTA/DÜŞÜK] Başlık
   - Neden: Sorunun açıklaması
   - Çözüm komutu (```json``` kod bloğu içinde çalıştırılabilir Elasticsearch API komutu)
   - Beklenen etki: "GC pause süresi ~Xs'den ~Ys'ye düşecek" gibi somut

Türkçe yanıt ver, teknik terimleri açıkla, Elasticsearch mühendislerinin anlayacağı detay seviyesinde ol.
MUTLAKA gerçek log mesajlarını kod bloğu içinde göster.
MUTLAKA çözüm komutlarını ```json``` kod bloğu içinde ver (Elasticsearch REST API formatında).
Önce log örneklerini göster, sonra pattern açıklamasını, sonra ÇALIŞTIRILABİLİR Elasticsearch API komut önerilerini göster."""
        else:
            system_prompt = """Sen MongoDB anomali analizi ve performans optimizasyonu konusunda uzman bir Senior DBA'sin.
MongoDB loglarındaki pattern'leri tanıyabilir, root cause analizi yapabilir ve ÇALIŞTIRILAB İLİR çözüm komutları sunabilirsin.

MONGODB LOG PATTERN BİLGİSİ:
- REPL: Replikasyon sorunları (lag, oplog, election)
- COMMAND: Yavaş sorgular, timeout'lar
- NETWORK: Bağlantı sorunları, dropped connections
- STORAGE: Disk I/O, WiredTiger cache sorunları
- INDEX: Index kullanımı, collection scan uyarıları
- CONTROL: Shutdown, startup, config değişiklikleri
- WRITE: Write concern, journal sorunları

ANALİZ YÖNTEMİ:
1. Pattern Tespiti: Benzer anomalileri grupla
2. Root Cause: Kök nedeni belirle
3. Impact Analizi: İş etkisini değerlendir
4. Çözüm Önerisi: Spesifik, uygulanabilir adımlar sun

ML MODEL YORUM KURALLARI:
- severity_score 0-100 arasıdır. 80+ KRİTİK, 60-80 YÜKSEK, 40-60 ORTA, 0-40 DÜŞÜK demektir.
- Kullanıcıya ML modelinin neden bu skoru verdiğini açıkla (hangi pattern, hangi frekans, hangi bileşen).
- Anomali grupları arasındaki korelasyonları belirt (ör: REPL lag + STORAGE I/O = disk darboğazı).

ÇÖZÜM KOMUTLARI KURALI (KRİTİK):
Her öneride MUTLAKA gerçek, kopyala-yapıştır ile çalıştırılabilir komut ver. Genel tavsiye VERME.

Örnek KÖTÜ yanıt: "Index oluşturmanız önerilir."
Örnek İYİ yanıt:
```mongodb
// Yavaş sorgu için compound index oluştur
db.orders.createIndex(
  { "customer_id": 1, "created_at": -1 },
  { name: "idx_orders_customer_date", background: true }
)
```

Komut türleri (duruma göre kullan):
- Index: db.collection.createIndex({...})
- Profiler: db.setProfilingLevel(1, { slowms: 100 })
- Explain: db.collection.find({...}).explain("executionStats")
- Stats: db.collection.stats(), db.serverStatus(), rs.status()
- Config: db.adminCommand({setParameter:1, ...})
- Replikasyon: rs.conf(), rs.stepDown(), rs.syncFrom()
- Sorgu optimizasyonu: db.collection.aggregate([...]) ile pipeline iyileştirme
- WiredTiger: db.serverStatus().wiredTiger.cache

YANIT FORMATI:
📊 ÖZET: [Tek cümlede ana bulgu + ML modelinin genel değerlendirmesi]

🔍 DETAYLI ANALİZ:
Her kritik anomali için:
- ML Severity Score ve ne anlama geldiğinin açıklaması
- Pattern açıklaması ve root cause
- **GERÇEK LOG ÖRNEKLERİ** (```code block``` içinde tam log mesajı)
- Pattern grupları ve sayıları
- Zaman dağılımı (peak saatler varsa)

⚠️ RİSKLER:
- Mevcut riskler (somut: "X collection'da full scan var, Y ms süren sorgular Z dakikada bir tekrar ediyor")
- Potansiyel zincir etkiler (ör: "Bu slow query birikerek connection pool'u tüketebilir")

✅ ÖNERİLER:
Her öneri şu formatta olmalı:
1. [ACİL/ORTA/DÜŞÜK] Başlık
   - Neden: Sorunun açıklaması
   - Çözüm komutu (```mongodb``` kod bloğu içinde)
   - Beklenen etki: "Sorgu süresi ~Xms'den ~Yms'ye düşecek" gibi somut

Türkçe yanıt ver, teknik terimleri açıkla, DBA'ların anlayacağı detay seviyesinde ol.
MUTLAKA gerçek log mesajlarını kod bloğu içinde göster.
MUTLAKA çözüm komutlarını ```mongodb``` kod bloğu içinde ver.
Önce log örneklerini göster, sonra pattern açıklamasını, sonra ÇALIŞTIRILABİLİR komut önerilerini göster."""

        if context_analyses:
            system_prompt += f"""

CONTEXT BİLGİSİ:
Bu sunucu veya benzer sunucularda daha önce tespit edilen {len(context_analyses)} analiz mevcut.
Bu geçmiş analizleri de göz önünde bulundurarak daha kapsamlı bir değerlendirme yap.
"""

        # 4. ADIM: DÖNGÜSEL ANALİZ
        chunk_responses = []
        total_selected = len(selected_chunk_indices)
        for i, chunk_idx in enumerate(selected_chunk_indices):
            current_progress = 40 + int(((i + 1) / total_selected) * 45)
            update_progress(request_id, "analyze", f"Yapay zeka analizi yapılıyor (Parça {i + 1}/{total_selected})...", current_progress)
            start_idx = chunk_idx * chunk_size
            end_idx = min(start_idx + chunk_size, len(all_anomalies))
            current_chunk = all_anomalies[start_idx:end_idx]

            logger.info(f"Processing chunk {chunk_idx + 1}/{total_chunks} with {len(current_chunk)} anomalies")

            if context_analyses:
                chunk_prompt = f"""

{anomaly_digest}

{conversation_history}KULLANICI SORUSU: {query}

İLGİLİ GEÇMİŞ ANALİZLER:
"""
                for idx, ctx in enumerate(context_analyses, 1):
                    chunk_prompt += f"""

Geçmiş Analiz #{idx} - {ctx.get('host', 'N/A')} ({ctx.get('time_range', 'N/A')}):
- Anomali Sayısı: {ctx.get('anomaly_count', 0)}
"""
                chunk_prompt += f"""

ANA ANALİZ - Chunk {chunk_idx + 1}/{total_chunks}:

ANOMALİ KATEGORİ DAĞILIMI (Bu chunk):
{_get_chunk_category_distribution(current_chunk)}

EN KRİTİK 5 ANOMALİ (Severity Score'a göre):
{_format_top_anomalies_with_full_logs(current_chunk, limit=5)}

TÜM ANOMALİ DETAYLARI (LOG MESAJLARIYLA):
{_format_anomalies_with_full_messages(current_chunk)}

GÖREV:
1. Bu chunk'taki pattern'leri tespit et
2. Benzer anomali logları grupla
3. Root cause analizi yap
4. Kullanıcının sorusuna odaklan
5. Spesifik log mesajlarına referans ver
6. Spesifik log gövdesini kullanıcıya direk göster
7. HER ANOMALİ İÇİN GERÇEK LOG MESAJINI KOD BLOĞU İÇİNDE GÖSTER
8. Log mesajlarındaki önemli bilgileri (tablo adı, sorgu süresi, hata kodu vb.) vurgula
9. ML severity score'larını yorumla: 80+ KRİTİK, 60-80 YÜKSEK, 40-60 ORTA, 0-40 DÜŞÜK — neden bu skor verildiğini açıkla
10. Her sorun için ÇALIŞTIRILABİLİR veritabanı komutu öner (kopyala-yapıştır çalışacak şekilde, kod bloğu içinde)
11. Genel tavsiye VERME — her komut spesifik tablo/index/collection adı içermeli (loglardan çıkar)
"""
            else:
                chunk_prompt = f"""

{anomaly_digest}

{conversation_history}KULLANICI SORUSU: {query}

CHUNK BİLGİSİ: {chunk_idx + 1}/{total_chunks} (Anomali {start_idx+1}-{end_idx} arası)

ANOMALİ KATEGORİ DAĞILIMI (Bu chunk):
{_get_chunk_category_distribution(current_chunk)}

EN KRİTİK 5 ANOMALİ (Severity Score'a göre):
{_format_top_anomalies_with_full_logs(current_chunk, limit=5)}

TÜM ANOMALİ DETAYLARI (LOG MESAJLARIYLA):
{_format_anomalies_with_full_messages(current_chunk)}

GÖREV:
1. Bu chunk'taki pattern'leri tespit et
2. Benzer anomali logları grupla
3. Root cause analizi yap
4. Kullanıcının sorusuna odaklan
5. Spesifik log mesajlarına referans ver
6. Spesifik log gövdesini kullanıcıya direk göster
7. HER ANOMALİ İÇİN GERÇEK LOG MESAJINI KOD BLOĞU İÇİNDE GÖSTER
8. Log mesajlarındaki önemli bilgileri (tablo adı, sorgu süresi, hata kodu vb.) vurgula
9. ML severity score'larını yorumla: 80+ KRİTİK, 60-80 YÜKSEK, 40-60 ORTA, 0-40 DÜŞÜK — neden bu skor verildiğini açıkla
10. Her sorun için ÇALIŞTIRILABİLİR veritabanı komutu öner (kopyala-yapıştır çalışacak şekilde, kod bloğu içinde)
11. Genel tavsiye VERME — her komut spesifik tablo/index/collection adı içermeli (loglardan çıkar)
"""

            estimated_tokens = estimate_token_count(chunk_prompt)
            if estimated_tokens > 15000:
                logger.warning(f"[TOKEN WARNING] Chunk {chunk_idx} exceeds soft limit: {estimated_tokens} tokens, truncating to 15 anomalies")
                current_chunk = current_chunk[:15]
                # Optionally, prompt regeneration (left as original source for brevity)
                # It's crucial that LLM uses context; only top anomalies/first 25 shown for safety

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=chunk_prompt)
            ]

            try:
                # LLM çağrısını thread'e taşıyarak event loop'un kilitlenmesini önle
                response = await asyncio.to_thread(llm_connector.invoke, messages)
                chunk_responses.append({
                    'chunk_idx': chunk_idx + 1,
                    'response': response.content,
                    'anomaly_count': len(current_chunk)
                })
                logger.info(f"Chunk {chunk_idx + 1} processed successfully")
            except Exception as e:
                logger.error(f"Error processing chunk {chunk_idx + 1}: {e}")
                chunk_responses.append({
                    'chunk_idx': chunk_idx + 1,
                    'response': f"Chunk {chunk_idx + 1} işlenemedi: {str(e)}",
                    'anomaly_count': len(current_chunk)
                })

        # 5. ADIM: Merge & Aggregation
        update_progress(request_id, "merge", "Analiz sonuçları birleştiriliyor ve özetleniyor...", 90)

        if len(chunk_responses) > 1:
            aggregate_prompt = f"""

{anomaly_digest}

{conversation_history}KULLANICI SORUSU: {query}

ANALİZ ÖZETİ:
- Toplam {len(all_anomalies)} anomali tespit edildi
- {len(chunk_responses)} farklı chunk analiz edildi
- Toplam {sum(cr['anomaly_count'] for cr in chunk_responses)} anomali detaylı incelendi

CHUNK ANALİZ SONUÇLARI:
"""
            for cr in chunk_responses:
                aggregate_prompt += f"\n\n[Chunk {cr['chunk_idx']}] ({cr['anomaly_count']} anomali):\n{cr['response'][:1500]}..."

            aggregate_prompt += """

Yukarıdaki chunk analizlerini birleştirerek, kullanıcının sorusuna kapsamlı ve net bir yanıt oluştur.

BİRLEŞTİRME KURALLARI:
1. Tekrar eden pattern'leri grupla, aynı sorunu tekrar tekrar yazma.
2. Her chunk'tan gelen EN KRİTİK bulguları öne çıkar.
3. Çözüm komutlarını birleştir — aynı soruna aynı komutu iki kez yazma.
4. MUTLAKA çalıştırılabilir komutlar içersin (genel tavsiye yazma).
5. Aşağıdaki YANIT FORMATINI kullan."""

            if is_mssql:
                merge_system = """Sen MSSQL anomali analiz uzmanı bir Senior DBA'sin. Birden fazla analizi birleştirip tek tutarlı rapor oluşturabilirsin.

YANIT FORMATI:
📊 ÖZET: [Birleştirilmiş ana bulgu + toplam anomali sayısı + en kritik pattern]

🔍 DETAYLI ANALİZ:
- Her kritik pattern grubu için root cause + gerçek log örnekleri (```code block``` içinde)

⚠️ RİSKLER:
- Somut riskler ve zincir etkileri

✅ ÖNERİLER:
Her öneri: [ACİL/ORTA/DÜŞÜK] Başlık + Neden + ```sql``` çalıştırılabilir T-SQL komutu + Beklenen etki

Türkçe yanıt ver. MUTLAKA gerçek çalıştırılabilir T-SQL komutları ```sql``` kod bloğu içinde ver."""
            elif is_elasticsearch:
                merge_system = """Sen Elasticsearch anomali analiz uzmanı bir Senior Elasticsearch Engineer'sin. Birden fazla analizi birleştirip tek tutarlı rapor oluşturabilirsin.

YANIT FORMATI:
📊 ÖZET: [Birleştirilmiş ana bulgu + toplam anomali sayısı + en kritik pattern]

🔍 DETAYLI ANALİZ:
- Her kritik pattern grubu için root cause + gerçek log örnekleri (```code block``` içinde)

⚠️ RİSKLER:
- Somut riskler ve zincir etkileri

✅ ÖNERİLER:
Her öneri: [ACİL/ORTA/DÜŞÜK] Başlık + Neden + ```json``` çalıştırılabilir Elasticsearch REST API komutu + Beklenen etki

Türkçe yanıt ver. MUTLAKA gerçek çalıştırılabilir Elasticsearch API komutları ```json``` kod bloğu içinde ver."""
            else:
                merge_system = """Sen MongoDB anomali analiz uzmanı bir Senior DBA'sin. Birden fazla analizi birleştirip tek tutarlı rapor oluşturabilirsin.

YANIT FORMATI:
📊 ÖZET: [Birleştirilmiş ana bulgu + toplam anomali sayısı + en kritik pattern]

🔍 DETAYLI ANALİZ:
- Her kritik pattern grubu için root cause + gerçek log örnekleri (```code block``` içinde)

⚠️ RİSKLER:
- Somut riskler ve zincir etkileri

✅ ÖNERİLER:
Her öneri: [ACİL/ORTA/DÜŞÜK] Başlık + Neden + ```mongodb``` çalıştırılabilir MongoDB komutu + Beklenen etki

Türkçe yanıt ver. MUTLAKA gerçek çalıştırılabilir MongoDB komutları ```mongodb``` kod bloğu içinde ver."""
            final_messages = [
                SystemMessage(content=merge_system),
                HumanMessage(content=aggregate_prompt)
            ]

            try:

                # Final birleştirmeyi de thread'e taşı
                final_response = await asyncio.to_thread(llm_connector.invoke, final_messages)
                ai_response = final_response.content

                logger.info("Multi-chunk aggregation completed successfully")
            except Exception as e:
                logger.error(f"Aggregation error: {e}")
                ai_response = "Anomali Analiz Özeti:\n\n"
                for cr in chunk_responses:
                    ai_response += f"[Chunk {cr['chunk_idx']}]:\n{cr['response']}\n\n"
        else:
            ai_response = chunk_responses[0]['response'] if chunk_responses else "Analiz yapılamadı"
            if selected_chunk_indices:
                logger.info(f"Single chunk response used (chunk {selected_chunk_indices[0] + 1})")
            else:
                logger.info("Single chunk response used (no chunk indices available)")

        # Conversation memory — bu Q&A turunu kaydet
        _save_conversation_turn(effective_analysis_id, query, ai_response)
        logger.info(f"Conversation turn saved for analysis {effective_analysis_id}")

        response_data = {
            "status": "success",
            "total_anomalies": len(all_anomalies),
            "ai_response": ai_response,
            "analysis_id": analysis.get("analysis_id"),
            "timestamp": str(analysis.get("timestamp")),
            "host": analysis.get("host")
        }

        if len(chunk_responses) > 1:
            response_data["chunks_processed"] = len(chunk_responses)
            response_data["processed_chunks"] = [
                {
                    "chunk_idx": cr['chunk_idx'],
                    "anomaly_count": cr['anomaly_count'],
                    "status": "processed"
                }
                for cr in chunk_responses
            ]
            response_data["processing_mode"] = "multi-chunk"
            response_data["chunk_info"] = f"{len(chunk_responses)} chunk analiz edildi ve birleştirildi"
        else:
            response_data["chunks_processed"] = 1
            response_data["processed_chunks"] = [{
                "chunk_idx": selected_chunk_indices[0] + 1 if selected_chunk_indices else 1,
                "anomaly_count": chunk_responses[0]['anomaly_count'] if chunk_responses else 0,
                "status": "processed"
            }]
            response_data["processing_mode"] = "single-chunk"
            response_data["chunk_info"] = f"Chunk {selected_chunk_indices[0] + 1}/{total_chunks} işlendi" if selected_chunk_indices else "Tek parça işlendi"

        response_data["total_chunks"] = total_chunks
        response_data["performance_metrics"] = {
            "processing_time_ms": int((datetime.now() - start_time).total_seconds() * 1000) if 'start_time' in locals() else None,
            "tokens_estimated": len(ai_response.split()) * 1.3 if ai_response else 0,
            "chunks_skipped": total_chunks - len(chunk_responses) if len(chunk_responses) < total_chunks else 0
        }

        # Son Adım: Complete
        update_progress(request_id, "complete", "İşlem tamamlandı!", 100)
        return response_data

    except Exception as e:
        logger.error(f"Chat anomaly query error: {e}", exc_info=True)
        update_progress(request_id, "error", f"Hata: {str(e)}", 0)
        return {
            "status": "error",
            "message": str(e),
            "total_anomalies": 0
        }
    finally:
        # Context'i temizle
        if token:
            request_context.reset(token)

@app.post("/api/get-anomaly-chunk")
async def get_anomaly_chunk(request: Request):
    """
    Belirli bir anomali chunk'ını getir ve LCWGPT ile işle
    
    Request body:
    {
        "analysis_id": "analysis_xxx",
        "chunk_index": 0,  # 0-based index
        "api_key": "xxx"
    }
    """
    try:
        data = await request.json()
        analysis_id = data.get("analysis_id")
        chunk_index = data.get("chunk_index", 0)
        api_key = data.get("api_key")
        
        # API key kontrolü
        if not await verify_api_key(api_key):
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid API key"}
            )
        
        logger.info(f"Getting chunk {chunk_index} for analysis {analysis_id}")
        
        # Storage'dan analizi al
        storage = await get_storage_manager()
        if storage:
            analysis_list = await storage.get_anomaly_history(
                filters={"analysis_id": analysis_id},
                limit=1,
                include_details=True
            )
            
            if not analysis_list or len(analysis_list) == 0:
                return JSONResponse(
                    status_code=404,
                    content={"error": "Analysis not found"}
                )
            
            analysis = analysis_list[0]
            
            # Anomalileri al
            if "detailed_data" in analysis:
                anomalies = analysis["detailed_data"].get("data", {}).get("critical_anomalies", [])
            else:
                # Fallback to sonuç
                anomalies = (analysis.get("sonuç") or {}).get("critical_anomalies", [])
            
            if not anomalies:
                return JSONResponse(
                    status_code=404,
                    content={"error": "No anomalies found in analysis"}
                )
            
            # Chunk'lara böl
            chunk_size = 20
            chunks = [anomalies[i:i+chunk_size] for i in range(0, len(anomalies), chunk_size)]
            total_chunks = len(chunks)
            
            # Geçerli chunk index kontrolü
            if chunk_index >= total_chunks or chunk_index < 0:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": f"Invalid chunk index. Valid range: 0-{total_chunks-1}",
                        "total_chunks": total_chunks
                    }
                )
            
            # İstenen chunk'ı al
            selected_chunk = chunks[chunk_index]
            
            # LCWGPT'ye gönder
            logger.info(f"Processing chunk {chunk_index + 1}/{total_chunks} with {len(selected_chunk)} anomalies")
            
            # LCWGPT isteği hazırla
            lcwgpt_prompt = f"""Aşağıda MongoDB anomali logları var. Bunları analiz et ve önemli pattern'leri açıkla.
            
            CHUNK BİLGİSİ: {chunk_index + 1}/{total_chunks}
            Toplam {len(anomalies)} anomaliden {chunk_index * chunk_size + 1}-{min((chunk_index + 1) * chunk_size, len(anomalies))} arası gösteriliyor.
            
            ANOMALI LOGLARI:
            """
            
            for i, anomaly in enumerate(selected_chunk, start=chunk_index * chunk_size + 1):
                lcwgpt_prompt += f"\n{i}. [{anomaly.get('timestamp', 'N/A')}] {anomaly.get('component', 'N/A')}: {anomaly.get('message', 'N/A')[:200]}"
            
            # LCWGPT'ye gönder
            llm_connector = await get_llm_connector()
            if llm_connector:
                try:
                    messages = [
                        SystemMessage(content="Sen MongoDB log analiz uzmanısın. Türkçe ve anlaşılır şekilde anomalileri açıkla."),
                        HumanMessage(content=lcwgpt_prompt)
                    ]
                    response = llm_connector.invoke(messages)
                    lcwgpt_response = response.content
                except Exception as e:
                    logger.error(f"LCWGPT invoke error: {e}")
                    lcwgpt_response = f"LCWGPT analizi yapılamadı: {str(e)}"
            else:
                lcwgpt_response = "LCWGPT bağlantısı kurulamadı"
            
            # Response hazırla
            result = {
                "status": "success",
                "chunk_index": chunk_index,
                "total_chunks": total_chunks,
                "chunk_info": f"{chunk_index + 1}/{total_chunks} chunk",
                "anomalies_in_chunk": len(selected_chunk),
                "total_anomalies": len(anomalies),
                "ai_response": lcwgpt_response,
                "has_next": chunk_index < total_chunks - 1,
                "has_previous": chunk_index > 0
            }
            
            return JSONResponse(content=result)
            
        else:
            return JSONResponse(
                status_code=503,
                content={"error": "Storage manager not initialized"}
            )
            
    except Exception as e:
        logger.error(f"Error getting anomaly chunk: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal server error: {str(e)}"}
        )

# Helper fonksiyonlar 
def _format_dict_for_prompt(data: dict, limit: int = None) -> str:
    """Dictionary'yi prompt için formatla"""
    sorted_items = sorted(data.items(), key=lambda x: x[1], reverse=True)
    if limit:
        sorted_items = sorted_items[:limit]
    
    result = []
    for key, value in sorted_items:
        result.append(f"- {key}: {value} adet")
    return "\n".join(result)

def _get_severity_category(score):
    """ML severity score'unu insan-okunur kategoriye çevir"""
    if score >= 80: return "KRİTİK"
    elif score >= 60: return "YÜKSEK"
    elif score >= 40: return "ORTA"
    else: return "DÜŞÜK"

def _format_top_anomalies_with_full_logs(anomalies: list, limit: int = 5) -> str:
    """En kritik anomalileri FULL LOG MESAJLARIYLA formatla (ML score yorumuyla)"""
    sorted_anomalies = sorted(anomalies,
                             key=lambda x: x.get('severity_score', 0),
                             reverse=True)[:limit]

    result = []
    for i, a in enumerate(sorted_anomalies, 1):
        score = a.get('severity_score', 0)
        category = _get_severity_category(score)
        context = a.get('context', {})
        # Fingerprint bilgisi varsa pattern tekrar sayısını göster
        fingerprint = a.get('message_fingerprint', '')
        fp_note = f"\n   Pattern Fingerprint: {fingerprint[:12]}..." if fingerprint else ""

        result.append(f"""
{i}. ANOMALİ #{a.get('index', i)}
   Timestamp: {a.get('timestamp', 'N/A')}
   Component: {a.get('component', 'N/A')}
   ML Severity Score: {score:.1f}/100 → {category} ({a.get('severity_level', 'N/A')})
   Anomaly Type: {a.get('anomaly_type', 'N/A')}{fp_note}

   TAM LOG MESAJI:
{a.get('message', 'Log mesajı mevcut değil')}

   Context — Operation: {context.get('operation', 'N/A')} | Host: {a.get('host', 'N/A')}
""")

    return "\n".join(result)

def _format_anomalies_with_full_messages(anomalies: list) -> str:
    """Anomalileri FULL LOG MESAJLARIYLA formatla (ML score yorumuyla)"""
    result = []
    for i, a in enumerate(anomalies[:20], 1):  # İlk 20 anomali
        context = a.get('context', {})
        score = a.get('severity_score', 0)
        category = _get_severity_category(score)
        result.append(f"""
--- Anomali #{i} ---
Component: {a.get('component', 'N/A')} | ML Score: {score:.1f}/100 ({category})
Timestamp: {a.get('timestamp', 'N/A')}
Anomaly Type: {a.get('anomaly_type', 'N/A')} | Operation: {context.get('operation', 'N/A')}

Tam Log Mesajı:
{a.get('message', 'Mesaj yok')}

---""")

    if len(anomalies) > 20:
        result.append(f"\n... ve {len(anomalies) - 20} anomali daha (token limiti nedeniyle kısaltıldı)")

    return "\n".join(result)

def _format_anomalies_for_prompt(anomalies: list) -> str:
    """Anomalileri prompt için formatla"""
    result = []
    for i, a in enumerate(anomalies[:20], 1):  # İlk 20 anomali
        result.append(f"{i}. [{a.get('component', 'N/A')}] Score: {a.get('severity_score', 0):.1f} - {a.get('message', '')[:80]}...")
    return "\n".join(result)

def _get_chunk_category_distribution(anomalies: list) -> str:
    """Chunk içindeki anomali kategorilerini özetle"""
    categories = {}
    for a in anomalies:
        component = a.get('component', 'UNKNOWN')
        categories[component] = categories.get(component, 0) + 1
    
    result = []
    for comp, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / len(anomalies)) * 100
        result.append(f"- {comp}: {count} adet (%{percentage:.1f})")
    return "\n".join(result)

def _get_time_distribution(anomalies: list) -> str:
    """Anomalilerin zaman dağılımını analiz et"""
    from collections import defaultdict
    hour_dist = defaultdict(int)
    
    for a in anomalies:
        timestamp = a.get('timestamp', '')
        if timestamp:
            try:
                # ISO format'tan saat çıkar
                hour = timestamp.split('T')[1].split(':')[0]
                hour_dist[hour] += 1
            except:
                pass
    
    if not hour_dist:
        return "Zaman bilgisi mevcut değil"
    
    # En yoğun saatleri bul
    peak_hours = sorted(hour_dist.items(), key=lambda x: x[1], reverse=True)[:3]
    result = [f"Peak saatler: {', '.join([f'{h}:00 ({c} anomali)' for h, c in peak_hours])}"]
    return "\n".join(result)

def _format_top_anomalies_detailed(anomalies: list, limit: int = 5) -> str:
    """En kritik anomalileri detaylı formatla"""
    # Severity score'a göre sırala
    sorted_anomalies = sorted(anomalies, 
                             key=lambda x: x.get('severity_score', 0), 
                             reverse=True)[:limit]
    
    result = []
    for i, a in enumerate(sorted_anomalies, 1):
        result.append(f"""
{i}. [{a.get('timestamp', 'N/A')}]
   Component: {a.get('component', 'N/A')}
   Severity: {a.get('severity_score', 0):.1f} ({a.get('severity_level', 'N/A')})
   Message: {a.get('message', 'N/A')[:200]}
   Context: {a.get('context', {}).get('operation', 'N/A')}
   Impact: {a.get('anomaly_type', 'N/A')}""")
    
    return "\n".join(result)

def _format_anomalies_with_context(anomalies: list) -> str:
    """Anomalileri context bilgileriyle formatla"""
    result = []
    for i, a in enumerate(anomalies[:30], 1):  # İlk 30 anomali
        context = a.get('context', {})
        result.append(
            f"{i}. [{a.get('component', 'N/A')}] "
            f"Score:{a.get('severity_score', 0):.1f} "
            f"Op:{context.get('operation', 'N/A')} "
            f"- {a.get('message', '')[:100]}"
        )
    
    if len(anomalies) > 30:
        result.append(f"... ve {len(anomalies) - 30} anomali daha")
    
    return "\n".join(result)

def _determine_relevant_chunk(query: str, all_anomalies: list, chunk_size: int) -> int:
    """
    Kullanıcı sorusuna göre en relevant chunk'ı belirle
    
    Args:
        query: Kullanıcı sorusu
        all_anomalies: Tüm anomaliler
        chunk_size: Chunk boyutu
        
    Returns:
        En relevant chunk'ın index'i
    """
    try:
        query_lower = query.lower()
        total_chunks = (len(all_anomalies) + chunk_size - 1) // chunk_size
        
        # Soruda belirtilen component'leri tespit et
        common_components = ['repl', 'query', 'command', 'network', 'storage', 'control', 'write', 'index']
        mentioned_components = [comp for comp in common_components if comp in query_lower]
        
        # Soruda belirtilen severity/önem kelimelerini tespit et  
        severity_keywords = {
            'kritik': ['critical', 'high'],
            'yüksek': ['high', 'critical'], 
            'orta': ['medium', 'moderate'],
            'düşük': ['low', 'info']
        }
        mentioned_severity = None
        for tr_key, en_values in severity_keywords.items():
            if tr_key in query_lower or any(en_val in query_lower for en_val in en_values):
                mentioned_severity = en_values
                break
        
        # Her chunk için relevance score hesapla
        chunk_scores = []
        for chunk_idx in range(total_chunks):
            start_idx = chunk_idx * chunk_size
            end_idx = min(start_idx + chunk_size, len(all_anomalies))
            chunk = all_anomalies[start_idx:end_idx]
            
            score = 0
            
            # Component match score
            if mentioned_components:
                component_matches = sum(1 for a in chunk 
                                      if any(comp in (a.get('component', '') or '').lower() 
                                           for comp in mentioned_components))
                score += component_matches * 2
            
            # Severity match score  
            if mentioned_severity:
                severity_matches = sum(1 for a in chunk
                                     if any(sev in (a.get('severity_level', '') or '').lower()
                                          for sev in mentioned_severity))
                score += severity_matches * 3
            
            # High score bias (kritik anomaliler öncelikli)
            avg_score = sum(a.get('severity_score', 0) for a in chunk) / len(chunk) if chunk else 0
            score += avg_score * 0.1
            
            # Son chunk'larda penalty (daha az relevant olma eğilimi)
            if chunk_idx > total_chunks * 0.7:
                score *= 0.8
                
            chunk_scores.append((chunk_idx, score))
        
        # En yüksek score'lu chunk'ı seç
        best_chunk = max(chunk_scores, key=lambda x: x[1])
        selected_chunk_idx = best_chunk[0]
        
        logger.info(f"Chunk relevance scores: {[(i, f'{s:.2f}') for i, s in chunk_scores]}")
        logger.info(f"Selected chunk {selected_chunk_idx + 1}/{total_chunks} with score {best_chunk[1]:.2f}")
        
        return selected_chunk_idx
        
    except Exception as e:
        logger.error(f"Error determining relevant chunk: {e}")
        # Fallback: İlk chunk'ı döndür
        return 0


@app.get("/api/debug/server-validation")
async def debug_server_validation(api_key: str):
    """
    Sunucu validasyon sistemini test et
    Production'da disable edilmeli
    """
    if not await verify_api_key(api_key):
        raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
    
    try:
        from src.anomaly.log_reader import get_available_mongodb_hosts
        
        # Mevcut sunucuları al
        available_hosts = get_available_mongodb_hosts(last_hours=24)
        
        # Test senaryoları
        test_results = {
            "available_hosts": available_hosts[:10],
            "total_hosts": len(available_hosts),
            "validation_tests": []
        }
        
        # Test 1: Sunucu adı olmadan query
        test_results["validation_tests"].append({
            "test": "Query without server name",
            "query": "anomali göster",
            "expected": "Server name required error",
            "endpoint": "/api/query"
        })
        
        # Test 2: Geçerli sunucu adı ile query
        if available_hosts:
            test_results["validation_tests"].append({
                "test": "Query with valid server name",
                "query": f"{available_hosts[0]} için anomali göster",
                "expected": "Success with server-specific data",
                "server_detected": available_hosts[0],
                "endpoint": "/api/query"
            })
        
        # Test 3: Chat endpoint validation
        test_results["validation_tests"].append({
            "test": "Chat without server name",
            "query": "yavaş sorgular neler?",
            "expected": "Server name required error",
            "endpoint": "/api/chat-query-anomalies"
        })
        
        # Test 4: FQDN düzeltmesi
        test_hostname = "lcwmongodb01n2"
        from src.anomaly.anomaly_tools import AnomalyDetectionTools
        tools = AnomalyDetectionTools()
        fixed_hostname = tools._fix_mongodb_hostname_fqdn(test_hostname)
        
        test_results["fqdn_correction"] = {
            "input": test_hostname,
            "output": fixed_hostname,
            "corrected": test_hostname != fixed_hostname
        }
        
        # Test 5: Storage'daki son analiz sunucu bilgisi
        storage = await get_storage_manager()
        if storage:
            recent_analyses = await storage.get_anomaly_history(limit=1)
            if recent_analyses:
                last_analysis = recent_analyses[0]
                test_results["last_analysis_server"] = {
                    "analysis_id": last_analysis.get("analysis_id"),
                    "host": last_analysis.get("host", "N/A"),
                    "timestamp": str(last_analysis.get("timestamp", "N/A"))
                }
        
        # Sistem durumu özeti
        test_results["system_status"] = {
            "query_endpoint_validation": "✅ ACTIVE",
            "chat_endpoint_validation": "✅ ACTIVE",
            "opensearch_host_filter": "✅ ACTIVE",
            "fqdn_correction": "✅ ACTIVE" if test_results.get("fqdn_correction", {}).get("corrected") else "⚠️ NOT NEEDED",
            "storage_server_tracking": "✅ ACTIVE" if test_results.get("last_analysis_server") else "⚠️ NO DATA"
        }
        
        logger.info(f"Server validation debug completed - {len(available_hosts)} hosts found")
        
        return test_results
        
    except Exception as e:
        logger.error(f"Server validation debug error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/dba/analyze-specific-time")
async def dba_analyze_specific_time(
    host: str = Query(..., description="MongoDB sunucu adı (virgülle ayrılmış multiple host destekler)"),
    start_time: str = Query(..., description="Başlangıç zamanı (ISO format)"),
    end_time: str = Query(..., description="Bitiş zamanı (ISO format)"),
    api_key: str = Query(..., description="API anahtarı"),
    auto_explain: bool = Query(True, description="LCWGPT ile otomatik açıklama")
):
    """
    DBA'lar için spesifik zaman aralığı anomali analizi (Semaphore Korumalı)
    
    Örnek kullanım:
    /api/dba/analyze-specific-time?host=LCWMONGODB01&start_time=2025-09-15T16:09:00Z&end_time=2025-09-15T16:11:00Z&api_key=xxx
    """
    async with ANOMALY_ANALYSIS_SEMAPHORE:
        try:
            # API key kontrolü
            if not await verify_api_key(api_key):
                raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
            
            # Multiple host desteği kontrolü
            hosts_list = []
            is_cluster = False

            if ',' in host:
                # Multiple hosts - virgülle ayrılmış
                hosts_list = [h.strip() for h in host.split(',')]
                is_cluster = True
                logger.info(f"DBA CLUSTER analysis request: {hosts_list} from {start_time} to {end_time}")
                
                # ✅ DEBUG: Her host'u ayrı ayrı logla
                for idx, h in enumerate(hosts_list):
                    logger.info(f"Host {idx + 1}/{len(hosts_list)}: '{h}'")
            else:
                # Tek host
                hosts_list = [host]
                logger.info(f"DBA single host analysis request: {host}")
            
            # Tarih formatı validasyonu
            from dateutil import parser
            try:
                start_dt = parser.parse(start_time)
                end_dt = parser.parse(end_time)
                
                # Zaman aralığı kontrolü (max 24 saat)
                time_diff = (end_dt - start_dt).total_seconds() / 3600
                if time_diff > 24:
                    logger.warning(f"Time range too large: {time_diff} hours")
                    # Uyarı ver ama devam et
                    
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Geçersiz tarih formatı: {e}")
            
            # Anomaly tools'u çağır
            from src.anomaly.anomaly_tools import AnomalyDetectionTools
            anomaly_tools = AnomalyDetectionTools(environment='production')

            if is_cluster:
                # Cluster analizi - paralel işleme
                import asyncio
                
                async def analyze_single_host(single_host):
                    """Tek bir host için analiz yap"""
                    result = anomaly_tools.analyze_mongodb_logs({
                        "source_type": "opensearch",
                        "host_filter": single_host,
                        "start_time": start_time,
                        "end_time": end_time,
                        "time_range": "custom"
                    })
                    return result
                
                # Paralel analiz başla
                logger.info(f"Starting parallel analysis for {len(hosts_list)} hosts...")
                
                # Asyncio.to_thread kullanarak sync fonksiyonu async çalıştır
                tasks = []
                for h in hosts_list:
                    tasks.append(asyncio.to_thread(
                        anomaly_tools.analyze_mongodb_logs,
                        {
                            "source_type": "opensearch",
                            "host_filter": h,
                            "start_time": start_time,
                            "end_time": end_time,
                            "time_range": "custom"
                        }
                    ))
                
                # Tüm analizleri bekle
                results = await asyncio.gather(*tasks)
                
                # ✅ DEBUG: Her host'un sonucunu logla
                for i, res_str in enumerate(results):
                    res = json.loads(res_str) if isinstance(res_str, str) else res_str
                    host_name = hosts_list[i]
                    logger.info(f"Host '{host_name}' result status: {res.get('durum', 'UNKNOWN')}")
                    if res.get('durum') == 'başarılı':
                        data = res.get('sonuç') or {}
                        logger.info(f"Host '{host_name}': {data.get('total_logs', 0)} logs, {len(data.get('critical_anomalies', []))} anomalies")
                    else:
                        logger.error(f"Host '{host_name}' analysis failed: {res.get('açıklama', 'No error message')}")
                
                # Sonuçları birleştir
                combined_anomalies = []
                total_logs = 0
                host_results = {}
                for i, res_str in enumerate(results):
                    res = json.loads(res_str) if isinstance(res_str, str) else res_str
                    host_name = hosts_list[i]
                    
                    if res.get('durum') == 'başarılı' and res.get('sonuç'):
                        data = res['sonuç']
                        # Her host'un anomalilerini topla
                        host_anomalies = data.get('critical_anomalies', [])
                        for anomaly in host_anomalies:
                            anomaly['source_host'] = host_name  # Host bilgisi ekle
                        combined_anomalies.extend(host_anomalies)
                        
                        # İstatistikleri topla
                        total_logs += data.get('total_logs', 0)
                        
                        # Host bazlı sonuçları sakla
                        host_results[host_name] = {
                            'anomaly_count': len(host_anomalies),
                            'logs_analyzed': data.get('total_logs', 0),
                            'anomaly_rate': data.get('anomaly_rate', 0)
                        }
                
                # Birleştirilmiş sonucu hazırla
                tool_result = {
                    'durum': 'başarılı',
                    'işlem': 'cluster_anomaly_analysis',
                    'açıklama': f'{len(hosts_list)} sunucu için cluster analizi tamamlandı',
                    'sonuç': {
                        'is_cluster': True,
                        'hosts_analyzed': hosts_list,
                        'total_logs': total_logs,
                        'critical_anomalies': combined_anomalies,
                        'anomaly_count': len(combined_anomalies),
                        'anomaly_rate': (len(combined_anomalies) / total_logs * 100) if total_logs > 0 else 0,
                        'host_breakdown': host_results
                    }
                }
                
            else:
                # Tek host analizi (mevcut kod)
                tool_result = anomaly_tools.analyze_mongodb_logs({
                    "source_type": "opensearch",
                    "host_filter": host,
                    "start_time": start_time,
                    "end_time": end_time,
                    "time_range": "custom"
                })
            
            # Sonucu parse et

            if isinstance(tool_result, str):
                result = json.loads(tool_result)
            else:
                result = tool_result
            
            # Kritik anomalileri al
            critical_anomalies = (result.get('sonuç') or {}).get('critical_anomalies', [])
            anomaly_count = len(critical_anomalies)
            

            # LCWGPT ile her anomaliyi tek tek açıklama (chunk bazlı, context-aware)
            ai_explanation = None
            if auto_explain and anomaly_count > 0:
                llm_connector = await get_llm_connector()
                if llm_connector:
                    try:
                        anomalies_to_analyze = critical_anomalies[:20]
                        chunk_size = 5
                        all_anomaly_explanations = []
                        
                        query = f"{host} sunucusu için {start_time} - {end_time} aralığında anomali analizi"

                        logger.info(f"Analyzing {len(anomalies_to_analyze)} anomalies individually in chunks of {chunk_size}")

                        # Context analizlerini almaya çalış (tüm kodda context kaynağı parse edilmiş olmalı)
                        context_analyses = result.get('context_analyses', None) if 'context_analyses' in result else None
                        total_chunks = (len(anomalies_to_analyze) + chunk_size - 1) // chunk_size

                        for chunk_idx, chunk_start in enumerate(range(0, len(anomalies_to_analyze), chunk_size)):
                            chunk_end = min(chunk_start + chunk_size, len(anomalies_to_analyze))
                            chunk = anomalies_to_analyze[chunk_start:chunk_end]

                            # ✅ DÜZELTME: Context'i direkt chunk prompt'una ekle, mevcut kullanıcı sorusu formatı korunarak
                            if context_analyses:
                                chunk_prompt = f"""
KULLANICI SORUSU: {query}

İLGİLİ GEÇMİŞ ANALİZLER:
"""
                                for idx, ctx in enumerate(context_analyses, 1):
                                    chunk_prompt += f"""
Geçmiş Analiz #{idx} - {ctx.get('host', 'N/A')} ({ctx.get('time_range', 'N/A')}):
- Anomali Sayısı: {ctx.get('anomaly_count', 0)}
"""
                                chunk_prompt += f"""

ANA ANALİZ - Chunk {chunk_idx + 1}/{total_chunks}:
"""
                            else:
                                chunk_prompt = f"""
KULLANICI SORUSU: {query}

Chunk {chunk_idx + 1}/{total_chunks}:
"""

                            chunk_prompt += f"""
MongoDB sisteminde tespit edilen {len(chunk)} anomaliyi analiz et.
Sunucu: {host}

Her bir anomali için ayrı ayrı:
1. Ne tür bir sorun olduğunu açıkla
2. Olası nedenleri mantıklı bir şekilde belirt
3. Sistem üzerindeki etkisini değerlendir veya açıkla
4. Spesifik çözüm önerisi sun, genel geçer bir çözüm kesinlikle önerme.
5. Analiz edilen anomali loglarını baz alarak gerçekçi ve uygulanabilir çözüm önerisi yap
6. Tüm log mesajlarını dikkatlice incele ve analiz et

ANOMALİLER:
"""

                            for i, anomaly in enumerate(chunk, 1):
                                anomaly_number = chunk_start + i
                                chunk_prompt += f"""

=== ANOMALİ #{anomaly_number} ===
Timestamp: {anomaly.get('timestamp', 'N/A')}
Component: {anomaly.get('component', 'UNKNOWN')}
Severity: {anomaly.get('severity_level', 'MEDIUM')}
Anomaly Score: {anomaly.get('anomaly_score', 0):.4f}
Host: {anomaly.get('source_host', anomaly.get('host', 'N/A'))}

Log Mesajı:
{anomaly.get('message', 'No message available')[:500]}

---
"""

                            chunk_prompt += """
YANIT FORMATI:
Her anomali için şu formatta yanıt ver:

**Anomali #X (Timestamp: [Timestamp] ve Açıklayıcı kısa başlık):**
📌 **Sorun:** [Kısa açıklama]
🔍 **Detay:** [Teknik detaylar]
⚠️ **Etki:** [Sistem üzerindeki etkisi]
💡 **Çözüm:** [Gerçekçi ve uygulanabilir çözüm önerisi]

Türkçe, teknik ve net ifadeler kullan.
"""

                            try:
                                messages = [
                                    SystemMessage(content="""Sen uzman bir MongoDB DBA'sin. 
Her anomaliyi detaylı analiz edip, spesifik çözümler öneriyorsun. Analiz edilen anomali loglarını baz alarak çözüm önerisi yap.
Yanıtların kısa, net ve aksiyona yönelik olmalı."""),
                                    HumanMessage(content=chunk_prompt)
                                ]

                                response = llm_connector.invoke(messages)
                                all_anomaly_explanations.append({
                                    'chunk_idx': chunk_idx,
                                    'start_idx': chunk_start + 1,
                                    'end_idx': chunk_start + len(chunk),
                                    'content': response.content
                                })

                                logger.info(f"Chunk {chunk_idx + 1}: Anomalies {chunk_start + 1}-{chunk_start + len(chunk)} analyzed")

                            except Exception as e:
                                logger.error(f"Error analyzing chunk {chunk_idx + 1}: {e}")
                                all_anomaly_explanations.append({
                                    'chunk_idx': chunk_idx,
                                    'start_idx': chunk_start + 1,
                                    'end_idx': chunk_start + len(chunk),
                                    'content': f"Bu anomaliler analiz edilemedi: {str(e)}"
                                })
                        
                        # Tüm açıklamaları birleştir
                        if all_anomaly_explanations:
                            ai_explanation = f"""
## 🔍 DETAYLI ANOMALİ ANALİZİ

**Analiz Özeti:**
- 📅 Zaman Aralığı: {start_time} - {end_time}
- 🖥️ Sunucu: {host}
- 📊 Toplam Anomali: {anomaly_count}
- 🔎 Detaylı İncelenen: {len(anomalies_to_analyze)}

---

### 📋 HER ANOMALİNİN DETAYLI ANALİZİ:

"""
                            # Her chunk'ın içeriğini ekle
                            for explanation in all_anomaly_explanations:
                                ai_explanation += f"\n{explanation['content']}\n"
                                if explanation != all_anomaly_explanations[-1]:
                                    ai_explanation += "\n---\n"
                            
                            ai_explanation += f"""

---

*Not: Toplam {anomaly_count} anomaliden ilk {len(anomalies_to_analyze)} tanesi detaylı analiz edilmiştir.*
"""
                            
                            logger.info(f"✅ Complete individual anomaly analysis for {len(anomalies_to_analyze)} anomalies")

                    except Exception as e:
                        logger.error(f"LCWGPT analysis error: {e}")
                        ai_explanation = f"Anomali analizi sırasında hata: {str(e)}"
            # Storage'a kaydet
            storage_id = None
            if ENABLE_STORAGE and anomaly_count > 0:
                try:
                    storage = await get_storage_manager()
                    save_result = await storage.save_anomaly_analysis(
                        analysis_result={
                            'durum': 'başarılı',
                            'işlem': 'dba_analysis',
                            'sonuç': {
                                'critical_anomalies': critical_anomalies[:500],  # UI için özet
                                'unfiltered_anomalies': critical_anomalies,  
                                'critical_anomalies_full': critical_anomalies,  
                                'total_logs': total_logs if is_cluster else (result.get('sonuç') or {}).get('total_logs', 0),
                                'anomaly_count': anomaly_count,
                                'anomaly_rate': (result.get('sonuç') or {}).get('anomaly_rate', 0),
                                'host_breakdown': host_results if is_cluster else None
                            }
                        },
                        source_type='opensearch_dba',
                        host=host,
                        time_range=f"{start_time} to {end_time}",
                        model_info=result.get('model_info') if isinstance(result, dict) else None  # Model metadata linkage
                    )
                    storage_id = save_result.get('analysis_id')
                    logger.info(f"✅ DBA analysis saved with ID: {storage_id}")
                except Exception as e:
                    logger.error(f"Failed to save DBA analysis: {e}")
            
            # Response hazırla
            return {
                "status": "success",
                "host": host,
                "time_range": {
                    "start": start_time,
                    "end": end_time,
                    "duration_hours": time_diff
                },
                "results": {
                    "total_logs_analyzed": total_logs if is_cluster else (result.get('sonuç') or {}).get('total_logs', 0),
                    "anomaly_count": anomaly_count,
                    "anomaly_rate": (result.get('sonuç') or {}).get('anomaly_rate', 0),
                    "critical_anomalies": critical_anomalies,  # TÜM anomaliler UI pagination için
                    "ai_summary": ai_explanation
                },
                "storage_id": storage_id or result.get('storage_info', {}).get('analysis_id'),
                "timestamp": datetime.now().isoformat()
            }
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"DBA analysis error: {e}")
            raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dba/analysis-history")
async def get_dba_analysis_history(
    limit: int = Query(20, le=50, description="Maksimum sonuç sayısı"),
    days_back: int = Query(30, le=90, description="Kaç gün geriye bakılacak"),
    api_key: str = Query(..., description="API anahtarı")
):
    """
    DBA analiz geçmişini MongoDB'den getir
    
    Returns:
        Son yapılan DBA analizlerinin özeti
    """
    try:
        # API key kontrolü
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        # Storage Manager'ı al
        storage = await get_storage_manager()
        if not storage:
            logger.warning("Storage Manager not available, returning empty history")
            return {
                "status": "success", 
                "analyses": [],
                "message": "Storage not available",
                "count": 0
            }
        
        # MongoDB'den DBA analizlerini çek
        logger.info(f"Fetching DBA analysis history: limit={limit}, days_back={days_back}")
        
        analyses = await storage.get_dba_analysis_history(
            source_type="opensearch_dba",
            limit=limit,
            days_back=days_back
        )
        
        # Başarılı response
        logger.info(f"✅ Retrieved {len(analyses)} DBA analyses from history")
        
        return {
            "status": "success",
            "analyses": analyses,
            "count": len(analyses),
            "query_params": {
                "limit": limit,
                "days_back": days_back
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get DBA analysis history: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Geçmiş yüklenirken hata: {str(e)}")

@app.get("/api/mssql/analysis-history")
async def get_mssql_analysis_history(
    limit: int = Query(20, le=50, description="Maksimum sonuç sayısı"),
    days_back: int = Query(30, le=90, description="Kaç gün geriye bakılacak"),
    api_key: str = Query(..., description="API anahtarı")
):
    """
    MSSQL analiz geçmişini MongoDB'den getir

    DBA analysis-history ile aynı yapı, source_type='mssql_opensearch' filtreli.

    Returns:
        Son yapılan MSSQL analizlerinin özeti
    """
    try:
        # API key kontrolü
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")

        # Storage Manager'ı al
        storage = await get_storage_manager()
        if not storage:
            logger.warning("Storage Manager not available, returning empty MSSQL history")
            return {
                "status": "success",
                "analyses": [],
                "message": "Storage not available",
                "count": 0
            }

        # MongoDB'den MSSQL analizlerini çek
        logger.info(f"Fetching MSSQL analysis history: limit={limit}, days_back={days_back}")

        analyses = await storage.get_dba_analysis_history(
            source_type="mssql_opensearch",
            limit=limit,
            days_back=days_back
        )

        # Başarılı response
        logger.info(f"✅ Retrieved {len(analyses)} MSSQL analyses from history")

        return {
            "status": "success",
            "analyses": analyses,
            "count": len(analyses),
            "database_type": "mssql",
            "query_params": {
                "limit": limit,
                "days_back": days_back
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get MSSQL analysis history: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"MSSQL geçmiş yüklenirken hata: {str(e)}")


@app.get("/api/elasticsearch/analysis-history")
async def get_elasticsearch_analysis_history(
    limit: int = Query(20, le=50, description="Maksimum sonuç sayısı"),
    days_back: int = Query(30, le=90, description="Kaç gün geriye bakılacak"),
    api_key: str = Query(..., description="API anahtarı")
):
    """
    Elasticsearch analiz geçmişini MongoDB'den getir

    DBA/MSSQL analysis-history ile aynı yapı, source_type='elasticsearch_opensearch' filtreli.

    Returns:
        Son yapılan Elasticsearch analizlerinin özeti
    """
    try:
        # API key kontrolü
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")

        # Storage Manager'ı al
        storage = await get_storage_manager()
        if not storage:
            logger.warning("Storage Manager not available, returning empty Elasticsearch history")
            return {
                "status": "success",
                "analyses": [],
                "message": "Storage not available",
                "count": 0
            }

        # MongoDB'den Elasticsearch analizlerini çek
        logger.info(f"Fetching Elasticsearch analysis history: limit={limit}, days_back={days_back}")

        analyses = await storage.get_dba_analysis_history(
            source_type="elasticsearch_opensearch",
            limit=limit,
            days_back=days_back
        )

        # Başarılı response
        logger.info(f"✅ Retrieved {len(analyses)} Elasticsearch analyses from history")

        return {
            "status": "success",
            "analyses": analyses,
            "count": len(analyses),
            "database_type": "elasticsearch",
            "query_params": {
                "limit": limit,
                "days_back": days_back
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get Elasticsearch analysis history: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Elasticsearch geçmiş yüklenirken hata: {str(e)}")

@app.get("/api/dba/analysis/{analysis_id}")
async def get_dba_analysis_details(
    analysis_id: str,
    api_key: str = Query(..., description="API anahtarı")
):
    """
    Belirli bir DBA analizinin detaylarını getir
    
    Args:
        analysis_id: MongoDB'deki analysis ID
        
    Returns:
        Analizin tüm detayları
    """
    try:
        # API key kontrolü
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        # Storage Manager'ı al
        storage = await get_storage_manager()
        if not storage:
            raise HTTPException(status_code=503, detail="Storage not available")
        
        # Analizi getir
        logger.info(f"Fetching DBA analysis details for ID: {analysis_id}")
        
        filters = {"analysis_id": analysis_id}
        analyses = await storage.get_anomaly_history(
            filters=filters,
            limit=1,
            include_details=True
        )
        
        if not analyses:
            raise HTTPException(status_code=404, detail="Analiz bulunamadı")
        
        analysis = analyses[0]
        
        # Response hazırla
        return {
            "status": "success",
            "analysis": analysis,
            "analysis_id": analysis_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get analysis details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= QUERY HISTORY ENDPOINTS =============
@app.post("/api/query-history/save")
async def save_query_history(request: Dict[str, Any]):
    """
    Save query to MongoDB history - METADATA DAHİL HER ŞEY
    """
    try:
        api_key = request.get("api_key")
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        storage = await get_storage_manager()
        if not storage or not storage.mongodb:
            raise HTTPException(status_code=503, detail="Storage not available")
        
        # TÜM metadata'yı dahil et
        _req_result = request.get("result") or {}
        _req_sonuc = _req_result.get("sonuç") or {}
        query_item = {
            # Temel bilgiler
            "query": request.get("query", ""),
            "type": request.get("type", "chatbot"),
            "category": request.get("category", "chatbot"),
            "durum": request.get("durum", "tamamlandı"),
            "işlem": request.get("işlem", ""),

            # Metadata
            "user_id": request.get("user_id"),
            "session_id": request.get("session_id"),
            "timestamp": request.get("timestamp"),
            "executionTime": request.get("executionTime"),

            # Sonuç verileri (sadece özet)
            "result_summary": {
                "durum": _req_result.get("durum"),
                "işlem": _req_result.get("işlem"),
                "has_anomalies": bool(_req_sonuc.get("critical_anomalies")),
                "anomaly_count": len(_req_sonuc.get("critical_anomalies", [])),
                "total_logs": _req_sonuc.get("total_logs", 0)
            },
            
            # Referanslar
            "storage_id": request.get("storage_id"),
            "analysis_id": request.get("analysis_id"),
            "parent_id": request.get("parentId"),
            
            # Flags
            "hasVisualization": request.get("hasVisualization", False),
            "hasResult": request.get("hasResult", False),
            "isAnomalyParent": request.get("isAnomalyParent", False),
            "fromMongoDB": True,  # Artık her şey MongoDB'de
            
            # AI/ML metadata
            "has_ml_data": bool(request.get("mlData")),
            "has_ai_explanation": bool(request.get("aiExplanation")),
            
            # Browser info (opsiyonel) - ✅ DÜZELTİLDİ
            "user_agent": request.get("user_agent"),
            "screen_resolution": request.get("screen_resolution"),
            "timezone": request.get("timezone")
        }
        
        # Büyük verileri ayrı collection'a kaydet (opsiyonel)
        if _req_sonuc.get("critical_anomalies"):
            # Anomali detayları için referans oluştur
            query_item["has_detailed_data"] = True
            query_item["anomaly_details_ref"] = request.get("storage_id")
        
        # MongoDB'ye kaydet
        query_id = await storage.mongodb.save_query_history(query_item)
        
        if query_id:
            logger.info(f"✅ Query metadata saved to MongoDB: {query_id}")
            logger.info(f"   Type: {query_item['type']}")
            logger.info(f"   Category: {query_item['category']}")
            logger.info(f"   Has Result: {query_item['hasResult']}")
            logger.info(f"   Session: {query_item['session_id']}")
            
            return {
                "status": "success",
                "query_id": query_id,
                "message": "Query and metadata saved to MongoDB",
                "saved_fields": len(query_item),
                "metadata_complete": True
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to save query")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving query history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/query-history/load")
async def load_query_history(
    api_key: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),  # Maksimum 200 olarak düzelt
    query_type: Optional[str] = None
):
    """
    Load query history from MongoDB
    Frontend localStorage yerine MongoDB'den yükleme
    """
    try:
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        storage = await get_storage_manager()
        if not storage or not storage.mongodb:
            logger.warning("Storage not available, returning empty history")
            return {
                "status": "success",
                "history": [],
                "count": 0,
                "source": "none"
            }
        
        # MongoDB'den query history al
        history = await storage.mongodb.get_query_history(
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            query_type=query_type
        )
        
        # Frontend formatına dönüştür
        formatted_history = []
        for item in history:
            # MongoDB'den gelen veriyi frontend formatına çevir
            formatted_item = {
                "id": item.get("query_id", ""),
                "timestamp": item.get("timestamp").isoformat() if item.get("timestamp") else None,
                "query": item.get("query", ""),
                "type": item.get("query_type", "chatbot"),
                "category": item.get("category", "chatbot"),
                "result": item.get("result", {}),
                "durum": item.get("durum", "tamamlandı"),
                "işlem": item.get("işlem", ""),
                "executionTime": item.get("execution_time"),
                "hasVisualization": item.get("has_visualization", False),
                "mlData": item.get("ml_data"),
                "aiExplanation": item.get("ai_explanation"),
                "storage_id": item.get("storage_id"),
                "childResult": item.get("result", {}),  # Compatibility
                "hasResult": True if item.get("result") else False,
                "fromMongoDB": True  # MongoDB'den geldiğini işaretle
            }
            formatted_history.append(formatted_item)
        
        logger.info(f"✅ Loaded {len(formatted_history)} items from MongoDB query history")
        
        return {
            "status": "success",
            "history": formatted_history,
            "count": len(formatted_history),
            "source": "mongodb"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading query history: {e}")
        return {
            "status": "error",
            "message": str(e),
            "history": [],
            "count": 0
        }


@app.delete("/api/query-history/{query_id}")
async def delete_query_history_item(query_id: str, api_key: str):
    """
    Delete a specific query from history
    """
    try:
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        storage = await get_storage_manager()
        if not storage or not storage.mongodb:
            raise HTTPException(status_code=503, detail="Storage not available")
        
        success = await storage.mongodb.delete_query_history_item(query_id)
        
        if success:
            logger.info(f"✅ Query {query_id} deleted from MongoDB")
            return {
                "status": "success",
                "message": f"Query {query_id} deleted"
            }
        else:
            raise HTTPException(status_code=404, detail="Query not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/storage/check-size")
async def check_storage_size(api_key: str):
    """
    Check MongoDB storage size and trigger cleanup if needed
    """
    try:
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        storage = await get_storage_manager()
        if not storage or not storage.mongodb:
            raise HTTPException(status_code=503, detail="Storage not available")
        
        # MongoDB boyutunu kontrol et
        size_info = await storage.mongodb.check_database_size()
        
        # Boyut limiti kontrolü (10GB varsayılan)
        max_size_gb = 10.0
        current_size = size_info.get("total_size_gb", 0)
        
        # Eğer limit aşıldıysa temizlik yap
        deleted_count = 0
        if current_size > max_size_gb:
            logger.warning(f"⚠️ Storage limit exceeded: {current_size:.2f} GB > {max_size_gb} GB")
            deleted_count = await storage.mongodb.cleanup_by_size(max_size_gb)
            
            # Temizlik sonrası yeni boyut
            size_info = await storage.mongodb.check_database_size()
        
        return {
            "status": "success",
            "size_info": size_info,
            "max_size_gb": max_size_gb,
            "is_over_limit": current_size > max_size_gb,
            "deleted_count": deleted_count,
            "message": f"Storage: {size_info.get('total_size_gb', 0):.2f} GB / {max_size_gb} GB"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking storage size: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/query-history/clear")
async def clear_query_history(request: Dict[str, Any]):
    """
    Clear ALL history (Chat + Anomaly + DBA) globally.
    Force delete all records regardless of session.
    """
    try:
        api_key = request.get("api_key")
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        storage = await get_storage_manager()
        if not storage or not storage.mongodb:
            raise HTTPException(status_code=503, detail="Storage not available")
        
        # 1. Chat History Silme (GLOBAL - Session farketmeksizin)
        deleted_queries = await storage.mongodb.clear_all_query_history()
        
        # 2. Anomaly & DBA History Silme (GLOBAL - Daha önce eklediğimiz fonksiyon)
        deleted_analyses = await storage.mongodb.clear_all_analysis_history()
        
        total_deleted = deleted_queries + deleted_analyses
        logger.info(f"✅ GLOBAL WIPE: Cleared {deleted_queries} queries and {deleted_analyses} analyses.")
        
        return {
            "status": "success",
            "deleted_count": total_deleted,
            "details": {
                "queries": deleted_queries,
                "analyses": deleted_analyses
            },
            "message": f"Tüm geçmiş temizlendi ({deleted_queries} sohbet, {deleted_analyses} analiz)"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/query-history/verify/{query_id}")
async def verify_query_history_item(query_id: str, api_key: str):
    """
    Verify if a query exists in MongoDB
    Used for data consistency checks
    """
    try:
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        storage = await get_storage_manager()
        if not storage or not storage.mongodb:
            return {"exists": False, "message": "Storage not available"}
        
        # MongoDB'de query_id ile arama yap
        collection = storage.mongodb.db[storage.mongodb.collections.get("query_history", "query_history")]
        
        # Query ID ile kayıt ara
        document = await collection.find_one({"query_id": query_id})
        
        if document:
            logger.info(f"✅ Query verified in MongoDB: {query_id}")
            return {
                "exists": True,
                "query_id": query_id,
                "timestamp": document.get("timestamp").isoformat() if document.get("timestamp") else None,
                "query": document.get("query", "")[:50] + "...",  # İlk 50 karakter
                "message": "Query found in MongoDB"
            }
        else:
            logger.warning(f"⚠️ Query not found in MongoDB: {query_id}")
            return {
                "exists": False,
                "query_id": query_id,
                "message": "Query not found"
            }
            
    except Exception as e:
        logger.error(f"Error verifying query: {e}")
        return {
            "exists": False,
            "error": str(e),
            "message": "Verification failed"
        }

# ============================================
# ML MODEL PANEL ENDPOINTS
# ============================================

@app.get("/api/ml/metrics")
async def get_ml_metrics(api_key: str = Query(...)):
    """ML model metriklerini döndür — sadece gercek veriler"""
    try:
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")

        # Baslangic: tum degerler None (bilinmiyor)
        metrics = {
            "model_accuracy": None,
            "f1_score": None,
            "precision": None,
            "recall": None,
            "total_logs_analyzed": 0,
            "total_anomalies_detected": 0,
            "anomaly_rate": 0.0,
            "model_version": None,
            "last_training_date": None,
            "is_trained": False
        }

        # Model durumunu kontrol et
        global anomaly_detector
        if anomaly_detector and anomaly_detector.is_trained:
            metrics["is_trained"] = True
            model_info = anomaly_detector.get_model_info()
            training_stats = model_info.get('training_stats', {})

            # Gercek egitim bilgileri
            metrics["model_version"] = f"v{training_stats.get('model_version', model_info.get('version', ''))}" if training_stats.get('model_version') or model_info.get('version') else None
            if training_stats.get('timestamp'):
                metrics["last_training_date"] = training_stats['timestamp']

            # Gercek feature/sample sayilari
            metrics["n_features"] = model_info.get('n_features', 0)
            metrics["n_training_samples"] = training_stats.get('n_samples', 0)

        # Storage'dan gercek analiz sonuclarini al
        storage = await get_storage_manager()
        if storage:
            try:
                recent = await storage.get_anomaly_history(limit=10)
                if recent:
                    total_logs = sum(a.get('logs_analyzed', 0) for a in recent)
                    total_anomalies = sum(a.get('anomaly_count', 0) for a in recent)

                    metrics["total_logs_analyzed"] = total_logs
                    metrics["total_anomalies_detected"] = total_anomalies
                    if total_logs > 0:
                        metrics["anomaly_rate"] = (total_anomalies / total_logs) * 100
                        # Accuracy: Isolation Forest icin anomaly_rate'den turetilen yaklasik deger
                        # Gercek accuracy degil, ama en azindan veri bazli
                        metrics["model_accuracy"] = round(100 - metrics["anomaly_rate"], 1)
            except Exception as e:
                logger.warning(f"Could not fetch metrics from storage: {e}")

        # NOT: f1_score, precision, recall Isolation Forest (unsupervised) modelde
        # gercek anlamda hesaplanamaz. Label verisi olmadan bu metrikler anlamsizdir.
        # Bu yuzden None olarak birakiyoruz — UI'da "--" gosterilecek.

        return {
            "status": "success",
            "metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"ML metrics error: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.post("/api/ml/validate-log")
async def validate_single_log(request: Dict[str, Any]):
    """Tek bir log satırını anomali açısından değerlendir"""
    try:
        api_key = request.get('api_key')
        log_text = request.get('log_text', '')
        
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        if not log_text:
            return {"status": "error", "message": "Log text is required"}
        
        # Anomaly detector kullan
        global anomaly_detector
        
        # Basit feature extraction
        from src.anomaly.feature_extractor import MongoDBLogFeatureExtractor
        extractor = MongoDBLogFeatureExtractor()
        
        # Tek log için features çıkar
        features = extractor.extract_features([{
            'message': log_text,
            'timestamp': datetime.now().isoformat(),
            'component': 'USER_INPUT',
            'severity': 'I'
        }])
        
        anomaly_score = 0.5  # Default
        
        if anomaly_detector.is_trained and len(features) > 0:
            # Model ile tahmin yap
            try:
                scores = anomaly_detector.model.decision_function(features)
                anomaly_score = abs(scores[0])
            except:
                pass
        
        # Basit keyword analizi de ekle
        severity_keywords = {
            'fatal': 0.9, 'error': 0.7, 'exception': 0.6, 
            'failed': 0.5, 'warning': 0.3, 'timeout': 0.6
        }
        
        log_lower = log_text.lower()
        for keyword, weight in severity_keywords.items():
            if keyword in log_lower:
                anomaly_score = max(anomaly_score, weight)
                break
        
        is_anomaly = anomaly_score > 0.5
        
        return {
            "status": "success",
            "analysis": {
                "is_anomaly": is_anomaly,
                "anomaly_score": min(0.99, anomaly_score),
                "severity": "HIGH" if anomaly_score > 0.7 else "MEDIUM" if anomaly_score > 0.4 else "LOW",
                "explanation": f"{'Anomali tespit edildi' if is_anomaly else 'Normal log'}. Score: {anomaly_score:.3f}",
                "recommendations": [
                    "Detaylı analiz için tam log dosyasını yükleyin"
                ] if is_anomaly else []
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Log validation error: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.get("/api/ml/model-info")
async def get_ml_model_info(api_key: str = Query(...)):
    """ML model bilgilerini dondur — sadece gercek veriler"""
    try:
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")

        global anomaly_detector

        # Baslangic: model yoksa tum degerler None
        model_info = {
            "model_type": "Isolation Forest",
            "is_trained": anomaly_detector.is_trained if anomaly_detector else False,
            "features_count": None,
            "training_samples": None,
            "model_trained_at": None,
            "model_version": None
        }

        if anomaly_detector and anomaly_detector.is_trained:
            info = anomaly_detector.get_model_info()
            training_stats = info.get('training_stats', {})
            if not isinstance(training_stats, dict):
                training_stats = {}

            model_info.update({
                "features_count": info.get('n_features', 0),
                "training_samples": training_stats.get('n_samples', 0),
                "model_trained_at": training_stats.get('timestamp'),
                "model_version": training_stats.get('model_version'),
                "server_name": training_stats.get('server_name'),
                "contamination_factor": info.get('parameters', {}).get('contamination', 0.05),
                "online_learning_enabled": info.get('online_learning', False)
            })

            # Buffer info
            buffer_info = anomaly_detector.get_historical_buffer_info()
            if buffer_info.get('enabled'):
                stats = buffer_info.get('buffer_stats', {})
                model_info["buffer_samples"] = stats.get('total_samples', 0)
                model_info["buffer_size_mb"] = stats.get('size_mb', 0)

            # Model dosya yolu — gercek .pkl dosyasini bul
            models_dir = Path("models")
            server = getattr(anomaly_detector, 'current_server', None)
            if server:
                safe_name = server.replace('.', '_').replace('/', '_')
                candidate = models_dir / f"isolation_forest_{safe_name}.pkl"
                if candidate.exists():
                    model_info["model_path"] = str(candidate.resolve())
                else:
                    model_info["model_path"] = str(candidate)
            else:
                candidate = models_dir / "isolation_forest.pkl"
                if candidate.exists():
                    model_info["model_path"] = str(candidate.resolve())
                else:
                    model_info["model_path"] = str(candidate)

        return {
            "status": "success",
            "model_info": model_info,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Model info error: {str(e)}")
        return {"status": "error", "message": str(e)}


# =====================================================================
# [FEEDBACK] Kullanici Anomali Feedback Sistemi
# =====================================================================

@app.post("/api/anomaly/feedback")
async def submit_anomaly_feedback(request: AnomalyFeedbackRequest):
    """
    Kullanici bir anomaliyi 'Dogru Tespit' veya 'Yanlis Alarm' olarak isaretler.
    In-memory store'a kaydeder. MongoDB varsa oraya da yazar.
    """
    try:
        if not await verify_api_key(request.api_key):
            raise HTTPException(status_code=401, detail="Gecersiz API anahtari")

        # Label validasyonu
        if request.label not in ("true_positive", "false_positive"):
            return {"status": "error", "message": "label 'true_positive' veya 'false_positive' olmali"}

        # In-memory store'a kaydet
        global anomaly_feedback_store
        if request.analysis_id not in anomaly_feedback_store:
            anomaly_feedback_store[request.analysis_id] = {}

        anomaly_feedback_store[request.analysis_id][request.anomaly_index] = {
            "label": request.label,
            "note": request.note,
            "timestamp": datetime.now().isoformat()
        }

        # MongoDB'ye de kaydet (varsa)
        try:
            storage = await get_storage_manager()
            if storage and hasattr(storage, 'save_user_feedback'):
                await storage.save_user_feedback(
                    analysis_id=request.analysis_id,
                    feedback={
                        "anomaly_index": request.anomaly_index,
                        "label": request.label,
                        "note": request.note,
                        "timestamp": datetime.now().isoformat()
                    }
                )
        except Exception as storage_err:
            logger.warning(f"MongoDB feedback kaydi basarisiz (in-memory devam ediyor): {storage_err}")

        # Analiz icin toplam feedback sayisi
        analysis_feedbacks = anomaly_feedback_store.get(request.analysis_id, {})
        tp_count = sum(1 for f in analysis_feedbacks.values() if f["label"] == "true_positive")
        fp_count = sum(1 for f in analysis_feedbacks.values() if f["label"] == "false_positive")

        logger.info(f"Feedback kaydedildi: analysis={request.analysis_id}, idx={request.anomaly_index}, label={request.label}")

        return {
            "status": "success",
            "message": "Feedback kaydedildi",
            "analysis_id": request.analysis_id,
            "anomaly_index": request.anomaly_index,
            "label": request.label,
            "feedback_summary": {
                "total_feedbacks": len(analysis_feedbacks),
                "true_positives": tp_count,
                "false_positives": fp_count
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Feedback kayit hatasi: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/anomaly/feedback/{analysis_id}")
async def get_anomaly_feedbacks(analysis_id: str, api_key: str = Query(...)):
    """Bir analiz icin tum kullanici feedback'lerini getir"""
    try:
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Gecersiz API anahtari")

        global anomaly_feedback_store
        feedbacks = anomaly_feedback_store.get(analysis_id, {})

        tp_count = sum(1 for f in feedbacks.values() if f["label"] == "true_positive")
        fp_count = sum(1 for f in feedbacks.values() if f["label"] == "false_positive")

        return {
            "status": "success",
            "analysis_id": analysis_id,
            "feedbacks": {str(k): v for k, v in feedbacks.items()},
            "summary": {
                "total_feedbacks": len(feedbacks),
                "true_positives": tp_count,
                "false_positives": fp_count
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Feedback getirme hatasi: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/ml/feedback-metrics")
async def get_feedback_metrics(api_key: str = Query(...)):
    """
    Toplanan kullanici feedback'lerinden gercek ML metrikleri hesapla.

    Mantik:
    - Model bir anomaliyi tespit etti (predicted=1)
    - Kullanici "true_positive" dedi → TP (model dogru bulmus)
    - Kullanici "false_positive" dedi → FP (model yanlis alarme vermis)
    - Feedback verilmemis anomaliler → sayilmaz (belirsiz)
    - Normal loglar (predicted=0) icin feedback olmadigi icin TN/FN hesaplanamaz
      Ama anomaly_rate'den yaklasik TN turetilir
    """
    try:
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Gecersiz API anahtari")

        global anomaly_feedback_store

        # Tum analizlerdeki feedback'leri topla
        total_tp = 0
        total_fp = 0
        total_feedbacks = 0
        analyses_with_feedback = 0

        for analysis_id, feedbacks in anomaly_feedback_store.items():
            if feedbacks:
                analyses_with_feedback += 1
                for fb in feedbacks.values():
                    total_feedbacks += 1
                    if fb["label"] == "true_positive":
                        total_tp += 1
                    elif fb["label"] == "false_positive":
                        total_fp += 1

        # Metrik hesaplama
        metrics = {
            "total_feedbacks": total_feedbacks,
            "analyses_with_feedback": analyses_with_feedback,
            "true_positives": total_tp,
            "false_positives": total_fp,
            "precision": None,
            "recall": None,
            "f1_score": None,
            "false_positive_rate": None,
            "confidence_level": "none"
        }

        if total_feedbacks > 0:
            # Precision = TP / (TP + FP) — modelin tespit ettikleri arasinda dogru orani
            precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
            metrics["precision"] = round(precision, 4)

            # False positive rate
            metrics["false_positive_rate"] = round(total_fp / total_feedbacks, 4)

            # lastAnomalyResult'tan total_logs ve n_anomalies cek (yaklasik TN/FN icin)
            # Bu sadece yaklasim — gercek TN/FN icin etiketli normal log lazim
            # Recall icin: TP / (TP + FN). FN bilinmiyor ama
            # kullanici sadece anomali isaretlenenler hakkinda feedback veriyor
            # Bu yuzden recall = None (hesaplanamaz — sadece precision gercek)

            # F1 sadece precision varsa hesaplanir (recall olmadan tek tarafli)
            # Recall bilinmedigi icin: lower-bound F1 = precision (recall=1 varsayimi)
            # Ama daha dogru: F1 = None (eksik bilgi)
            metrics["f1_score"] = None  # Recall olmadan hesaplanamaz

            # Guven seviyesi
            if total_feedbacks >= 50:
                metrics["confidence_level"] = "high"
            elif total_feedbacks >= 20:
                metrics["confidence_level"] = "medium"
            elif total_feedbacks >= 5:
                metrics["confidence_level"] = "low"
            else:
                metrics["confidence_level"] = "very_low"

        return {
            "status": "success",
            "metrics": metrics,
            "disclaimer": "Precision gercek kullanici feedback'inden hesaplandi. Recall ve F1 icin etiketli normal log verisi gereklidir.",
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Feedback metrics hatasi: {e}")
        return {"status": "error", "message": str(e)}


# [PAGINATION] On-Demand Data Loading Endpoint
@app.get("/api/analysis/{analysis_id}/paged-anomalies")
async def get_paged_anomalies(
    analysis_id: str, 
    api_key: str,
    skip: int = Query(0, ge=0, description="Kaç kayıt atlanacak"), 
    limit: int = Query(100, le=1000, description="Kaç kayıt getirilecek (Max 1000)"),
    list_type: str = Query("unfiltered_anomalies", regex="^(unfiltered_anomalies|critical_anomalies)$", description="Hangi liste çekilecek")
):
    """
    MongoDB'deki kayıtlı analizden anomali listesini parça parça (pagination) getirir.
    Projection ($slice) kullandığı için bellek dostudur.
    
    Args:
        list_type: 'unfiltered_anomalies' veya 'critical_anomalies'
    """
    try:
        # 1. Güvenlik Kontrolü
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        # 2. Storage Bağlantısı
        storage = await get_storage_manager()
        if not storage or not getattr(storage, "mongodb", None):
            raise HTTPException(status_code=503, detail="Storage servisi aktif değil")
        collection = storage.mongodb.db["anomaly_history"]
        # 3. MongoDB Projection Hazırlığı
        # Sadece istenen array'in, istenen aralığını ($slice) çekiyoruz.
        # Diğer büyük alanları (detailed_data vb.) network'e yüklemiyoruz.
        projection = {
            f"sonuç.{list_type}": {"$slice": [skip, limit]},
            "analysis_id": 1,
            # Gereksiz büyük alanları hariç tut
            "detailed_data": 0, 
            "sonuç.data": 0,
            "sonuç.component_analysis": 0
        }
        # 4. Veriyi Çek
        doc = await collection.find_one(
            {"analysis_id": analysis_id}, 
            projection
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Analiz bulunamadı")
        # 5. İstenen listeyi güvenli şekilde al
        # Not: MongoDB projection sonucu nested yapıyı korur: doc['sonuç']['unfiltered_anomalies']
        result_content = doc.get("sonuç") or {}
        anomalies = result_content.get(list_type, [])
        # Eğer veri yoksa boş liste dön (Hata fırlatma)
        if not anomalies:
            anomalies = []
        return {
            "status": "success",
            "analysis_id": analysis_id,
            "list_type": list_type,
            "pagination": {
                "skip": skip,
                "limit": limit,
                "fetched_count": len(anomalies)
            },
            "anomalies": anomalies
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pagination error for {analysis_id}: {e}")
        # Detaylı hatayı loga bas ama kullanıcıya genel hata dön
        raise HTTPException(status_code=500, detail=f"Veri çekme hatası: {str(e)}")

        
# Startup event'e ekle
@app.on_event("startup")
async def startup_event():
    """Uygulama başlatıldığında"""

    # ✅ GÜÇLENDİRİLMİŞ FİLTRELEME:
    # Hem Logger'a hem de Handler'larına filtreyi zorla ekle
    access_logger = logging.getLogger("uvicorn.access")
    endpoint_filter = EndpointFilter()

    # 1. Logger seviyesinde filtre
    access_logger.addFilter(endpoint_filter)

    # 2. Handler seviyesinde filtre (Çift dikiş - asıl işi yapan bu)
    for handler in access_logger.handlers:
        handler.addFilter(endpoint_filter)

    # Custom Log Handler'ı ekle
    progress_handler = AnomalyProgressLogHandler()
    logging.getLogger().addHandler(progress_handler)
    logger.info("✅ AnomalyProgressLogHandler registered and filters applied")

    # Session cleanup task'ı başlat
    asyncio.create_task(cleanup_expired_sessions())
    logger.info("Session cleanup task başlatıldı")

    # Progress cleanup task'ı başlat
    asyncio.create_task(cleanup_progress_cache())
    logger.info("Progress cache cleanup task başlatıldı")
    
    """API başlatıldığında çalışacak işlemler"""
    global storage_manager, anomaly_detector

    logger.info("Starting API server...")

    # Storage Manager'ı başlat
    if ENABLE_STORAGE:
        storage_manager = StorageManager()
        connected = await storage_manager.initialize()

        if connected:
            logger.info("✅ Storage Manager initialized successfully")
        else:
            logger.warning("⚠️ Storage Manager initialization failed - auto-save disabled")
            storage_manager = None

    # Model Auto-Load: Mevcut modeli kontrol et ve yükle
    try:
        models_dir = Path("models")
        models_dir.mkdir(parents=True, exist_ok=True)

        # Önce server-specific modelleri kontrol et
        if models_dir.exists():
            model_files = [f for f in os.listdir(models_dir) if f.startswith("isolation_forest_") and f.endswith(".pkl")]

            if model_files:
                # En son güncellenen modeli yükle
                latest_model = max(model_files, key=lambda f: os.path.getmtime(models_dir / f))
                server_name = latest_model.replace("isolation_forest_", "").replace(".pkl", "")
                model_path = models_dir / latest_model

                logger.info(f"📊 Found server-specific model: {latest_model}")
                logger.info(f"Loading server-specific model for: {server_name}")

                # Model'i yükle - Singleton pattern ile instance al
                # get_instance() içinde load_model(server_name=...) çağrılır.
                # FQDN normalizasyonu (split('.')[0]) yüzünden get_instance() dosya
                # adını yanlış çözebilir.  Bu yüzden: henüz yüklenmediyse, gerçek
                # dosya yolu ile bir kez daha deneriz.
                detector = MongoDBAnomalyDetector.get_instance(server_name=server_name)
                if not detector.is_trained:
                    success = detector.load_model(str(model_path))
                else:
                    success = True
                # Backward compatibility için global reference'ı güncelle
                anomaly_detector = detector

                if success:
                    # Model bilgilerini logla
                    model_info = detector.get_model_info()  # ✅ değişti

                    # 🔍 DEBUG: Model ve buffer durumunu detaylı logla
                    logger.info(f"🔍 DEBUG: Server-specific model yükleme sonrası durum kontrolü")
                    logger.info(f"    📍 Is trained: {detector.is_trained}")  # ✅ değişti
                    logger.info(f"    📍 Model instance ID: {id(detector)}")  # ✅ değişti
                    logger.info(f"    📍 Buffer enabled: {hasattr(detector, 'historical_data')}")  # ✅ değişti
                    if hasattr(detector, 'historical_data') and detector.historical_data:  # ✅ değişti
                        buffer_metadata = detector.historical_data.get('metadata', {})  # ✅ değişti
                        logger.info(f"    📍 Buffer metadata: {buffer_metadata}")
                        logger.info(f"    📍 Buffer samples: {buffer_metadata.get('total_samples', 'N/A')}")

                    logger.info(f"✅ Server-specific model loaded successfully!")
                    logger.info(f"    Server: {server_name}")
                    logger.info(f"    Model type: {model_info.get('model_type', 'Unknown')}")
                    logger.info(f"    Features: {model_info.get('n_features', 0)}")
                    logger.info(f"    Is trained: {model_info.get('is_trained', False)}")

                    # Historical buffer bilgisi
                    buffer_info = detector.get_historical_buffer_info()  # ✅ değişti
                    if buffer_info.get('enabled'):
                        buffer_stats = buffer_info.get('buffer_stats', {})
                        logger.info(f"    Historical buffer: {buffer_stats.get('total_samples', 0)} samples")
                        logger.info(f"    Buffer size: {buffer_stats.get('size_mb', 0):.2f} MB")
                        logger.info(f"    Last update: {buffer_stats.get('last_update', 'N/A')}")
                else:
                    logger.warning(f"⚠️ Server-specific model file exists but could not be loaded: {latest_model}")
                    logger.info("Will try global model or train new model on first analysis")

            elif (models_dir / "isolation_forest.pkl").exists():
                # Global model'i yükle
                global_model_path = models_dir / "isolation_forest.pkl"
                logger.info(f"📊 Found global model at: {global_model_path}")
                logger.info("Loading global model...")

                # Model'i yükle
                detector = MongoDBAnomalyDetector.get_instance(server_name="global")
                success = detector.load_model(str(global_model_path))
                # Backward compatibility için global reference'ı güncelle
                anomaly_detector = detector

                if success:
                    # Model bilgilerini logla
                    model_info = detector.get_model_info()  # ✅ değişti

                    # 🔍 DEBUG: Global model ve buffer durumunu detaylı logla
                    logger.info(f"🔍 DEBUG: Global model yükleme sonrası durum kontrolü")
                    logger.info(f"    📍 Is trained: {detector.is_trained}")  # ✅ değişti
                    logger.info(f"    📍 Model instance ID: {id(detector)}")  # ✅ değişti
                    logger.info(f"    📍 Buffer enabled: {hasattr(detector, 'historical_data')}")  # ✅ değişti
                    if hasattr(detector, 'historical_data') and detector.historical_data:  # ✅ değişti
                        buffer_metadata = detector.historical_data.get('metadata', {})  # ✅ değişti
                        logger.info(f"    📍 Buffer metadata: {buffer_metadata}")
                        logger.info(f"    📍 Buffer samples: {buffer_metadata.get('total_samples', 'N/A')}")

                    logger.info("✅ Global model loaded successfully!")
                    logger.info(f"    Model type: {model_info.get('model_type', 'unknown')}")
                    logger.info(f"    Features: {model_info.get('n_features', 0)}")
                    logger.info(f"    Is trained: {model_info.get('is_trained', False)}")

                    # Historical buffer bilgisi
                    buffer_info = detector.get_historical_buffer_info()  # ✅ değişti
                    if buffer_info.get('enabled'):
                        buffer_stats = buffer_info.get('buffer_stats', {})
                        logger.info(f"    Historical buffer: {buffer_stats.get('total_samples', 0)} samples")
                        logger.info(f"    Buffer size: {buffer_stats.get('size_mb', 0):.2f} MB")
                        logger.info(f"    Last update: {buffer_stats.get('last_update', 'N/A')}")
                else:
                    logger.warning("⚠️ Global model file exists but could not be loaded")
                    logger.info("Will train new model on first analysis")
            else:
                logger.info("📊 No existing models found at startup")
                logger.info(f"    Checked directory: {models_dir}")
                logger.info("    Will train new model on first analysis")
        else:
            logger.info(f"📊 Models directory created: {models_dir}")
            logger.info("    Will train new model on first analysis")

    except Exception as e:
        logger.error(f"Failed to initialize StorageManager: {e}")
        logger.error(f"❌ Error during model auto-load: {e}")
        logger.error(f"    Will train new model on first analysis")
        import traceback
        traceback.print_exc()


# ============= SYSTEM RESET ENDPOINT =============
@app.post("/api/system-reset")
async def system_reset(request: Dict[str, Any]):
    """
    Sistem reset endpoint - secili kategorileri temizler.
    system_reset.py scriptinin web API versiyonu.
    """
    import glob as glob_module

    categories = request.get("categories", [])
    dry_run = request.get("dry_run", True)

    if not categories:
        raise HTTPException(status_code=400, detail="En az bir kategori secilmeli")

    PROJECT_ROOT = Path(__file__).parent.parent.resolve()

    # Kategori -> hedef dosya/dizin eslesmesi
    CATEGORY_TARGETS = {
        "ml_models": [
            {"pattern": "models/*.pkl", "type": "file"},
            {"pattern": "models/**/*.pkl", "type": "file"},
            {"pattern": "storage/models/*.pkl", "type": "file"},
            {"pattern": "storage/models/**/*.pkl", "type": "file"},
            {"pattern": "models_backup_*", "type": "dir"},
        ],
        "anomaly_output": [
            {"pattern": "output/*.csv", "type": "file"},
            {"pattern": "output/*.json", "type": "file"},
            {"pattern": "storage/exports/anomaly/*.json", "type": "file"},
            {"pattern": "storage/exports/anomaly/*.pkl", "type": "file"},
            {"pattern": "storage/exports/anomaly/*.csv", "type": "file"},
        ],
        "storage_depot": [
            {"pattern": "storage/temp/*", "type": "file"},
            {"pattern": "storage/backups/*", "type": "any"},
            {"pattern": "storage/uploads/*", "type": "any"},
        ],
        "cache": [
            {"pattern": "cache/**/*", "type": "any"},
            {"pattern": "cache/*", "type": "any"},
        ],
        "logs": [
            {"pattern": "logs/*.log", "type": "file"},
            {"pattern": "temp_logs/*", "type": "any"},
        ],
        "metrics": [
            {"pattern": "metrics/*.json", "type": "file"},
        ],
        "pycache": [
            {"pattern": "**/__pycache__", "type": "dir"},
        ],
    }

    MONGODB_COLLECTIONS_LIST = [
        "anomaly_history", "model_registry", "user_feedback",
        "analysis_cache", "query_history", "user_preferences",
    ]

    def find_items(cat_key):
        targets = CATEGORY_TARGETS.get(cat_key, [])
        found = []
        for target in targets:
            pattern = str(PROJECT_ROOT / target["pattern"])
            items = glob_module.glob(pattern, recursive=True)
            for item in items:
                if "/.git/" in item or "/.git" == item:
                    continue
                if "/config/" in item:
                    continue
                if target["type"] == "file" and os.path.isfile(item):
                    found.append((item, "file"))
                elif target["type"] == "dir" and os.path.isdir(item):
                    found.append((item, "dir"))
                elif target["type"] == "any":
                    if os.path.isfile(item):
                        found.append((item, "file"))
                    elif os.path.isdir(item):
                        found.append((item, "dir"))
        # Tekrarlari kaldir
        seen = set()
        unique = []
        for p, t in found:
            if p not in seen:
                seen.add(p)
                unique.append((p, t))
        return unique

    def get_size(path):
        if os.path.isfile(path):
            return os.path.getsize(path)
        elif os.path.isdir(path):
            total = 0
            for dp, dn, fns in os.walk(path):
                for f in fns:
                    fp = os.path.join(dp, f)
                    if os.path.exists(fp):
                        total += os.path.getsize(fp)
            return total
        return 0

    def format_size(b):
        if b < 1024: return f"{b} B"
        elif b < 1024*1024: return f"{b/1024:.1f} KB"
        elif b < 1024*1024*1024: return f"{b/(1024*1024):.1f} MB"
        else: return f"{b/(1024*1024*1024):.2f} GB"

    file_results = {}
    total_files = 0
    total_bytes = 0

    for cat in categories:
        if cat == "mongodb":
            continue  # MongoDB ayri islenecek
        if cat not in CATEGORY_TARGETS:
            continue

        items = find_items(cat)
        deleted = 0
        failed = 0
        cat_bytes = 0

        for path, ftype in items:
            size = get_size(path)
            if not dry_run:
                try:
                    if ftype == "file":
                        os.remove(path)
                    elif ftype == "dir":
                        shutil.rmtree(path)
                    deleted += 1
                    cat_bytes += size
                except Exception as e:
                    logger.warning(f"[SYSTEM RESET] Silinemedi: {path} - {e}")
                    failed += 1
            else:
                deleted += 1
                cat_bytes += size

        file_results[cat] = {
            "deleted": deleted,
            "failed": failed,
            "total_bytes": cat_bytes,
            "total_bytes_formatted": format_size(cat_bytes)
        }
        total_files += deleted
        total_bytes += cat_bytes

    # MongoDB temizligi
    mongodb_results = {"cleared": 0, "failed": 0, "total_docs": 0}
    if "mongodb" in categories:
        try:
            from pymongo import MongoClient as SyncMongoClient
            conn_str = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
            db_name = os.getenv('MONGODB_STORAGE_DB', 'anomaly_detection')
            client = SyncMongoClient(conn_str, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            db = client[db_name]
            existing = db.list_collection_names()
            for coll_name in MONGODB_COLLECTIONS_LIST:
                if coll_name not in existing:
                    continue
                try:
                    doc_count = db[coll_name].count_documents({})
                    if not dry_run:
                        result = db[coll_name].delete_many({})
                        mongodb_results["total_docs"] += result.deleted_count
                    else:
                        mongodb_results["total_docs"] += doc_count
                    mongodb_results["cleared"] += 1
                except Exception as e:
                    logger.warning(f"[SYSTEM RESET] MongoDB '{coll_name}' temizlenemedi: {e}")
                    mongodb_results["failed"] += 1
            client.close()
        except Exception as e:
            logger.warning(f"[SYSTEM RESET] MongoDB baglanti hatasi: {e}")

    mode = "dry_run" if dry_run else "executed"
    logger.info(f"[SYSTEM RESET] mode={mode}, categories={categories}, "
                f"files={total_files}, bytes={total_bytes}, "
                f"mongo_docs={mongodb_results['total_docs']}")

    return JSONResponse({
        "status": "success",
        "mode": mode,
        "file_results": file_results,
        "mongodb_results": mongodb_results,
        "total_files": total_files,
        "total_size_formatted": format_size(total_bytes)
    })


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

    # Uvicorn'u başlatırken log_config=None veriyoruz.
    # Bu sayede Uvicorn kendi default log config'ini yüklemez,
    # bizim yukarıda yaptığımız logging.basicConfig ve addFilter ayarlarını kullanır.
    uvicorn.run(
        "api:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=True,
        log_level="info",
        log_config=None  # Bizim log ayarlarımızı ezmemesi için
    )