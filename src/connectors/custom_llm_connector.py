# MongoDB-LLM-assistant/src/connectors/custom_llm_connector.py

"""
Custom LLM Connector - Corporate LLM Integration
This module provides integration with a corporate LLM service as an alternative to OpenAI.
"""
import os
import json
import requests
from typing import Optional, Dict, Any, List
try:
    from langchain.schema import BaseMessage, HumanMessage, SystemMessage, AIMessage
    from langchain.chat_models.base import BaseChatModel
    from langchain.callbacks.manager import CallbackManagerForLLMRun
    from langchain.schema.output import ChatGeneration, ChatResult
except ImportError:
    from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.callbacks.manager import CallbackManagerForLLMRun
    from langchain_core.outputs import ChatGeneration, ChatResult
from dotenv import load_dotenv
from .base_connector import BaseConnector
import logging

# Ortam değişkenlerini yükle
load_dotenv()

# Logger ayarla
logger = logging.getLogger(__name__)


class CustomLLMChat(BaseChatModel):
    """Custom LLM LangChain chat model wrapper"""

    api_key: str
    endpoint: str
    institution_id: str
    model_name: str = "Sonnet"
    temperature: float = 0.0
    timeout: int = 180
    max_retries: int = 3

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any
    ) -> ChatResult:
        """Send request to Custom LLM API and get response"""

        # Convert messages to Custom LLM format
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

        # Custom LLM expected payload format
        payload = {
            "message": main_message,
            "context": "\n".join(context_messages) if context_messages else "",
            "model": self.model_name,
            "institution_id": self.institution_id
        }

        # Debug için request log
        logger.debug(f"Custom LLM Request - Endpoint: {self.endpoint}")
        logger.debug(f"Custom LLM Request - Model: {self.model_name}")
        logger.debug(f"Custom LLM Request - Institution: {self.institution_id}")
        logger.debug(f"Custom LLM Request - Message: {payload.get('message', '')[:100]}...")
        logger.debug(f"Custom LLM Request - Full payload: {json.dumps(payload, ensure_ascii=False)[:500]}")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Retry mantığı ile istek gönder
        last_error = None
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Custom LLM API call attempt {attempt + 1}/{self.max_retries}")

                response = requests.post(
                    self.endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )

                # HTTP hata kontrolü
                if response.status_code != 200:
                    logger.error(f"Custom LLM API HTTP error: {response.status_code} - {response.text}")
                    response.raise_for_status()

                # JSON yanıtı parse et
                try:
                    logger.debug(f"Custom LLM Raw Response (full): {response.text}")
                    logger.info(f"Custom LLM Raw Response length: {len(response.text)} characters")

                    result = response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"Custom LLM API JSON parse error: {e}")
                    logger.error(f"Raw response: {response.text[:500]}")
                    raise Exception(f"Custom LLM API returned invalid JSON response")

                # Debug için response log
                logger.debug(f"Custom LLM Response status: {response.status_code}")
                logger.debug(f"Custom LLM Response keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")

                # Parse response - support multiple response formats
                content = None

                logger.debug(f"Custom LLM Response structure: {json.dumps(result, indent=2)}")
                logger.info(f"Custom LLM Response type: {type(result)}")

                # Format 1: Direct string response
                if isinstance(result, str):
                    logger.debug("DEBUG: Format 1 - Direct string response")
                    content = result

                # Format 2: message field
                elif "message" in result:
                    logger.debug("DEBUG: Format 2 - 'message' field found")
                    content = result["message"]
                    logger.debug(f"DEBUG: message content type: {type(content)}, value: {str(content)[:100]}...")

                # Format 3: response or reply field
                elif "response" in result:
                    logger.debug("DEBUG: Format 3 - 'response' field found")
                    content = result["response"]
                    logger.debug(f"DEBUG: response content type: {type(content)}, value: {str(content)[:100]}...")
                elif "reply" in result:
                    logger.debug("DEBUG: Format 3 - 'reply' field found")
                    content = result["reply"]
                    logger.debug(f"DEBUG: reply content type: {type(content)}, value: {str(content)[:100]}...")

                # Format 4: OpenAI-like format
                elif "choices" in result and isinstance(result["choices"], list) and len(result["choices"]) > 0:
                    logger.debug("DEBUG: Format 4 - OpenAI-like 'choices' format")
                    choice = result["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        content = choice["message"]["content"]
                        logger.debug("DEBUG: Found content in choices[0].message.content")
                    elif "text" in choice:
                        content = choice["text"]
                        logger.debug("DEBUG: Found content in choices[0].text")

                # Format 5: content field
                elif "content" in result:
                    logger.debug("DEBUG: Format 5 - 'content' field found")
                    content = result["content"]
                    logger.debug(f"DEBUG: content field type: {type(content)}, value: {str(content)[:100]}...")

                # Format 6: text field
                elif "text" in result:
                    logger.debug("DEBUG: Format 6 - 'text' field found")
                    content = result["text"]
                    logger.debug(f"DEBUG: text field type: {type(content)}, value: {str(content)[:100]}...")

                # Format 7: data wrapper
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
                    logger.error(f"Custom LLM API response missing content. Response: {result}")
                    raise Exception("Custom LLM API response missing content")

                logger.info(f"Custom LLM Raw Response Content (first 1500 chars): {content[:1500]}")

                logger.debug(f"Custom LLM Response content length: {len(content)}")
                logger.info(f"Custom LLM Response SUCCESS - content extracted successfully")

                # LangChain formatında yanıt oluştur
                generation = ChatGeneration(
                    message=AIMessage(content=content)
                )

                return ChatResult(generations=[generation])

            except requests.exceptions.Timeout:
                last_error = "Custom LLM API timeout"
                logger.warning(f"Custom LLM API timeout on attempt {attempt + 1}")
                if attempt < self.max_retries - 1:
                    continue

            except requests.exceptions.RequestException as e:
                last_error = f"Custom LLM API request failed: {str(e)}"
                logger.warning(f"Custom LLM API request error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    continue

            except Exception as e:
                last_error = str(e)
                logger.error(f"Custom LLM API error on attempt {attempt + 1}: {e}")
                if attempt < self.max_retries - 1:
                    continue

        error_msg = f"Custom LLM API error ({self.max_retries} attempts): {last_error}"
        logger.error(error_msg)
        raise Exception(error_msg)

    @property
    def _llm_type(self) -> str:
        """Return LLM type identifier"""
        return "custom_llm"

    @property
    def _identifying_params(self) -> Dict[str, Any]:
        """Return model parameters"""
        return {
            "model_name": self.model_name,
            "temperature": self.temperature,
            "endpoint": self.endpoint,
            "institution_id": self.institution_id
        }


class CustomLLMConnector(BaseConnector):
    """Custom corporate LLM API connector"""

    def __init__(self):
        super().__init__()

        # Ortam değişkenlerinden yapılandırmayı al
        self.api_key = os.getenv('CUSTOM_LLM_API_KEY', '')
        self.endpoint = os.getenv('CUSTOM_LLM_ENDPOINT', '')
        self.institution_id = os.getenv('CUSTOM_LLM_INSTITUTION_ID', '')
        self.model_name = os.getenv('CUSTOM_LLM_MODEL', 'Sonnet')

        # Validate required configuration
        if not self.api_key:
            self.logger.warning("CUSTOM_LLM_API_KEY not set. Custom LLM connector will not work until configured.")
        if not self.endpoint:
            self.logger.warning("CUSTOM_LLM_ENDPOINT not set. Custom LLM connector will not work until configured.")
        self.llm: Optional[CustomLLMChat] = None

        # Log yapılandırma bilgileri (hassas bilgileri gizle)
        self.logger.info(f"Custom LLM Connector initialized - Endpoint: {self.endpoint}")
        self.logger.info(f"Custom LLM Connector initialized - Model: {self.model_name}")
        self.logger.info(f"Custom LLM Connector initialized - Institution: {self.institution_id}")
        self.logger.debug(f"Custom LLM Connector initialized - API Key: {self.api_key[:10]}...")

        # DEBUG: Log seviyesi kontrolü
        current_level = logging.getLogger().getEffectiveLevel()
        self.logger.info(f"DEBUG: Current logging level: {current_level} (DEBUG={logging.DEBUG}, INFO={logging.INFO})")

    def connect(self) -> bool:
        """Establish Custom LLM connection"""
        try:
            self.logger.info("Custom LLM connection establishing...")

            # LLM instance oluştur
            self.llm = CustomLLMChat(
                api_key=self.api_key,
                endpoint=self.endpoint,
                institution_id=self.institution_id,
                model_name=self.model_name,
                temperature=0,
                timeout=30,
                max_retries=2
            )

            # Bağlantıyı test et
            self.logger.info("Custom LLM connection test in progress...")
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
                    self.logger.info("Custom LLM connection successful!")
                    self.logger.debug(f"Test yanıtı: {content[:100]}...")
                    self.logger.info(f"DEBUG: Test response length: {len(content)}")
                    return True
                else:
                    self.logger.error("Custom LLM connection test returned no response")
                    self.logger.error(f"DEBUG: Response: {response}")
                    if response and response.generations:
                        self.logger.error(f"DEBUG: Generations[0]: {response.generations[0]}")
                        self.logger.error(f"DEBUG: Message: {response.generations[0].message}")
                    return False

            except Exception as e:
                self.logger.error(f"Custom LLM connection test failed: {e}")
                self._connected = False
                return False

        except Exception as e:
            self.logger.error(f"Custom LLM connection error: {e}")
            self._connected = False
            return False

    def disconnect(self) -> bool:
        """Clean up connection"""
        self.llm = None
        self._connected = False
        self.logger.info("Custom LLM connection closed")
        return True

    def validate_connection(self) -> bool:
        """Validate API key and endpoint"""
        is_valid = bool(self.api_key and self.endpoint and self.institution_id and self.llm)
        if not is_valid:
            self.logger.warning("Custom LLM connection validation failed - missing parameters")
        return is_valid

    def invoke(self, messages: List[BaseMessage]) -> Any:
        """LangChain compatible invoke method - used by anomaly_tools.py"""
        if not self.is_connected():
            self.logger.error("Custom LLM invoke called but no connection")
            raise Exception("Custom LLM connection not established")

        try:
            self.logger.info(f"DEBUG: Custom LLM invoke call - {len(messages)} messages")
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
            self.logger.error(f"Custom LLM invoke error: {e}")
            raise
