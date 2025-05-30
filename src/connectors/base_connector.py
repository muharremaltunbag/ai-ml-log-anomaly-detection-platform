from abc import ABC, abstractmethod
import logging
from typing import Any, Optional

class BaseConnector(ABC):
    """Tüm connector'lar için temel sınıf"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._connected = False
    
    @abstractmethod
    def connect(self) -> bool:
        """Bağlantı kurma metodu"""
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """Bağlantı kesme metodu"""
        pass
    
    @abstractmethod
    def validate_connection(self) -> bool:
        """Bağlantı doğrulama"""
        pass
    
    def is_connected(self) -> bool:
        """Bağlantı durumu kontrolü"""
        return self._connected