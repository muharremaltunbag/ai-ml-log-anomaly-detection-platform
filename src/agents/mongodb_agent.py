# src\agents\mongodb_agent.py

from typing import Dict, Any, List, Optional, Tuple
from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain.memory import ConversationBufferMemory
from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from ..connectors.mongodb_connector import MongoDBConnector
from ..connectors.openai_connector import OpenAIConnector
from ..connectors.lcwgpt_connector import LCWGPTConnector
from .query_translator import QueryTranslator
from .query_validator import QueryValidator
from .schema_analyzer import SchemaAnalyzer
from .tools import get_all_tools

import logging

class MongoDBAgent:
    """MongoDB doğal dil sorgu agent'ı"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # MongoDB bağlantı durumu için flag ekle
        self.mongodb_connected = False
        
        # Bileşenleri başlat
        self.db_connector = MongoDBConnector()
        # YENİ: LCWGPT kullan, OpenAI yerine
        self.llm_connector = LCWGPTConnector()  # OpenAI yerine LCWGPT
        self.openai_connector = self.llm_connector  # Geriye uyumluluk için
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
            # MongoDB bağlantısını dene (opsiyonel)
            self.logger.info("MongoDB bağlantısı kuruluyor...")
            self.logger.debug("MongoDB connector durumu kontrol ediliyor...")
            if self.db_connector.connect():
                self.logger.info("MongoDB bağlantısı başarılı")
                self.mongodb_connected = True
            else:
                self.logger.warning("MongoDB bağlantısı başarısız - Sistem MongoDB olmadan devam edecek")
                self.mongodb_connected = False
                # MongoDB bağlantısı başarısız olsa bile devam et
            
            # LLM bağlantısı (zorunlu) - LCWGPT kullanılıyor
            self.logger.info("LCWGPT bağlantısı kuruluyor...")
            self.logger.debug("LCWGPT connector durumu kontrol ediliyor...")
            if not self.llm_connector.connect():
                self.logger.error("LCWGPT bağlantısı başarısız")
                return False
            self.logger.debug("LCWGPT bağlantısı başarılı")
            
            # Bileşenleri bağla
            self.logger.debug("Schema analyzer veritabanı bağlantısı ayarlanıyor...")
            self.analyzer.set_database(self.db_connector.database)
            self.logger.debug("Query translator LLM bağlantısı ayarlanıyor...")
            self.translator.set_llm(self.llm_connector.llm)
            
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
            self.logger.debug("LCWGPT tools agent oluşturuluyor...")
            agent = create_openai_tools_agent(
                llm=self.llm_connector.llm,  # LCWGPT kullan
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
            
            # YENİ: Onay kontrolü
            if additional_args.get('confirmation_required'):
                # Onay yanıtını kontrol et
                user_response = user_input.lower().strip()
                if user_response in ['evet', 'onay', 'başlat', 'yes']:
                    self.logger.info("Kullanıcı onayı alındı, anomali analizi başlatılıyor")
                    # Onaylanmış parametrelerle devam et
                    user_input = "MongoDB loglarında anomali analizi yap"
                    additional_args['confirmation_required'] = False
                elif user_response in ['hayır', 'iptal', 'dur', 'no']:
                    self.logger.info("Kullanıcı analizi iptal etti")
                    return {
                        "durum": "iptal",
                        "işlem": "anomali_analizi",
                        "açıklama": "Anomali analizi iptal edildi. Yeni bir sorgu girebilirsiniz.",
                        "sonuç": None
                    }
                else:
                    # Yeni parametre girişi
                    self.logger.info("Kullanıcı yeni parametreler giriyor")
                    additional_args['confirmation_required'] = False
                    # Normal akışa devam et
            
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
            
            # YENİ: Doğal dilden parametre çıkarımı
            if is_anomaly_query and not additional_args.get('params_extracted'):
                self.logger.info("Doğal dilden parametre çıkarımı başlatılıyor")
                
                # Sunucu ve zaman çıkar
                detected_server = self._extract_server_from_query(user_input)
                time_range, readable_time = self._extract_time_range_from_query(user_input)
                
                # Onay mesajı oluştur ve döndür
                confirmation_msg = self._create_confirmation_message(
                    detected_server, time_range, readable_time
                )
                
                # Parametreleri sakla
                additional_args['detected_server'] = detected_server
                additional_args['detected_time_range'] = time_range
                additional_args['confirmation_required'] = True
                additional_args['params_extracted'] = True
                
                return {
                    "durum": "onay_bekliyor",
                    "işlem": "parametre_tespiti",
                    "açıklama": confirmation_msg,
                    "sonuç": {
                        "server": detected_server,
                        "time_range": time_range,
                        "readable_time": readable_time
                    },
                    "öneriler": [
                        "Parametreler doğruysa 'evet' yazın",
                        "Farklı parametreler için yeni sorgu girin"
                    ]
                }
            
            # YENİ: Veri kaynağı parametrelerini ekle
            if is_anomaly_query:
                self.logger.debug("Anomaly parametreleri hazırlanıyor...")
                enhanced_input = user_input
                
                # YENİ: Tespit edilen parametreleri kullan
                if additional_args.get('detected_server') is not None:
                    # Onaylanmış parametreler mevcut
                    self.logger.info("Tespit edilen parametreler kullanılıyor")
                    time_range = additional_args.get('detected_time_range', 'last_day')
                    host_filter = additional_args.get('detected_server')  # None olabilir (tüm sunucular)
                else:
                    # Eski yöntem - manuel parametreler
                    time_range = additional_args.get('time_range', 'last_day')
                    host_filter = additional_args.get('host_filter')
                
                # Anomaly tool'a gönderilecek parametreleri hazırla
                anomaly_params = {
                    "time_range": time_range
                }
                
                # YENİ: OpenSearch varsayılan veri kaynağı olarak ayarla
                source_type = additional_args.get('source_type', 'opensearch')  # 'file' yerine 'opensearch'
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
                elif source_type == 'opensearch':
                    # YENİ: Host filter'ı ekle
                    if host_filter:
                        anomaly_params['host_filter'] = host_filter
                        self.logger.info(f"OpenSearch host filter ayarlandı: {host_filter}")
                    else:
                        self.logger.info("Tüm MongoDB sunucuları için analiz yapılacak")
                
                # Host filter varsa ekle (tüm kaynaklar için) - GÜNCELLEME
                if host_filter and source_type != 'opensearch':  # OpenSearch için zaten eklendi
                    anomaly_params['host_filter'] = host_filter
                    self.logger.debug(f"Host filter eklendi: {anomaly_params['host_filter']}")
                
                # Train komutları için özel
                if 'train' in user_input.lower() or 'model' in user_input.lower():
                    anomaly_params['sample_size'] = 10000
                    self.logger.debug("Train modu parametreleri eklendi")
                
                # Parametreleri JSON string olarak ekle
                import json
                params_str = json.dumps(anomaly_params)
                
                # YENİ: Sunucu bilgisini açık şekilde belirt
                if host_filter:
                    # Sunucu adını sorguya açık şekilde ekle
                    server_info = f" (Sunucu: {host_filter})"
                    enhanced_input = f"{user_input}{server_info} {params_str}"
                    self.logger.info(f"✅ Sunucu bilgisi sorguya eklendi: {host_filter}")
                else:
                    # Tüm sunucular için
                    server_info = " (Tüm MongoDB sunucuları)"
                    enhanced_input = f"{user_input}{server_info} {params_str}"
                    self.logger.info("📊 Tüm sunucular için analiz yapılacak")
                
                self.logger.debug(f"Parametrelerle genişletilmiş sorgu: {enhanced_input[:200]}...")
                
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
            # MongoDB bağlantısı (opsiyonel)
            if self.mongodb_connected:
                mongodb_status = self.db_connector.is_connected()
                self.logger.debug(f"MongoDB bağlantı durumu: {mongodb_status}")
                if not mongodb_status:
                    self.logger.warning("MongoDB bağlantısı kopuk, yenileniyor...")
                    if not self.db_connector.connect():
                        self.logger.warning("MongoDB yeniden bağlantı başarısız - Devam ediliyor")
                        self.mongodb_connected = False
                    else:
                        self.logger.debug("MongoDB yeniden bağlantı başarılı")
                        self.mongodb_connected = True
            
            # LLM bağlantısı
            llm_status = self.llm_connector.is_connected()
            self.logger.debug(f"LCWGPT bağlantı durumu: {llm_status}")
            if not llm_status:
                self.logger.warning("LCWGPT bağlantısı kopuk, yenileniyor...")
                if not self.llm_connector.connect():
                    self.logger.debug("LCWGPT yeniden bağlantı başarısız")
                    return False
                self.logger.debug("LCWGPT yeniden bağlantı başarılı")
            
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
                    
                    # YENİ: Anomali analizi sonuçlarını formatla
                    if response.get('işlem') == 'anomaly_analysis':
                        return self._format_anomaly_response(response)
                    
                    return response
            except json.JSONDecodeError:
                self.logger.debug("Çıktı JSON formatında değil, standart formatlama yapılacak")
                pass
            
            # YENİ: Output içinde gömülü JSON var mı kontrol et
            try:
                # Output içinde JSON pattern'i ara
                import re
                json_pattern = r'\{[^{}]*"durum"[^{}]*\}'
                json_match = re.search(json_pattern, output, re.DOTALL)
                
                if json_match:
                    # JSON kısmını çıkar ve parse et
                    json_str = json_match.group(0)
                    # En dıştaki { } arasındaki her şeyi al
                    start_idx = output.find('{')
                    end_idx = output.rfind('}')
                    if start_idx != -1 and end_idx != -1:
                        json_str = output[start_idx:end_idx+1]
                        response = json.loads(json_str)
                        
                        if all(key in response for key in ["durum", "işlem", "açıklama"]):
                            self.logger.debug("Output içinde gömülü JSON bulundu ve parse edildi")
                            
                            # Anomali analizi ise özel formatlama
                            if response.get('işlem') == 'anomaly_analysis':
                                return self._format_anomaly_response(response)
                            
                            return response
            except Exception as e:
                self.logger.debug(f"Gömülü JSON parse hatası: {e}")
            
            # YENİ: Tool response'larını kontrol et
            if agent_result.get("intermediate_steps"):
                for step in agent_result.get("intermediate_steps", []):
                    if len(step) >= 2 and hasattr(step[0], 'tool'):
                        tool_name = step[0].tool
                        tool_output = step[1]
                        
                        # Anomaly tool response'unu kontrol et
                        if 'analyze_mongodb_logs' in tool_name:
                            self.logger.debug(f"Anomaly tool response found, parsing...")
                            try:
                                # Tool output bir string ise parse et
                                if isinstance(tool_output, str):
                                    # JSON kısmını bul
                                    start_idx = tool_output.find('{')
                                    end_idx = tool_output.rfind('}')
                                    if start_idx != -1 and end_idx != -1:
                                        json_str = tool_output[start_idx:end_idx+1]
                                        tool_response = json.loads(json_str)
                                        
                                        # Tool response'ta AI explanation var mı?
                                        if isinstance(tool_response, dict) and tool_response.get('sonuç', {}).get('ai_explanation'):
                                            self.logger.debug("AI explanation found in tool response!")
                                            # Tool response'u direkt döndür
                                            return tool_response
                            except Exception as e:
                                self.logger.debug(f"Tool response parse error: {e}")
            # Standart format oluştur
            intermediate_steps_count = len(agent_result.get("intermediate_steps", []))
            tools_used = [
                step[0].tool for step in agent_result.get("intermediate_steps", [])
            ]
            self.logger.debug(f"Standart format oluşturuluyor: {intermediate_steps_count} adım, {len(tools_used)} araç kullanıldı")
            
            # Tool'lardan anomaly tool kullanıldı mı kontrol et
            is_anomaly_result = any('analyze_mongodb_logs' in tool for tool in tools_used)

            # İşlem tipini belirle
            operation_type = "anomaly_analysis" if is_anomaly_result else "sorgu_tamamlandı"
            
            return {
                "durum": "başarılı",
                "işlem": operation_type,
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

    def _format_anomaly_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Anomali analizi sonuçlarını kullanıcı dostu formata dönüştür"""
        try:
            # Eğer zaten formatlanmışsa direkt döndür
            if response.get('işlem') == 'anomaly_analysis':
                return response
            
            # Açıklama metnini parse et
            description = response.get('açıklama', '')
            result_data = response.get('sonuç', {})
            
            # Kullanıcı dostu özet oluştur
            if isinstance(result_data, dict) and 'summary' in result_data:
                summary = result_data['summary']
                anomaly_count = summary.get('n_anomalies', 0)
                anomaly_rate = summary.get('anomaly_rate', 0)
                total_logs = summary.get('total_logs', 0)
                
                # Kritik anomaliler varsa vurgula
                critical_count = len(result_data.get('critical_anomalies', []))
                security_alerts = result_data.get('security_alerts', {})
                
                user_friendly_text = f"""
🔍 **Anomali Analizi Tamamlandı**

📊 **Analiz Özeti:**
- Toplam Log Sayısı: {total_logs:,}
- Tespit Edilen Anomali: {anomaly_count:,} (%{anomaly_rate:.1f})
- Kritik Anomali: {critical_count}
"""
                
                if security_alerts:
                    user_friendly_text += "\n⚠️ **GÜVENLİK UYARISI:** DROP operasyonları tespit edildi!\n"
                
                # Önerileri ekle
                if response.get('öneriler'):
                    user_friendly_text += "\n💡 **Öneriler:**\n"
                    for öneri in response['öneriler']:
                        user_friendly_text += f"- {öneri}\n"
                
                response['açıklama'] = user_friendly_text
            
            return response
            
        except Exception as e:
            self.logger.error(f"Anomaly response formatlama hatası: {e}")
            return response

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
            
            if self.llm_connector:
                self.logger.debug("LCWGPT bağlantısı kapatılıyor...")
                self.llm_connector.disconnect()
            
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
            "mongodb_connected": self.mongodb_connected,
            "llm_connected": self.llm_connector.is_connected() if self.llm_connector else False,
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

    def _extract_server_from_query(self, query: str) -> Optional[str]:
        """Doğal dil sorgusundan MongoDB sunucu adını çıkar"""
        import re
        
        # Sunucu isim kalıpları
        server_patterns = [
            r'(lcwmongodb\d+n\d+)',  # lcwmongodb01n2 formatı
            r'(ECOMLOGMNG\d+)',       # ECOMLOGMNG01 formatı
            r'(testmongodb\d+)',      # testmongodb01 formatı
            r'(NTFCMONGODB\d+)',      # NTFCMONGODB01 formatı
            r'([A-Z]+MONGODB\d+)',    # Genel MongoDB sunucu formatı
            r'(pplazmongodbn\d+)',    # pplazmongodbn2 formatı (FQDN'siz)
            r'(pplmongodbn\d+)',      # pplmongodbn1 formatı (FQDN'li)
            r'(ecfavmngdbn\d+)',      # ecfavmngdbn3 formatı
            r'(hqsectwrapmdbn\d+)',   # hqsectwrapmdbn1 formatı
            r'(kznmongodbn\d+)',      # kznmongodbn1 formatı
            r'([a-z]+mongo\d+)',      # kzmongo02, rumongo02 formatı
        ]
        
        query_lower = query.lower()
        query_original = query
        
        # Pattern matching
        for pattern in server_patterns:
            # Case-insensitive arama
            match = re.search(pattern, query_original, re.IGNORECASE)
            if match:
                server_name = match.group(1)
                self.logger.debug(f"Sunucu tespit edildi: {server_name}")
                
                # FQDN kontrolü ve ekleme mantığı
                # Whitelist yaklaşımı - belirli pattern'lere .lcwaikiki.local ekle
                server_lower = server_name.lower()
                
                # Zaten FQDN varsa ekleme
                if not server_name.endswith('.lcwaikiki.local'):
                    # FQDN eklenmesi gereken pattern'ler (whitelist)
                    fqdn_required_patterns = [
                        r'^lcwmongodb\d+n\d+$',           # lcwmongodb01n2
                        r'^testmongodb\d+$',               # testmongodb01
                        r'^devmongodb\d+$',                # devmongodb02
                        r'^pplmongodbn\d+$',               # pplmongodbn1 (az'sız olanlar!)
                        r'^kznmongodbn\d+$',               # kznmongodbn1, KZNMONGODBN2
                        r'^ntfcmongodb\d+$',               # NTFCMONGODB01 (karışık durum)
                    ]
                    
                    # Pattern kontrolü
                    for fqdn_pattern in fqdn_required_patterns:
                        if re.match(fqdn_pattern, server_lower):
                            server_name = f"{server_name}.lcwaikiki.local"
                            self.logger.debug(f"FQDN eklendi: {server_name}")
                            break
                    else:
                        # Whitelist'te değilse FQDN ekleme
                        self.logger.debug(f"FQDN eklenmedi (whitelist dışı): {server_name}")
                
                return server_name
        
        # Özel durumlar
        if "tüm sunucular" in query_lower or "bütün sunucular" in query_lower:
            self.logger.debug("Tüm sunucular seçildi")
            return None  # None = tüm sunucular
        
        self.logger.debug("Sorguda sunucu adı bulunamadı")
        return None

    def _extract_time_range_from_query(self, query: str) -> Tuple[str, str]:
        """
        Doğal dil sorgusundan zaman aralığını çıkar
        Returns: (time_range, human_readable_time)
        """
    
        import re
        query_lower = query.lower()
        
        # Önce sayısal ifadeleri kontrol et (X günlük, Y haftalık vb.)
        numeric_patterns = [
            (r'(\d+)\s*(gün|günlük)', 'day'),
            (r'(\d+)\s*(hafta|haftalık)', 'week'),
            (r'(\d+)\s*(ay|aylık)', 'month'),
            (r'(\d+)\s*(saat|saatlik)', 'hour')
        ]
        
        for pattern, unit in numeric_patterns:
            match = re.search(pattern, query_lower)
            if match:
                number = int(match.group(1))
                
                # Backend'in anlayacağı formata dönüştür
                if unit == 'hour':
                    if number <= 1:
                        return "last_hour", f"son {number} saat"
                    elif number <= 24:
                        return "last_day", f"son {number} saat"
                    else:
                        return "last_week", f"son {number} saat"
                elif unit == 'day':
                    if number <= 1:
                        return "last_day", f"son {number} gün"
                    elif number <= 7:
                        return "last_week", f"son {number} gün"
                    elif number <= 30:
                        return "last_month", f"son {number} gün"
                    else:
                        return "last_month", f"son {number} gün"
                elif unit == 'week':
                    if number <= 1:
                        return "last_week", f"son {number} hafta"
                    elif number <= 4:
                        return "last_month", f"son {number} hafta"
                    else:
                        return "last_month", f"son {number} hafta"
                elif unit == 'month':
                    return "last_month", f"son {number} ay"
        # Zaman kalıpları ve karşılıkları
        time_patterns = {
            # Saat bazlı
            "son 1 saat": ("last_hour", "son 1 saat"),
            "son bir saat": ("last_hour", "son 1 saat"),
            "son saat": ("last_hour", "son 1 saat"),
            
            # Gün bazlı
            "son 24 saat": ("last_day", "son 24 saat"),
            "son gün": ("last_day", "son 24 saat"),
            "bugün": ("last_day", "bugün"),
            "dün": ("last_day", "dün"),
            
            # Hafta bazlı
            "son 7 gün": ("last_week", "son 7 gün"),
            "son hafta": ("last_week", "son 1 hafta"),
            "bu hafta": ("last_week", "bu hafta"),
            "geçen hafta": ("last_week", "geçen hafta"),
            
            # Ay bazlı
            "son 30 gün": ("last_month", "son 30 gün"),
            "son ay": ("last_month", "son 1 ay"),
            "bu ay": ("last_month", "bu ay"),
        }
        
        # Pattern matching
        for pattern, (time_range, readable) in time_patterns.items():
            if pattern in query_lower:
                self.logger.debug(f"Zaman aralığı tespit edildi: {time_range} ({readable})")
                return time_range, readable
        
        # Varsayılan: son 24 saat
        self.logger.debug("Zaman aralığı belirtilmemiş, varsayılan: son 24 saat")
        return "last_day", "son 24 saat"

    def _create_confirmation_message(self, server: Optional[str], time_range: str, readable_time: str) -> str:
        """Kullanıcı onayı için mesaj oluştur"""
        server_text = f"`{server}`" if server else "**Tüm MongoDB sunucuları**"
        
        message = f"""
🔍 **Anomali Analizi Parametreleri Tespit Edildi:**

📊 **Sunucu:** {server_text}
⏰ **Zaman Aralığı:** {readable_time}
🔧 **Veri Kaynağı:** OpenSearch

Bu parametrelerle anomali analizi başlatılsın mı?

✅ **Onaylıyorsanız:** "evet", "onay", "başlat" yazın
❌ **İptal etmek için:** "hayır", "iptal", "dur" yazın
✏️ **Düzeltmek için:** Yeni parametrelerle sorgunuzu tekrar yazın
"""
        return message


