# src\agents\mongodb_agent.py

from typing import Dict, Any, List, Optional
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from ..connectors.mongodb_connector import MongoDBConnector
from ..connectors.openai_connector import OpenAIConnector
from .query_translator import QueryTranslator
from .query_validator import QueryValidator
from .schema_analyzer import SchemaAnalyzer
from .tools import get_all_tools

import logging

class MongoDBAgent:
    """MongoDB doğal dil sorgu agent'ı"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Bileşenleri başlat
        self.db_connector = MongoDBConnector()
        self.openai_connector = OpenAIConnector()
        self.validator = QueryValidator()
        self.analyzer = SchemaAnalyzer()
        self.translator = QueryTranslator()
        
        # Agent ve executor
        self.agent_executor = None
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="output"
        )
        
        # Agent system prompt
        self.system_prompt = """Sen MongoDB veritabanı asistanısın. Kullanıcıların doğal dil sorgularını MongoDB işlemlerine çevirip çalıştırıyorsun.

GÖREVLER:
1. Kullanıcının doğal dil sorgusunu anla
2. Uygun MongoDB işlemini belirle
3. Güvenli ve optimize edilmiş sorgular oluştur
4. Sonuçları anlaşılır şekilde sun

ARAÇLAR:
- mongodb_query: Sorgu çalıştırma (find, aggregate, count vb.)
- view_schema: Koleksiyon yapısını görüntüleme
- manage_indexes: Index yönetimi

KURALLAR:
- Her zaman önce schema'yı kontrol et
- Güvenlik uyarılarına dikkat et
- Büyük sonuç setleri için limit kullan
- Hataları kullanıcı dostu açıkla

ÖRNEK KULLANIMLAR:
- "users koleksiyonunda 30 yaşından büyükleri bul" → mongodb_query ile find
- "products tablosunun yapısını göster" → view_schema
- "orders'da date alanına index ekle" → manage_indexes

