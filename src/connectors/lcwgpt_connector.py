# MongoDB-LLM-assistant\src\connectors\lcwgpt_connector.py

"""
LCWGPT Connector - LC Waikiki Kurumsal LLM Entegrasyonu
Bu modül, OpenAI yerine kurumsal LCWGPT servisini kullanmak için yazılmıştır.
"""
import os
import json
import requests
from typing import Optional, Dict, Any, List
from langchain.schema import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langchain.chat_models.base import BaseChatModel
from langchain.callbacks.manager import CallbackManagerForLLMRun
from langchain.schema.output import ChatGeneration, ChatResult
from dotenv import load_dotenv
from .base_connector import BaseConnector
import logging

# Ortam değişkenlerini yükle
load_dotenv()

# Logger ayarla
logger = logging.getLogger(__name__)


class LCWGPTChat(BaseChatModel):
    """LCWGPT için özel LangChain chat model wrapper"""
    
    api_key: str
    endpoint: str
    institution_id: str
    model_name: str = "Sonnet"
    temperature: float = 0.0
    # Büyük batch analizleri ve aggregation için süre uzatıldı
    timeout: int = 180
    # Ağ hatalarına karşı direnç artırıldı
    max_retries: int = 3
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any
    ) -> ChatResult:
        """LCWGPT API'ye istek gönder ve yanıt al"""
        
        # Mesajları LCWGPT formatına dönüştür
        formatted_messages = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                formatted_messages.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                formatted_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                formatted_messages.append({"role": "assistant", "content": msg.content})
        
        # Mesajları birleştirerek tek bir string haline getir
        context_messages = []
        main_message = ""

        for msg in formatted_messages:
            if msg["role"] == "system":
                context_messages.append(f"System: {msg['content']}")
            elif msg["role"] == "user":
                main_message = msg["content"]  # Son user mesajını ana mesaj olarak kullan
            elif msg["role"] == "assistant":
                context_messages.append(f"Assistant: {msg['content']}")

        # LCWGPT'nin beklediği format
        payload = {
            "message": main_message,
            "context": "\n".join(context_messages) if context_messages else "",
            "model": self.model_name,
            "institution_id": self.institution_id
        }
        
        # Debug için request log
        logger.debug(f"LCWGPT Request - Endpoint: {self.endpoint}")
        logger.debug(f"LCWGPT Request - Model: {self.model_name}")
        logger.debug(f"LCWGPT Request - Institution: {self.institution_id}")
        logger.debug(f"LCWGPT Request - Message: {payload.get('message', '')[:100]}...")
        logger.debug(f"LCWGPT Request - Full payload: {json.dumps(payload, ensure_ascii=False)[:500]}")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Retry mantığı ile istek gönder
        last_error = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"LCWGPT API call attempt {attempt + 1}/{self.max_retries}")
                
                response = requests.post(
                    self.endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )
                
                # HTTP hata kontrolü
                if response.status_code != 200:
                    logger.error(f"LCWGPT API HTTP error: {response.status_code} - {response.text}")
                    response.raise_for_status()
                
                # JSON yanıtı parse et
                try:
                    # DEBUG: Ham response'u logla
                    logger.debug(f"LCWGPT Raw Response (full): {response.text}")
                    logger.info(f"LCWGPT Raw Response length: {len(response.text)} characters")
                    
                    result = response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"LCWGPT API JSON parse error: {e}")
                    logger.error(f"Raw response: {response.text[:500]}")
                    raise Exception(f"LCWGPT API geçersiz JSON yanıtı döndü")
                
                # Debug için response log
                logger.debug(f"LCWGPT Response status: {response.status_code}")
                logger.debug(f"LCWGPT Response keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
                
                # LCWGPT yanıtını parse et - farklı olası yanıt formatlarını destekle
                content = None
                
                # Debug için response yapısını logla
                logger.debug(f"LCWGPT Response structure: {json.dumps(result, indent=2)}")
                logger.info(f"LCWGPT Response type: {type(result)}")
                
                # Format 1: Doğrudan message/text response
                if isinstance(result, str):
                    logger.debug("DEBUG: Format 1 - Direct string response")
                    content = result
                
                # Format 2: message field'ı olan response
                elif "message" in result:
                    logger.debug("DEBUG: Format 2 - 'message' field found")
                    content = result["message"]
                    logger.debug(f"DEBUG: message content type: {type(content)}, value: {str(content)[:100]}...")
                
                # Format 3: response veya reply field'ı
                elif "response" in result:
                    logger.debug("DEBUG: Format 3 - 'response' field found")
                    content = result["response"]
                    logger.debug(f"DEBUG: response content type: {type(content)}, value: {str(content)[:100]}...")
                elif "reply" in result:
                    logger.debug("DEBUG: Format 3 - 'reply' field found")
                    content = result["reply"]
                    logger.debug(f"DEBUG: reply content type: {type(content)}, value: {str(content)[:100]}...")
                
                # Format 4: OpenAI benzeri format
                elif "choices" in result and isinstance(result["choices"], list) and len(result["choices"]) > 0:
                    logger.debug("DEBUG: Format 4 - OpenAI-like 'choices' format")
                    choice = result["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        content = choice["message"]["content"]
                        logger.debug("DEBUG: Found content in choices[0].message.content")
                    elif "text" in choice:
                        content = choice["text"]
                        logger.debug("DEBUG: Found content in choices[0].text")
                
                # Format 5: content field'ı
                elif "content" in result:
                    logger.debug("DEBUG: Format 5 - 'content' field found")
                    content = result["content"]
                    logger.debug(f"DEBUG: content field type: {type(content)}, value: {str(content)[:100]}...")
                
                # Format 6: text field'ı
                elif "text" in result:
                    logger.debug("DEBUG: Format 6 - 'text' field found")
                    content = result["text"]
                    logger.debug(f"DEBUG: text field type: {type(content)}, value: {str(content)[:100]}...")
                
                # Format 7: data içinde response
                elif "data" in result:
                    logger.debug("DEBUG: Format 7 - 'data' field found")
                    data = result["data"]
                    logger.debug(f"DEBUG: data type: {type(data)}")
                    if isinstance(data, dict):
                        logger.debug(f"DEBUG: data dict keys: {list(data.keys())}")
                        content = data.get("message") or data.get("content") or data.get("text") or data.get("response")
                        logger.debug(f"DEBUG: extracted content from data: {str(content)[:100] if content else 'None'}...")
                    elif isinstance(data, str):
                        content = data
                        logger.debug("DEBUG: data is string")
                
                # DEBUG: Final content kontrolü
                logger.info(f"DEBUG: Final content status - content: {bool(content)}")
                if content:
                    logger.info(f"DEBUG: Final content type: {type(content)}")
                    logger.info(f"DEBUG: Final content length: {len(str(content))}")
                    logger.debug(f"DEBUG: Final content value: {str(content)[:200]}...")
                else:
                    logger.error("DEBUG: Content is None/empty after all format checks")
                    logger.error("DEBUG: Available fields in response:")
                    if isinstance(result, dict):
                        for key, value in result.items():
                            logger.error(f"  - {key}: {type(value)} = {str(value)[:100]}...")
                
                if not content:
                    logger.error(f"LCWGPT API yanıtında content bulunamadı. Response: {result}")
                    raise Exception("LCWGPT API yanıtında content bulunamadı")
                
                # Ham içeriği detaylı logla
                logger.info(f"LCWGPT Raw Response Content (first 1500 chars): {content[:1500]}")
                
                logger.debug(f"LCWGPT Response content length: {len(content)}")
                logger.info(f"LCWGPT Response SUCCESS - content extracted successfully")
                
                # LangChain formatında yanıt oluştur
                generation = ChatGeneration(
                    message=AIMessage(content=content)
                )
                
                return ChatResult(generations=[generation])
                
            except requests.exceptions.Timeout:
                last_error = "LCWGPT API zaman aşımı"
                logger.warning(f"LCWGPT API timeout on attempt {attempt + 1}")
                if attempt < self.max_retries - 1:
                    continue
                    
            except requests.exceptions.RequestException as e:
                last_error = f"LCWGPT API isteği başarısız: {str(e)}"
                logger.warning(f"LCWGPT API request error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    continue
                    
            except Exception as e:
                last_error = str(e)
                logger.error(f"LCWGPT API error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    continue
        
        # Tüm denemeler başarısız olduysa hata fırlat
        error_msg = f"LCWGPT API hatası ({self.max_retries} deneme sonrası): {last_error}"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    @property
    def _llm_type(self) -> str:
        """LLM tipini döndür"""
        return "lcwgpt"
    
    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """Model parametrelerini döndür"""
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "endpoint": self.endpoint,
            "institution_id": self.institution_id
        }


class LCWGPTConnector(BaseConnector):
    """LCWGPT kurumsal API bağlantı yöneticisi"""
    
    def __init__(self):
        super().__init__()
        
        # Ortam değişkenlerinden yapılandırmayı al
        self.api_key = os.getenv('LCWGPT_API_KEY', 'sk_gsMk5_sScqq9ZXFxOr751GJsuIf4VhI6tQhMOp2siW8')
        self.endpoint = os.getenv('LCWGPT_ENDPOINT', 'https://lcwgpt-test.lcwaikiki.com/api/service/message')
        self.institution_id = os.getenv('LCWGPT_INSTITUTION_ID', 'analitikverimüdürlügü')
        self.model_name = os.getenv('LCWGPT_MODEL', 'Sonnet')
        self.llm: Optional[LCWGPTChat] = None
        
        # Log yapılandırma bilgileri (hassas bilgileri gizle)
        self.logger.info(f"LCWGPT Connector initialized - Endpoint: {self.endpoint}")
        self.logger.info(f"LCWGPT Connector initialized - Model: {self.model_name}")
        self.logger.info(f"LCWGPT Connector initialized - Institution: {self.institution_id}")
        self.logger.debug(f"LCWGPT Connector initialized - API Key: {self.api_key[:10]}...")
        
        # DEBUG: Log seviyesi kontrolü
        current_level = logging.getLogger().getEffectiveLevel()
        self.logger.info(f"DEBUG: Current logging level: {current_level} (DEBUG={logging.DEBUG}, INFO={logging.INFO})")
        
    def connect(self) -> bool:
        """LCWGPT bağlantısını kur"""
        try:
            self.logger.info("LCWGPT bağlantısı kuruluyor...")
            
            # LLM instance oluştur
            self.llm = LCWGPTChat(
                api_key=self.api_key,
                endpoint=self.endpoint,
                institution_id=self.institution_id,
                model_name=self.model_name,
                temperature=0,  # Deterministik sonuçlar için
                timeout=30,
                max_retries=2
            )
            
            # Bağlantıyı test et
            self.logger.info("LCWGPT bağlantı testi yapılıyor...")
            test_messages = [
                SystemMessage(content="Sen bir MongoDB anomali analiz uzmanısın."),
                HumanMessage(content="Merhaba, sistemin çalıştığını onaylayabilir misin?")
            ]
            
            try:
                response = self.llm._generate(test_messages)
                self.logger.debug(f"DEBUG: Test response type: {type(response)}")
                self.logger.debug(f"DEBUG: Test response generations: {bool(response.generations) if response else 'No response'}")
                
                if response and response.generations and response.generations[0].message.content:
                    content = response.generations[0].message.content
                    self._connected = True
                    self.logger.info("LCWGPT bağlantısı başarılı!")
                    self.logger.debug(f"Test yanıtı: {content[:100]}...")
                    self.logger.info(f"DEBUG: Test response length: {len(content)}")
                    return True
                else:
                    self.logger.error("LCWGPT bağlantı testi yanıt döndürmedi")
                    self.logger.error(f"DEBUG: Response: {response}")
                    if response and response.generations:
                        self.logger.error(f"DEBUG: Generations[0]: {response.generations[0]}")
                        self.logger.error(f"DEBUG: Message: {response.generations[0].message}")
                    return False
                    
            except Exception as e:
                self.logger.error(f"LCWGPT bağlantı testi başarısız: {e}")
                self._connected = False
                return False
                
        except Exception as e:
            self.logger.error(f"LCWGPT bağlantı hatası: {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> bool:
        """Bağlantıyı temizle"""
        self.llm = None
        self._connected = False
        self.logger.info("LCWGPT bağlantısı kapatıldı")
        return True
    
    def validate_connection(self) -> bool:
        """API key ve endpoint doğrulaması"""
        is_valid = bool(self.api_key and self.endpoint and self.institution_id and self.llm)
        if not is_valid:
            self.logger.warning("LCWGPT bağlantı doğrulaması başarısız - eksik parametreler")
        return is_valid
    
    def invoke(self, messages: List[BaseMessage]) -> Any:
        """LangChain uyumlu invoke metodu - anomaly_tools.py tarafından kullanılır"""
        if not self.is_connected():
            self.logger.error("LCWGPT invoke çağrısı yapıldı ama bağlantı yok")
            raise Exception("LCWGPT bağlantısı yok")
        
        try:
            self.logger.info(f"DEBUG: LCWGPT invoke çağrısı - {len(messages)} mesaj")
            for i, msg in enumerate(messages):
                self.logger.debug(f"DEBUG: Message {i}: {type(msg).__name__} - {str(msg.content)[:100]}...")
            
            result = self.llm._generate(messages)
            
            self.logger.debug(f"DEBUG: Invoke result type: {type(result)}")
            if result and result.generations:
                message = result.generations[0].message
                self.logger.info(f"DEBUG: Invoke result message type: {type(message)}")
                self.logger.info(f"DEBUG: Invoke result content length: {len(message.content) if message.content else 0}")
                self.logger.debug(f"DEBUG: Invoke result content preview: {str(message.content)[:100] if message.content else 'None'}...")
                return message
            else:
                self.logger.error("DEBUG: Invoke result is empty or malformed")
                self.logger.error(f"DEBUG: Result: {result}")
                return None
                
        except Exception as e:
            self.logger.error(f"LCWGPT invoke hatası: {e}")
            raise