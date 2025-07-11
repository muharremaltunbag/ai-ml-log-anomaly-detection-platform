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
            self.logger.debug("MongoDB connector durumu kontrol ediliyor...")
            if not self.db_connector.connect():
                self.logger.error("MongoDB bağlantısı başarısız")
                return False
            self.logger.debug("MongoDB bağlantısı başarılı")
            
            self.logger.info("OpenAI bağlantısı kuruluyor...")
            self.logger.debug("OpenAI connector durumu kontrol ediliyor...")
            if not self.openai_connector.connect():
                self.logger.error("OpenAI bağlantısı başarısız")
                return False
            self.logger.debug("OpenAI bağlantısı başarılı")
            
            # Bileşenleri bağla
            self.logger.debug("Schema analyzer veritabanı bağlantısı ayarlanıyor...")
            self.analyzer.set_database(self.db_connector.database)
            self.logger.debug("Query translator LLM bağlantısı ayarlanıyor...")
            self.translator.set_llm(self.openai_connector.llm)
            
            # Agent'ı oluştur
            self.logger.debug("Agent oluşturma işlemi başlatılıyor...")
            self._create_agent()
            
            self.logger.info("MongoDB Agent başarıyla başlatıldı")
            return True
            
        except Exception as e:
            self.logger.error(f"Başlatma hatası: {e}")
            self.logger.debug(f"Başlatma hatası detayı: {e}", exc_info=True)
            return False

    def _create_agent(self):
        """LangChain agent'ı oluştur"""
        try:
            # Tool'ları al
            self.logger.debug("Agent araçları yükleniyor...")
            tools = get_all_tools(
                self.db_connector,
                self.validator,
                self.analyzer
            )
            self.logger.debug(f"{len(tools)} araç yüklendi: {[tool.name for tool in tools]}")
            
            # Prompt template oluştur
            self.logger.debug("Prompt template oluşturuluyor...")
            prompt = ChatPromptTemplate.from_messages([
                ("system", self.system_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad")
            ])
            
            # Agent oluştur
            self.logger.debug("OpenAI tools agent oluşturuluyor...")
            agent = create_openai_tools_agent(
                llm=self.openai_connector.llm,
                tools=tools,
                prompt=prompt
            )
            
            # Agent executor oluştur
            self.logger.debug("Agent executor oluşturuluyor...")
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
            self.logger.debug(f"Agent oluşturma hatası detayı: {e}", exc_info=True)
            raise

    def process_query(self, user_input: str) -> Dict[str, Any]:
        """Kullanıcı sorgusunu işle"""
        try:
            # Boş sorgu kontrolü
            if not user_input or not user_input.strip():
                self.logger.debug("Boş sorgu tespit edildi")
                return {
                    "durum": "hata",
                    "işlem": "sorgu_işleme",
                    "açıklama": "Lütfen bir sorgu girin",
                    "sonuç": None
                }
            
            # Bağlantı kontrolü
            self.logger.debug("Bağlantı durumu kontrol ediliyor...")
            if not self._check_connections():
                self.logger.debug("Bağlantı kontrolü başarısız")
                return {
                    "durum": "hata",
                    "işlem": "bağlantı_kontrolü",
                    "açıklama": "Veritabanı bağlantısı kurulamadı",
                    "sonuç": None
                }
            self.logger.debug("Bağlantılar aktif")
            
            # Agent'ı çalıştır
            self.logger.info(f"Sorgu işleniyor: {user_input[:100]}...")
            self.logger.debug(f"Tam sorgu: {user_input}")
            
            result = self.agent_executor.invoke({
                "input": user_input
            })
            
            self.logger.debug(f"Agent sonucu alındı, intermediate steps: {len(result.get('intermediate_steps', []))}")
            
            # Sonucu formatla
            formatted_result = self._format_response(result)
            self.logger.debug(f"Formatlanmış sonuç durumu: {formatted_result.get('durum')}")
            return formatted_result
            
        except Exception as e:
            self.logger.error(f"Sorgu işleme hatası: {e}")
            self.logger.debug(f"Sorgu işleme hatası detayı: {e}", exc_info=True)
            return {
                "durum": "hata",
                "işlem": "sorgu_işleme",
                "açıklama": f"İşlem sırasında hata oluştu: {str(e)}",
                "sonuç": None,
                "öneriler": ["Sorgunuzu basitleştirmeyi deneyin", "Koleksiyon adını kontrol edin"]
            }

    def process_query_with_args(self, user_input: str, additional_args: Dict[str, Any]) -> Dict[str, Any]:
        """SSH config gibi ek parametrelerle sorgu işle"""
        try:
            # Boş sorgu kontrolü
            if not user_input or not user_input.strip():
                self.logger.debug("Boş sorgu tespit edildi (with args)")
                return {
                    "durum": "hata",
                    "işlem": "sorgu_işleme",
                    "açıklama": "Lütfen bir sorgu girin",
                    "sonuç": None
                }
            
            # Bağlantı kontrolü
            self.logger.debug("Bağlantı durumu kontrol ediliyor (with args)...")
            if not self._check_connections():
                self.logger.debug("Bağlantı kontrolü başarısız (with args)")
                return {
                    "durum": "hata",
                    "işlem": "bağlantı_kontrolü",
                    "açıklama": "Veritabanı bağlantısı kurulamadı",
                    "sonuç": None
                }
            
            # Anomaly detection sorgularını tespit et
            is_anomaly_query = any(keyword in user_input.lower() for keyword in [
                'anomali', 'anomaly', 'log', 'analiz', 'train', 'model'
            ])
            self.logger.debug(f"Anomaly sorgusu tespit edildi: {is_anomaly_query}")
            
            # YENİ: Veri kaynağı parametrelerini ekle
            if is_anomaly_query:
                self.logger.debug("Anomaly parametreleri hazırlanıyor...")
                enhanced_input = user_input
                
                # Anomaly tool'a gönderilecek parametreleri hazırla
                anomaly_params = {
                    "time_range": additional_args.get('time_range', 'last_day')
                }
                
                # Veri kaynağına göre parametreleri ekle
                source_type = additional_args.get('source_type', 'file')
                anomaly_params['source_type'] = source_type
                self.logger.debug(f"Veri kaynağı türü: {source_type}")
                
                if source_type == 'upload':
                    anomaly_params['file_path'] = additional_args.get('uploaded_file_path')
                elif source_type == 'file':
                    anomaly_params['file_path'] = additional_args.get('file_path')
                elif source_type == 'mongodb_direct':
                    anomaly_params['connection_string'] = additional_args.get('connection_string')
                elif source_type == 'test_servers':
                    anomaly_params['server_name'] = additional_args.get('server_name')
                
                # Train komutları için özel
                if 'train' in user_input.lower() or 'model' in user_input.lower():
                    anomaly_params['sample_size'] = 10000
                    self.logger.debug("Train modu parametreleri eklendi")
                
                # Parametreleri JSON string olarak ekle
                import json
                params_str = json.dumps(anomaly_params)
                enhanced_input = f"{user_input} {params_str}"
                self.logger.debug(f"Parametrelerle genişletilmiş sorgu hazırlandı")
                
            else:
                enhanced_input = user_input
                self.logger.debug("Normal sorgu modunda devam ediliyor")
            
            # Agent'ı çalıştır
            self.logger.info(f"Sorgu işleniyor: {enhanced_input[:100]}...")
            self.logger.debug(f"Tam enhanced sorgu: {enhanced_input}")
            
            result = self.agent_executor.invoke({
                "input": enhanced_input
            })
            
            self.logger.debug(f"Agent sonucu alındı (with args), intermediate steps: {len(result.get('intermediate_steps', []))}")
            
            # Sonucu formatla
            formatted_result = self._format_response(result)
            self.logger.debug(f"Formatlanmış sonuç durumu (with args): {formatted_result.get('durum')}")
            return formatted_result
            
        except Exception as e:
            self.logger.error(f"Sorgu işleme hatası: {e}")
            self.logger.debug(f"Sorgu işleme hatası detayı (with args): {e}", exc_info=True)
            return {
                "durum": "hata",
                "işlem": "sorgu_işleme",
                "açıklama": f"İşlem sırasında hata oluştu: {str(e)}",
                "sonuç": None,
                "öneriler": ["Veri kaynağı parametrelerini kontrol edin"]
            }

    def _check_connections(self) -> bool:
        """Bağlantıları kontrol et ve gerekirse yenile"""
        try:
            # MongoDB bağlantısı
            mongodb_status = self.db_connector.is_connected()
            self.logger.debug(f"MongoDB bağlantı durumu: {mongodb_status}")
            if not mongodb_status:
                self.logger.warning("MongoDB bağlantısı kopuk, yenileniyor...")
                if not self.db_connector.connect():
                    self.logger.debug("MongoDB yeniden bağlantı başarısız")
                    return False
                self.logger.debug("MongoDB yeniden bağlantı başarılı")
            
            # OpenAI bağlantısı
            openai_status = self.openai_connector.is_connected()
            self.logger.debug(f"OpenAI bağlantı durumu: {openai_status}")
            if not openai_status:
                self.logger.warning("OpenAI bağlantısı kopuk, yenileniyor...")
                if not self.openai_connector.connect():
                    self.logger.debug("OpenAI yeniden bağlantı başarısız")
                    return False
                self.logger.debug("OpenAI yeniden bağlantı başarılı")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Bağlantı kontrolü hatası: {e}")
            self.logger.debug(f"Bağlantı kontrolü hatası detayı: {e}", exc_info=True)
            return False

    def _format_response(self, agent_result: Dict) -> Dict[str, Any]:
        """Agent sonucunu standart formata dönüştür"""
        try:
            # Agent çıktısını al
            output = agent_result.get("output", "")
            self.logger.debug(f"Agent çıktısı uzunluğu: {len(output)} karakter")
            
            # JSON formatında mı kontrol et
            try:
                import json
                response = json.loads(output)
                # Zaten doğru formatta
                if all(key in response for key in ["durum", "işlem", "açıklama"]):
                    self.logger.debug("Çıktı zaten doğru JSON formatında")
                    return response
            except:
                self.logger.debug("Çıktı JSON formatında değil, standart formatlama yapılacak")
                pass
            
            # Standart format oluştur
            intermediate_steps_count = len(agent_result.get("intermediate_steps", []))
            tools_used = [
                step[0].tool for step in agent_result.get("intermediate_steps", [])
            ]
            self.logger.debug(f"Standart format oluşturuluyor: {intermediate_steps_count} adım, {len(tools_used)} araç kullanıldı")
            
            return {
                "durum": "başarılı",
                "işlem": "sorgu_tamamlandı",
                "açıklama": output,
                "sonuç": {
                    "intermediate_steps": intermediate_steps_count,
                    "tools_used": tools_used
                }
            }
            
        except Exception as e:
            self.logger.error(f"Response formatlama hatası: {e}")
            self.logger.debug(f"Response formatlama hatası detayı: {e}", exc_info=True)
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
            message_count = len(self.memory.chat_memory.messages) if self.memory else 0
            self.logger.debug(f"Konuşma geçmişi temizleniyor: {message_count} mesaj")
            self.memory.clear()
            self.logger.info("Konuşma geçmişi temizlendi")
            
        except Exception as e:
            self.logger.error(f"Geçmiş temizleme hatası: {e}")
            self.logger.debug(f"Geçmiş temizleme hatası detayı: {e}", exc_info=True)

    def shutdown(self):
        """Agent'ı güvenli şekilde kapat"""
        try:
            self.logger.info("MongoDB Agent kapatılıyor...")
            
            # Bağlantıları kapat
            if self.db_connector:
                self.logger.debug("MongoDB bağlantısı kapatılıyor...")
                self.db_connector.disconnect()
            
            if self.openai_connector:
                self.logger.debug("OpenAI bağlantısı kapatılıyor...")
                self.openai_connector.disconnect()
            
            # Belleği temizle
            if self.memory:
                self.logger.debug("Agent belleği temizleniyor...")
                self.memory.clear()
            
            self.logger.info("MongoDB Agent kapatıldı")
            
        except Exception as e:
            self.logger.error(f"Kapatma hatası: {e}")
            self.logger.debug(f"Kapatma hatası detayı: {e}", exc_info=True)

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
                "manage_indexes",
                "check_server_status",
                "get_server_metrics",
                "find_resource_intensive_processes",
                "execute_monitoring_command",
                "get_servers_by_tag",
                "analyze_query_performance",
                "get_slow_queries",
                "analyze_mongodb_logs",
                "get_anomaly_summary",
                "train_anomaly_model"
            ]
        }


