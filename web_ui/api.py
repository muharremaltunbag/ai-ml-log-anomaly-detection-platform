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
from langchain.schema import HumanMessage, SystemMessage
from src.connectors.lcwgpt_connector import LCWGPTConnector

from src.agents.mongodb_agent import MongoDBAgent
from web_ui.config import *
from dotenv import load_dotenv
# Anomaly detector import
from src.anomaly.anomaly_detector import MongoDBAnomalyDetector

# Global anomaly detector instance
anomaly_detector = MongoDBAnomalyDetector()
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
# Storage configuration
ENABLE_STORAGE = AUTO_SAVE_CONFIG.get("enabled", True)
MODEL_AUTO_LOAD = True  # Startup'ta modeli otomatik yükle
MODEL_PATH = "models/isolation_forest.pkl"  # Default model path

# Global LCWGPT connector instance
llm_connector: Optional[Any] = None
llm_lock = asyncio.Lock()


# Onay bekleyen parametreleri saklamak için - KALDIRILDI
# pending_confirmations: Dict[str, Dict[str, Any]] = {}  # DEPRECATED: Onay akışı kaldırıldı

# Güvenli session yönetimi
user_sessions: Dict[str, Dict[str, Any]] = {}

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
                
                # Sunucu adı yoksa hata dön
                if not detected_server:
                    logger.warning("❌ Anomali sorgusu yapıldı ama sunucu adı belirtilmedi")
                    return QueryResponse(
                        durum="eksik_parametre",
                        işlem="server_validation_failed",
                        açıklama="⚠️ Lütfen analiz yapmak istediğiniz MongoDB sunucusunu belirtin.\n\nÖrnek: 'lcwmongodb01n2 için anomali analizi yap'",
                        öneriler=[
                            "Sorgunuza sunucu adını ekleyin",
                            f"Mevcut sunucular: {', '.join(available_hosts[:5])}...",
                            "Örnek: 'lcwmongodb01n2 sunucusunda anomali var mı?'"
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
    """Cluster bazlı anomali analizi - tüm node'ları paralel analiz et"""
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
                    "sonuç": None
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
                    "sonuç": None
                })
        
        # Sonuçları birleştir

        combined_anomalies = []
        total_logs = 0
        host_results = {}
        failed_hosts = []
        
        for host, result_str in results:
            try:
                result = json.loads(result_str) if isinstance(result_str, str) else result_str
                
                if result.get('durum') == 'başarılı' and 'sonuç' in result:
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
                time_range=time_range
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
            # Mevcut sunucuları al ve kullanıcıya göster
            try:
                from src.anomaly.log_reader import get_available_mongodb_hosts
                available_hosts = get_available_mongodb_hosts(last_hours=24)
                
                logger.error("OpenSearch modu - Host filter belirtilmedi")
                
                # Detaylı hata mesajı
                error_message = {
                    "error": "Host filter zorunludur",
                    "message": "OpenSearch'ten veri çekmek için bir MongoDB sunucusu seçmelisiniz.",
                    "available_hosts": available_hosts[:20] if available_hosts else [],
                    "suggestion": "Lütfen 'host_filter' parametresinde bir sunucu adı belirtin.",
                    "example": {
                        "host_filter": available_hosts[0] if available_hosts else "lcwmongodb01n2.lcwaikiki.local"
                    }
                }
                
                raise HTTPException(
                    status_code=400, 
                    detail=error_message
                )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Host listesi alınamadı: {e}")
                raise HTTPException(
                    status_code=400, 
                    detail="OpenSearch için host filter belirtilmeli"
                )
        
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
            "host_filter": request.host_filter,
            "start_time": request.start_time,  # YENİ
            "end_time": request.end_time        # YENİ
        }
        
        # YENİ: Eğer start_time ve end_time verilmişse, time_range'i override et
        if request.start_time and request.end_time:
            analysis_params["time_range"] = "custom"  # Custom time range indicator
            logger.info(f"Using custom date range: {request.start_time} to {request.end_time}")

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
            tool_params = {
                "source_type": "opensearch",
                "host_filter": request.host_filter,
                "time_range": request.time_range,
                "last_hours": analysis_params.get("last_hours", 24)
            }

            # YENİ: Custom date range parametrelerini ekle
            if request.start_time and request.end_time:
                tool_params["start_time"] = request.start_time
                tool_params["end_time"] = request.end_time
                logger.info(f"OpenSearch query with date range: {request.start_time} - {request.end_time}")

            
            tool_result = anomaly_tools.analyze_mongodb_logs(tool_params)
            
            # Tool sonucunu parse et

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


