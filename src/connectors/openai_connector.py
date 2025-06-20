# C:\Users\muharrem.altunbag\MongoDB-LLM-assistant\MongoDB-LLM-assistant\src\connectors\openai_connector.py


import os
from typing import Optional
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from .base_connector import BaseConnector

load_dotenv()

class OpenAIConnector(BaseConnector):
    """OpenAI API bağlantı yöneticisi"""
    
    def __init__(self):
        super().__init__()
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.model_name = os.getenv('OPENAI_MODEL', 'gpt-4o')
        self.llm: Optional[ChatOpenAI] = None
        
    def connect(self) -> bool:
        """OpenAI LLM bağlantısını kur"""
        try:
            self.llm = ChatOpenAI(
                api_key=self.api_key,
                model=self.model_name,
                temperature=0,
                max_tokens=2000,
                timeout=30,
                max_retries=2
            )
            self._connected = True
            self.logger.info("OpenAI bağlantısı başarılı")
            return True
        except Exception as e:
            self.logger.error(f"OpenAI bağlantı hatası: {e}")
            return False
    
    def disconnect(self) -> bool:
        """Bağlantıyı temizle"""
        self.llm = None
        self._connected = False
        return True
    
    def validate_connection(self) -> bool:
        """API key doğrulaması"""
        return bool(self.api_key and self.llm)