Kullanıcıyla Türkçe iletişim kur. Teknik terimleri açıkla."""
    
    def initialize(self) -> bool:
        """Agent'ı başlat"""
        try:
            # Bağlantıları kur
            self.logger.info("MongoDB bağlantısı kuruluyor...")
            if not self.db_connector.connect():
                self.logger.error("MongoDB bağlantısı başarısız")
                return False
            
            self.logger.info("OpenAI bağlantısı kuruluyor...")
            if not self.openai_connector.connect():
                self.logger.error("OpenAI bağlantısı başarısız")
                return False
            
            # Bileşenleri bağla
            self.analyzer.set_database(self.db_connector.database)
            self.translator.set_llm(self.openai_connector.llm)
            
            # Agent'ı oluştur
            self._create_agent()
            
            self.logger.info("MongoDB Agent başarıyla başlatıldı")
            return True
            
        except Exception as e:
            self.logger.error(f"Başlatma hatası: {e}")
            return False
        
    def _create_agent(self):
        """LangChain agent'ı oluştur"""
        try:
            # Tool'ları al
            tools = get_all_tools(
                self.db_connector,
                self.validator,
                self.analyzer
            )
            
            # Prompt template oluştur
            prompt = ChatPromptTemplate.from_messages([
                ("system", self.system_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad")
            ])
            
            # Agent oluştur
            agent = create_openai_tools_agent(
                llm=self.openai_connector.llm,
                tools=tools,
                prompt=prompt
            )
            
            # Agent executor oluştur
            self.agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                memory=self.memory,
                verbose=True,
                max_iterations=5,
                handle_parsing_errors=True,
                return_intermediate_steps=True
            )
            
            self.logger.info("Agent başarıyla oluşturuldu")
            
        except Exception as e:
            self.logger.error(f"Agent oluşturma hatası: {e}")
            raise
    
    def process_query(self, user_input: str) -> Dict[str, Any]:
        """Kullanıcı sorgusunu işle"""
        try:
            # Boş sorgu kontrolü
            if not user_input or not user_input.strip():
                return {
                    "durum": "hata",
                    "işlem": "sorgu_işleme",
                    "açıklama": "Lütfen bir sorgu girin",
                    "sonuç": None
                }
            
            # Bağlantı kontrolü
            if not self._check_connections():
                return {
                    "durum": "hata",
                    "işlem": "bağlantı_kontrolü",
                    "açıklama": "Veritabanı bağlantısı kurulamadı",
                    "sonuç": None
                }
            
            # Agent'ı çalıştır
            self.logger.info(f"Sorgu işleniyor: {user_input[:100]}...")
            
            result = self.agent_executor.invoke({
                "input": user_input
            })
            
            # Sonucu formatla
            return self._format_response(result)
            
        except Exception as e:
            self.logger.error(f"Sorgu işleme hatası: {e}")
            return {
                "durum": "hata",
                "işlem": "sorgu_işleme",
                "açıklama": f"İşlem sırasında hata oluştu: {str(e)}",
                "sonuç": None,
                "öneriler": ["Sorgunuzu basitleştirmeyi deneyin", "Koleksiyon adını kontrol edin"]
            }
    
    def _check_connections(self) -> bool:
        """Bağlantıları kontrol et ve gerekirse yenile"""
        try:
            # MongoDB bağlantısı
            if not self.db_connector.is_connected():
                self.logger.warning("MongoDB bağlantısı kopuk, yenileniyor...")
                if not self.db_connector.connect():
                    return False
            
            # OpenAI bağlantısı
            if not self.openai_connector.is_connected():
                self.logger.warning("OpenAI bağlantısı kopuk, yenileniyor...")
                if not self.openai_connector.connect():
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Bağlantı kontrolü hatası: {e}")
            return False
    
    def _format_response(self, agent_result: Dict) -> Dict[str, Any]:
        """Agent sonucunu standart formata dönüştür"""
        try:
            # Agent çıktısını al
            output = agent_result.get("output", "")
            
            # JSON formatında mı kontrol et
            try:
                import json
                response = json.loads(output)
                # Zaten doğru formatta
                if all(key in response for key in ["durum", "işlem", "açıklama"]):
                    return response
            except:
                pass
            
            # Standart format oluştur
            return {
                "durum": "başarılı",
                "işlem": "sorgu_tamamlandı",
                "açıklama": output,
                "sonuç": {
                    "intermediate_steps": len(agent_result.get("intermediate_steps", [])),
                    "tools_used": [
                        step[0].tool for step in agent_result.get("intermediate_steps", [])
                    ]
                }
            }
            
        except Exception as e:
            self.logger.error(f"Response formatlama hatası: {e}")
            return {
                "durum": "uyarı",
                "işlem": "formatlama",
                "açıklama": str(agent_result),
                "sonuç": None
            }
    def get_available_collections(self) -> List[str]:
        """Mevcut koleksiyonları döndür"""
        try:
            if not self._check_connections():
                return []
            
            return self.analyzer.get_available_collections()
            
        except Exception as e:
            self.logger.error(f"Koleksiyon listesi hatası: {e}")
            return []
    
    def analyze_collection(self, collection_name: str, detailed: bool = False) -> Dict[str, Any]:
        """Koleksiyon şemasını analiz et"""
        try:
            if not self._check_connections():
                return {"error": "Bağlantı hatası"}
            
            if detailed:
                return self.analyzer.analyze_collection_schema_advanced(collection_name)
            else:
                return self.analyzer.analyze_collection_schema(collection_name)
                
        except Exception as e:
            self.logger.error(f"Koleksiyon analizi hatası: {e}")
            return {"error": str(e)}
    
    def translate_natural_query(self, query: str) -> Dict[str, Any]:
        """Doğal dil sorgusunu MongoDB sorgusuna çevir (test için)"""
        try:
            collections = self.get_available_collections()
            
            # Schema ipuçları topla
            schema_hints = {}
            for coll in collections[:5]:  # İlk 5 koleksiyon
                schema_hints[coll] = self.analyzer.analyze_collection_schema(coll)
            
            return self.translator.translate_query(query, collections, schema_hints)
            
        except Exception as e:
            self.logger.error(f"Çeviri hatası: {e}")
            return {"error": str(e)}
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """Konuşma geçmişini döndür"""
        try:
            messages = self.memory.chat_memory.messages
            history = []
            
            for msg in messages:
                if hasattr(msg, "content"):
                    history.append({
                        "type": msg.__class__.__name__,
                        "content": msg.content
                    })
            
            return history
            
        except Exception as e:
            self.logger.error(f"Geçmiş okuma hatası: {e}")
            return []
    
    def clear_conversation_history(self):
        """Konuşma geçmişini temizle"""
        try:
            self.memory.clear()
            self.logger.info("Konuşma geçmişi temizlendi")
            
        except Exception as e:
            self.logger.error(f"Geçmiş temizleme hatası: {e}")
    
    def shutdown(self):
        """Agent'ı güvenli şekilde kapat"""
        try:
            self.logger.info("MongoDB Agent kapatılıyor...")
            
            # Bağlantıları kapat
            if self.db_connector:
                self.db_connector.disconnect()
            
            if self.openai_connector:
                self.openai_connector.disconnect()
            
            # Belleği temizle
            if self.memory:
                self.memory.clear()
            
            self.logger.info("MongoDB Agent kapatıldı")
            
        except Exception as e:
            self.logger.error(f"Kapatma hatası: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Agent durumunu döndür"""
        return {
            "mongodb_connected": self.db_connector.is_connected() if self.db_connector else False,
            "openai_connected": self.openai_connector.is_connected() if self.openai_connector else False,
            "agent_ready": self.agent_executor is not None,
            "conversation_length": len(self.memory.chat_memory.messages) if self.memory else 0,
            "available_tools": [
                "mongodb_query",
                "view_schema", 
                "manage_indexes"
            ]
        }