def estimate_token_count(text: str) -> int:
    """Yaklaşık token sayısını hesapla"""
    # Ortalama olarak 4 karakter = 1 token
    return len(text) // 4

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


@app.post("/api/chat-query-anomalies")
async def chat_query_anomalies(request: Dict[str, Any]):
    """Chat üzerinden anomali sorgulama - LCWGPT ile"""
    start_time = datetime.now()  # Performance tracking için
    
    try:
        # API key kontrolü
        if not await verify_api_key(request.get('api_key')):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        query = request.get("query", "")
        analysis_id = request.get("analysis_id")
        
        logger.info(f"Chat anomaly query received - Query: {query[:50]}...")
        
        # YENİ: Analysis ID yoksa sunucu adı zorunlu
        if not analysis_id:
            try:
                from src.anomaly.log_reader import get_available_mongodb_hosts
                available_hosts = get_available_mongodb_hosts(last_hours=24)
                
                # Query'de sunucu adı kontrolü
                detected_server = None
                query_lower = query.lower()
                for host in available_hosts:
                    # Hem tam host adı hem de kısa versiyonu kontrol et
                    host_short = host.split('.')[0] if '.' in host else host
                    if host.lower() in query_lower or host_short.lower() in query_lower:
                        detected_server = host
                        logger.info(f"✅ Chat query'de sunucu tespit edildi: {detected_server}")
                        break
                
                if not detected_server:
                    logger.warning("❌ Chat anomali sorgusu yapıldı ama sunucu adı belirtilmedi")
                    # Kullanıcı dostu mesaj ve sunucu listesi
                    host_examples = available_hosts[:5] if available_hosts else []
                    return {
                        "status": "error",
                        "message": f"""⚠️ Lütfen sorgunuzda hangi MongoDB sunucusunu analiz etmek istediğinizi belirtin.

📌 **Mevcut sunucular:**
{chr(10).join(['• ' + h for h in host_examples])}

💡 **Örnek sorgular:**
- "{host_examples[0] if host_examples else 'lcwmongodb01n2'} sunucusundaki yavaş sorgular neler?"
- "{host_examples[0].split('.')[0] if host_examples else 'lcwmongodb01n2'} için authentication hataları var mı?"
- "{host_examples[0].split('.')[0] if host_examples else 'lcwmongodb01n2'}'deki kritik anomaliler nelerdir?" """,
                        "available_hosts": available_hosts,
                        "total_anomalies": 0
                    }
                
                # Sunucu adı varsa, o sunucuya ait son analizi bul
                # Sunucu adı varsa, o sunucuya ait son analizi bul
                filters = {"host": detected_server}
                logger.info(f"✅ Server detected in query: {detected_server}")
                logger.info(f"Searching for existing analysis in storage for server: {detected_server}")
                
                # Storage'dan bu sunucuya ait son analizi çek
                try:
                    storage = await get_storage_manager()
                    server_analyses = await storage.get_anomaly_history(
                        filters={"host": detected_server},
                        limit=1,
                        include_details=True
                    )
                    
                    if server_analyses and len(server_analyses) > 0:
                        logger.info(f"✅ Found existing analysis for {detected_server} in storage")
                        # Analysis ID'yi override et
                        analysis_id = server_analyses[0].get("analysis_id")
                        filters = {"analysis_id": analysis_id}
                        logger.info(f"Using analysis_id from storage: {analysis_id}")
                    else:
                        logger.warning(f"⚠️ No analysis found for server {detected_server} in storage")
                        # Kullanıcıya bilgilendirici mesaj dön
                        return {
                            "status": "error",
                            "message": f"❌ {detected_server} sunucusu için kayıtlı anomali analizi bulunamadı.\n\n" +
                                     f"Lütfen önce bu sunucu için anomali analizi yapın:\n" +
                                     f"• OpenSearch veri kaynağını seçin\n" +
                                     f"• '{detected_server}' sunucusunu seçin\n" +
                                     f"• 'Anomali Analizi Yap' butonuna tıklayın\n\n" +
                                     f"Analiz tamamlandıktan sonra sorularınızı sorabilirsiniz.",
                            "server_detected": detected_server,
                            "available_hosts": [],
                            "total_anomalies": 0
                        }
                except Exception as e:
                    logger.error(f"Error checking storage for server {detected_server}: {e}")
                    # Hata durumunda devam et
                    filters = {"host": detected_server}
                    
            except Exception as e:
                logger.error(f"Sunucu listesi alınamadı: {e}")
                # Fallback: analysis_id olmadan devam et
                filters = {}
        else:
            # Analysis ID varsa onu kullan
            filters = {"analysis_id": analysis_id}
        
        # Storage'dan anomalileri al
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
        
        # Unfiltered anomalileri al
        all_anomalies = analysis.get("unfiltered_anomalies", [])
        if not all_anomalies:
            all_anomalies = analysis.get("critical_anomalies", [])
        
        logger.info(f"Found {len(all_anomalies)} anomalies for LCWGPT processing")
        
        # ✅ TEST 2: Storage-First Yaklaşım
        logger.info(f"[STORAGE TEST] Loaded {len(all_anomalies)} anomalies from storage")
        logger.info(f"[STORAGE TEST] Analysis ID: {analysis_id}")
        
        # LCWGPT ile işle
        llm_connector = await get_llm_connector()

        if not llm_connector:
            logger.error("LCWGPT connection failed")
            return {
                "status": "error",
                "message": "LCWGPT bağlantısı kurulamadı",
                "total_anomalies": len(all_anomalies)
            }
        
        # ✅ Multi-chunk processing - Tüm chunk'ları işle
        # Token limitini aşmamak için chunk boyutunu küçült
        chunk_size = 20  
        total_chunks = (len(all_anomalies) + chunk_size - 1) // chunk_size

        # Progressive processing - Her seferde 3 chunk işle
        batch_size = 3  # Her batch'te 3 chunk
        max_chunks_to_process = min(total_chunks, 25)  # Maksimum 25 chunk (500 anomali)

        logger.info(f"Will process {max_chunks_to_process} chunks in batches of {batch_size}")

        # Kullanıcının sorusuna göre chunk önceliklendirmesi yap
        chunk_relevance_scores = []
        for i in range(total_chunks):
            relevance_score = _calculate_chunk_relevance(query, all_anomalies[i*chunk_size:(i+1)*chunk_size], i)
            chunk_relevance_scores.append((i, relevance_score))

        # En relevant chunk'ları seç
        chunk_relevance_scores.sort(key=lambda x: x[1], reverse=True)
        selected_chunk_indices = [idx for idx, _ in chunk_relevance_scores[:max_chunks_to_process]]
        selected_chunk_indices.sort()  # Sıralı işlem için

        logger.info(f"Processing {len(selected_chunk_indices)} most relevant chunks out of {total_chunks}")

        # ✅ TEST 1: Multi-Chunk Processing
        logger.info(f"[MULTI-CHUNK TEST] Processing {len(selected_chunk_indices)} chunks")
        logger.info(f"[MULTI-CHUNK TEST] Chunk indices: {selected_chunk_indices}")
        logger.info(f"[MULTI-CHUNK TEST] Total anomalies: {len(all_anomalies)}")

        # Component ve severity dağılımı hesapla (tüm anomaliler için)
        component_dist = {}
        severity_dist = {}
        for a in all_anomalies:
            comp = a.get('component', 'N/A')
            component_dist[comp] = component_dist.get(comp, 0) + 1
            
            sev = a.get('severity_level', 'N/A')
            severity_dist[sev] = severity_dist.get(sev, 0) + 1

        # LCWGPT için gelişmiş system prompt
        system_prompt = """Sen MongoDB anomali analizi ve performans optimizasyonu konusunda uzman bir DBA'sin. 
MongoDB loglarındaki pattern'leri tanıyabilir, root cause analizi yapabilir ve spesifik çözüm önerileri sunabilirsin.

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

YANIT FORMATI:
📊 ÖZET: [Tek cümlede ana bulgu ve ilgili log'ları tamamiyle göster]

🔍 DETAYLI ANALİZ:
Her kritik anomali için:
- Pattern açıklaması
- **GERÇEK LOG ÖRNEKLERİ:**[Timestamp] [Component] [Severity] Tam gövdesiyle log mesajı burada gösterilmeli
- Pattern grupları ve sayıları
- En kritik 6-7 spesifik log örneği
- Zaman dağılımı (peak saatler varsa)

⚠️ RİSKLER:
- Mevcut riskler
- Potansiyel sorunlar

✅ ÖNERİLER:
- Acil aksiyon gerektiren adımlar
- Orta vadeli iyileştirmeler
- Monitoring önerileri

Türkçe yanıt ver, teknik terimleri açıkla, DBA'ların anlayacağı detay seviyesinde ol. MUTLAKA gerçek log mesajlarını kod bloğu içinde göster. Önce log örneklerini göster sonra pattern açıklamasını ve sonra önerileri göster."""

        # Her chunk için LCWGPT çağrısı yap ve sonuçları topla
        chunk_responses = []
        for chunk_idx in selected_chunk_indices:
            start_idx = chunk_idx * chunk_size
            end_idx = min(start_idx + chunk_size, len(all_anomalies))
            current_chunk = all_anomalies[start_idx:end_idx]
            
            logger.info(f"Processing chunk {chunk_idx + 1}/{total_chunks} with {len(current_chunk)} anomalies")
            
            # Chunk-specific prompt hazırla
            chunk_prompt = f"""
KULLANICI SORUSU: {query}

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
6.Spesifik log gövdesini kullanıcıya direk göster
7. HER ANOMALİ İÇİN GERÇEK LOG MESAJINI KOD BLOĞU İÇİNDE GÖSTER
8. Log mesajlarındaki önemli bilgileri (tablo adı, sorgu süresi, hata kodu vb.) vurgula
"""

            # ✅ Token limit kontrolü
            estimated_tokens = estimate_token_count(chunk_prompt)
            if estimated_tokens > 3000:  # LCWGPT limit varsayımı
                logger.warning(f"[TOKEN WARNING] Chunk {chunk_idx} may exceed token limit: {estimated_tokens}")
                # Chunk'ı daha da küçült
                current_chunk = current_chunk[:25]  # Sadece ilk 25 anomali
                # Prompt'u yeniden hazırla
                chunk_prompt = f"""
KULLANICI SORUSU: {query}

CHUNK BİLGİSİ: {chunk_idx + 1}/{total_chunks} (Anomali {start_idx+1}-{min(start_idx+25, end_idx)} arası - TOKEN LİMİT UYARISI)

EN KRİTİK 5 ANOMALİ (Severity Score'a göre):
{_format_top_anomalies_detailed(current_chunk, limit=5)}

TÜM ANOMALİ DETAYLARI (İlk 25):
{_format_anomalies_with_context(current_chunk)}

GÖREV: Bu chunk'taki pattern'leri tespit et ve kullanıcının sorusuna odaklan.
"""

            # LCWGPT'ye gönder
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=chunk_prompt)
            ]
            
            try:
                response = llm_connector.invoke(messages)
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

        # Tüm chunk response'larını birleştir
        if len(chunk_responses) > 1:
            # Aggregate prompt hazırla
            aggregate_prompt = f"""
KULLANICI SORUSU: {query}

ANALİZ ÖZETİ:
- Toplam {len(all_anomalies)} anomali tespit edildi
- {len(chunk_responses)} farklı chunk analiz edildi
- Toplam {sum(cr['anomaly_count'] for cr in chunk_responses)} anomali detaylı incelendi

COMPONENT DAĞILIMI:
{_format_dict_for_prompt(component_dist, limit=10)}

SEVERITY DAĞILIMI:
{_format_dict_for_prompt(severity_dist)}

CHUNK ANALİZ SONUÇLARI:
"""
            for cr in chunk_responses:
                aggregate_prompt += f"\n\n[Chunk {cr['chunk_idx']}] ({cr['anomaly_count']} anomali):\n{cr['response'][:500]}..."
            
            aggregate_prompt += "\n\nYukarıdaki chunk analizlerini birleştirerek, kullanıcının sorusuna kapsamlı ve net bir yanıt oluştur."
            
            # Final aggregation
            final_messages = [
                SystemMessage(content="Sen MongoDB anomali analiz uzmanısın. Birden fazla analizi birleştirip özet çıkarabilirsin."),
                HumanMessage(content=aggregate_prompt)
            ]
            
            try:
                final_response = llm_connector.invoke(final_messages)
                ai_response = final_response.content
                logger.info("Multi-chunk aggregation completed successfully")
            except Exception as e:
                logger.error(f"Aggregation error: {e}")
                # Fallback: Chunk response'larını direkt birleştir
                ai_response = "Anomali Analiz Özeti:\n\n"
                for cr in chunk_responses:
                    ai_response += f"[Chunk {cr['chunk_idx']}]:\n{cr['response']}\n\n"
        else:
            # Tek chunk varsa direkt kullan
            ai_response = chunk_responses[0]['response'] if chunk_responses else "Analiz yapılamadı"
            logger.info(f"Single chunk response used (chunk {selected_chunk_indices[0] + 1})")

        
        # Response hazırla
        response_data = {
            "status": "success",
            "total_anomalies": len(all_anomalies),
            "ai_response": ai_response,
            "analysis_id": analysis.get("analysis_id"),
            "timestamp": str(analysis.get("timestamp"))
        }

        # Multi-chunk bilgilerini ekle
        if len(chunk_responses) > 1:
            # Multi-chunk processing yapıldı
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
            # Tek chunk processing
            response_data["chunks_processed"] = 1
            response_data["processed_chunks"] = [{
                "chunk_idx": selected_chunk_indices[0] + 1 if selected_chunk_indices else 1,
                "anomaly_count": chunk_responses[0]['anomaly_count'] if chunk_responses else 0,
                "status": "processed"
            }]
            response_data["processing_mode"] = "single-chunk"
            response_data["chunk_info"] = f"Chunk {selected_chunk_indices[0] + 1}/{total_chunks} işlendi"

        # Total chunks bilgisini ekle
        response_data["total_chunks"] = total_chunks

        # Performance metrics ekle (opsiyonel)
        response_data["performance_metrics"] = {
            "processing_time_ms": int((datetime.now() - start_time).total_seconds() * 1000) if 'start_time' in locals() else None,
            "tokens_estimated": len(ai_response.split()) * 1.3 if ai_response else 0,  # Yaklaşık token tahmini
            "chunks_skipped": total_chunks - len(chunk_responses) if len(chunk_responses) < total_chunks else 0
        }

        return response_data
        
    except Exception as e:
        logger.error(f"Chat anomaly query error: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "total_anomalies": 0
        }


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
                anomalies = analysis.get("sonuç", {}).get("critical_anomalies", [])
            
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

