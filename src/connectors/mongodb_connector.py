# src/connectors/mongodb_connector.py

import os
from typing import Optional, Dict, Any
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from dotenv import load_dotenv
from .base_connector import BaseConnector

load_dotenv()

class MongoDBConnector(BaseConnector):
    """MongoDB bağlantı yöneticisi"""
    
    def __init__(self):
        super().__init__()
        self.client: Optional[MongoClient] = None
        self.database = None
        self.uri = os.getenv('MONGODB_URI')
        self.db_name = os.getenv('MONGODB_DATABASE')
        
    def connect(self) -> bool:
        """MongoDB'ye güvenli bağlantı"""
        try:
            self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self.client.admin.command('ping')
            self.database = self.client[self.db_name]
            self._connected = True
            self.logger.info("MongoDB bağlantısı başarılı")
            return True
        except (ConnectionFailure, OperationFailure) as e:
            self.logger.error(f"MongoDB bağlantı hatası: {e}")
            return False
    
    def disconnect(self) -> bool:
        """Bağlantıyı kapat"""
        if self.client:
            self.client.close()
            self._connected = False
            return True
        return False
    
    def validate_connection(self) -> bool:
        """Bağlantı sağlığını kontrol et"""
        try:
            self.client.admin.command('ping')
            return True
        except:
            return False