def _format_top_anomalies_with_full_logs(anomalies: list, limit: int = 5) -> str:
    """En kritik anomalileri FULL LOG MESAJLARIYLA formatla"""
    sorted_anomalies = sorted(anomalies, 
                             key=lambda x: x.get('severity_score', 0), 
                             reverse=True)[:limit]
    
    result = []
    for i, a in enumerate(sorted_anomalies, 1):
        result.append(f"""
{i}. ANOMALİ #{a.get('index', i)}
   Timestamp: {a.get('timestamp', 'N/A')}
   Component: {a.get('component', 'N/A')}
   Severity: {a.get('severity_score', 0):.1f} ({a.get('severity_level', 'N/A')})
   
   LOG MESAJI:
{a.get('message', 'Log mesajı mevcut değil')}

Context: {a.get('context', {}).get('operation', 'N/A')}
Anomaly Type: {a.get('anomaly_type', 'N/A')}
Host: {a.get('host', 'N/A')}
""")
    
    return "\n".join(result)

def _format_anomalies_with_full_messages(anomalies: list) -> str:
    """Anomalileri FULL LOG MESAJLARIYLA formatla"""
    result = []
    for i, a in enumerate(anomalies[:20], 1):  # İlk 20 anomali
        context = a.get('context', {})
        result.append(f"""
--- Anomali #{i} ---
Component: {a.get('component', 'N/A')} | Score: {a.get('severity_score', 0):.1f}
Timestamp: {a.get('timestamp', 'N/A')}
Operation: {context.get('operation', 'N/A')}

Log Mesajı:
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
    DBA'lar için spesifik zaman aralığı anomali analizi
    
    Örnek kullanım:
    /api/dba/analyze-specific-time?host=LCWMONGODB01&start_time=2025-09-15T16:09:00Z&end_time=2025-09-15T16:11:00Z&api_key=xxx
    """
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
                    data = res.get('sonuç', {})
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
                
                if res.get('durum') == 'başarılı' and 'sonuç' in res:
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
        critical_anomalies = result.get('sonuç', {}).get('critical_anomalies', [])
        anomaly_count = len(critical_anomalies)
        

        # LCWGPT ile her anomaliyi tek tek açıklama (30 anomali, chunk bazlı)
        ai_explanation = None
        if auto_explain and anomaly_count > 0:
            llm_connector = await get_llm_connector()
            if llm_connector:
                try:
                    # İlk 20 anomaliyi al
                    anomalies_to_analyze = critical_anomalies[:20]
                    chunk_size = 5
                    all_anomaly_explanations = []
                    
                    logger.info(f"Analyzing {len(anomalies_to_analyze)} anomalies individually in chunks of {chunk_size}")
                    
                    # Her chunk'ı işle
                    for chunk_idx, chunk_start in enumerate(range(0, len(anomalies_to_analyze), chunk_size)):
                        chunk_end = min(chunk_start + chunk_size, len(anomalies_to_analyze))
                        chunk = anomalies_to_analyze[chunk_start:chunk_end]
                        
                        chunk_prompt = f"""
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
                        
                        # Her anomaliyi detaylı ekle
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
                            'total_logs': total_logs if is_cluster else result.get('sonuç', {}).get('total_logs', 0),
                            'anomaly_count': anomaly_count,
                            'anomaly_rate': result.get('sonuç', {}).get('anomaly_rate', 0),
                            'host_breakdown': host_results if is_cluster else None
                        }
                    },
                    source_type='opensearch_dba',
                    host=host,
                    time_range=f"{start_time} to {end_time}"
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
                "total_logs_analyzed": total_logs if is_cluster else result.get('sonuç', {}).get('total_logs', 0),
                "anomaly_count": anomaly_count,
                "anomaly_rate": result.get('sonuç', {}).get('anomaly_rate', 0),
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
                "durum": request.get("result", {}).get("durum"),
                "işlem": request.get("result", {}).get("işlem"),
                "has_anomalies": bool(request.get("result", {}).get("sonuç", {}).get("critical_anomalies")),
                "anomaly_count": len(request.get("result", {}).get("sonuç", {}).get("critical_anomalies", [])),
                "total_logs": request.get("result", {}).get("sonuç", {}).get("total_logs", 0)
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
        if request.get("result", {}).get("sonuç", {}).get("critical_anomalies"):
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
    Clear all query history for a user/session
    """
    try:
        api_key = request.get("api_key")
        if not await verify_api_key(api_key):
            raise HTTPException(status_code=401, detail="Geçersiz API anahtarı")
        
        user_id = request.get("user_id")
        session_id = request.get("session_id")
        
        if not user_id and not session_id:
            raise HTTPException(status_code=400, detail="user_id or session_id required")
        
        storage = await get_storage_manager()
        if not storage or not storage.mongodb:
            raise HTTPException(status_code=503, detail="Storage not available")
        
        # Get all items to delete
        history = await storage.mongodb.get_query_history(
            user_id=user_id,
            session_id=session_id,
            limit=1000  # Max items to delete
        )
        
        deleted_count = 0
        for item in history:
            if await storage.mongodb.delete_query_history_item(item.get("query_id")):
                deleted_count += 1
        
        logger.info(f"✅ Cleared {deleted_count} query history items")
        
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "message": f"Cleared {deleted_count} items from history"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing query history: {e}")
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

# Startup event'e ekle
@app.on_event("startup")
async def startup_event():
    """Uygulama başlatıldığında"""
    # Session cleanup task'ı başlat
    asyncio.create_task(cleanup_expired_sessions())
    logger.info("Session cleanup task başlatıldı")
    
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
                
                # Model'i yükle
                success = anomaly_detector.load_model(str(model_path))
                
                if success:
                    # Model bilgilerini logla
                    model_info = anomaly_detector.get_model_info()  
                    
                    # 🔍 DEBUG: Model ve buffer durumunu detaylı logla
                    logger.info(f"🔍 DEBUG: Server-specific model yükleme sonrası durum kontrolü")
                    logger.info(f"   📍 Is trained: {anomaly_detector.is_trained}")
                    logger.info(f"   📍 Model instance ID: {id(anomaly_detector)}")
                    logger.info(f"   📍 Buffer enabled: {hasattr(anomaly_detector, 'historical_data')}")
                    if hasattr(anomaly_detector, 'historical_data') and anomaly_detector.historical_data:
                        buffer_metadata = anomaly_detector.historical_data.get('metadata', {})
                        logger.info(f"   📍 Buffer metadata: {buffer_metadata}")
                        logger.info(f"   📍 Buffer samples: {buffer_metadata.get('total_samples', 'N/A')}")
                    
                    logger.info(f"✅ Server-specific model loaded successfully!")
                    logger.info(f"   Server: {server_name}")
                    logger.info(f"   Model type: {model_info.get('model_type', 'Unknown')}")
                    logger.info(f"   Features: {model_info.get('n_features', 0)}")
                    logger.info(f"   Is trained: {model_info.get('is_trained', False)}")
                    
                    # Historical buffer bilgisi
                    buffer_info = anomaly_detector.get_historical_buffer_info()
                    if buffer_info.get('enabled'):
                        buffer_stats = buffer_info.get('buffer_stats', {})
                        logger.info(f"   Historical buffer: {buffer_stats.get('total_samples', 0)} samples")
                        logger.info(f"   Buffer size: {buffer_stats.get('size_mb', 0):.2f} MB")
                        logger.info(f"   Last update: {buffer_stats.get('last_update', 'N/A')}")
                else:
                    logger.warning(f"⚠️ Server-specific model file exists but could not be loaded: {latest_model}")
                    logger.info("Will try global model or train new model on first analysis")
                    
            elif (models_dir / "isolation_forest.pkl").exists():
                # Global model'i yükle
                global_model_path = models_dir / "isolation_forest.pkl"
                logger.info(f"📊 Found global model at: {global_model_path}")
                logger.info("Loading global model...")
                
                # Model'i yükle
                success = anomaly_detector.load_model(str(global_model_path))
                
                if success:
                    # Model bilgilerini logla
                    model_info = anomaly_detector.get_model_info()
                    
                    # 🔍 DEBUG: Global model ve buffer durumunu detaylı logla
                    logger.info(f"🔍 DEBUG: Global model yükleme sonrası durum kontrolü")
                    logger.info(f"   📍 Is trained: {anomaly_detector.is_trained}")
                    logger.info(f"   📍 Model instance ID: {id(anomaly_detector)}")
                    logger.info(f"   📍 Buffer enabled: {hasattr(anomaly_detector, 'historical_data')}")
                    if hasattr(anomaly_detector, 'historical_data') and anomaly_detector.historical_data:
                        buffer_metadata = anomaly_detector.historical_data.get('metadata', {})
                        logger.info(f"   📍 Buffer metadata: {buffer_metadata}")
                        logger.info(f"   📍 Buffer samples: {buffer_metadata.get('total_samples', 'N/A')}")
                    
                    logger.info("✅ Global model loaded successfully!")
                    logger.info(f"   Model type: {model_info.get('model_type', 'unknown')}")
                    logger.info(f"   Features: {model_info.get('n_features', 0)}")
                    logger.info(f"   Is trained: {model_info.get('is_trained', False)}")
                    
                    # Historical buffer bilgisi
                    buffer_info = anomaly_detector.get_historical_buffer_info()
                    if buffer_info.get('enabled'):
                        buffer_stats = buffer_info.get('buffer_stats', {})
                        logger.info(f"   Historical buffer: {buffer_stats.get('total_samples', 0)} samples")
                        logger.info(f"   Buffer size: {buffer_stats.get('size_mb', 0):.2f} MB")
                        logger.info(f"   Last update: {buffer_stats.get('last_update', 'N/A')}")
                else:
                    logger.warning("⚠️ Global model file exists but could not be loaded")
                    logger.info("Will train new model on first analysis")
            else:
                logger.info("📊 No existing models found at startup")
                logger.info(f"   Checked directory: {models_dir}")
                logger.info("   Will train new model on first analysis")
        else:
            logger.info(f"📊 Models directory created: {models_dir}")
            logger.info("   Will train new model on first analysis")
            
    except Exception as e:
        logger.error(f"Failed to initialize StorageManager: {e}")
        logger.error(f"❌ Error during model auto-load: {e}")
        logger.error(f"   Will train new model on first analysis")
        import traceback
        traceback.print_exc()

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