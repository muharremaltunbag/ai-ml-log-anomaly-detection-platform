# tests\test_opensearch_proxy.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.anomaly.log_reader import OpenSearchProxyReader
import logging

# Logging ayarla
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

print("🧪 Testing OpenSearch Proxy Reader with Login...")
print("-" * 50)

# Reader'ı başlat
print("\n1️⃣ Initializing reader...")
logger.debug("Starting OpenSearchProxyReader initialization")
reader = OpenSearchProxyReader()
logger.debug("OpenSearchProxyReader initialized successfully")
logger.debug(f"Reader base_url: {getattr(reader, 'base_url', 'No base_url found')}")
logger.debug(f"Reader credentials: {getattr(reader, 'username', 'No username')} / {'***' if hasattr(reader, 'password') else 'No password'}")

# Bağlantıyı test et (login dahil)
print("\n2️⃣ Testing connection (includes login)...")
logger.debug("Attempting connection to OpenSearch proxy")
logger.debug(f"Reader configuration: {vars(reader) if hasattr(reader, '__dict__') else 'No config visible'}")

try:
    logger.debug("=== Starting connection process ===")
    logger.debug("Phase 1: Login attempt")
    logger.debug(f"Login URL construction: base_url={getattr(reader, 'base_url', 'N/A')}")
    
    connection_result = reader.connect()
    logger.debug(f"Connection attempt result: {connection_result}")
    
    if connection_result:
        print("✅ Connection successful! (Login + Health check passed)")
        logger.debug("Connection established successfully")
        logger.debug(f"Connection details: {getattr(reader, 'client', 'No client attribute') if hasattr(reader, 'client') else 'No client found'}")
        logger.debug("=== Cluster health check details ===")
        logger.debug(f"Health check URL: {getattr(reader, 'base_url', 'N/A')}/_cluster/health")
        logger.debug(f"Session cookies: {getattr(reader, 'session', {}).cookies if hasattr(reader, 'session') else 'No session found'}")
        
        # Log okuma testi
        print("\n3️⃣ Reading logs from last 1 hour...")
        logger.debug("Starting log reading operation with limit=10, last_hours=1")
        df = reader.read_logs(limit=10, last_hours=1)
        logger.debug(f"Log reading completed. DataFrame shape: {df.shape if not df.empty else 'Empty'}")
        
        if not df.empty:
            print(f"✅ Successfully read {len(df)} logs")
            print(f"   Columns: {list(df.columns)}")
            logger.debug(f"Retrieved {len(df)} logs with columns: {list(df.columns)}")
            
            print(f"\n   Sample log:")
            if 'msg' in df.columns:
                print(f"   Message: {df.iloc[0]['msg'][:100]}...")
            if 't' in df.columns:
                print(f"   Timestamp: {df.iloc[0]['t']}")
            if 'host' in df.columns:
                print(f"   Host: {df.iloc[0].get('host', 'N/A')}")
            
            # Anomaly detection için gerekli alanları kontrol et
            print(f"\n4️⃣ Checking required fields for anomaly detection...")
            logger.debug("Checking required fields for anomaly detection")
            required_fields = ['t', 's', 'c', 'msg']
            missing_fields = [field for field in required_fields if field not in df.columns]
            
            if missing_fields:
                print(f"⚠️  Missing fields: {missing_fields}")
                logger.warning(f"Missing required fields: {missing_fields}")
            else:
                print("✅ All required fields present!")
                logger.debug("All required fields are present in the DataFrame")
        else:
            print("❌ No logs retrieved")
            logger.warning("No logs were retrieved from the query")
    else:
        print("❌ Connection failed")
        logger.error("Failed to establish connection to OpenSearch proxy")
        logger.error(f"Connection failure details: Check reader state - {getattr(reader, 'last_error', 'No error info available')}")
        logger.error("=== URL encoding troubleshooting ===")
        logger.error(f"Base URL raw: {repr(getattr(reader, 'base_url', 'N/A'))}")
        logger.error(f"Login endpoint: {getattr(reader, 'base_url', 'N/A')}/login")
        logger.error(f"Health endpoint: {getattr(reader, 'base_url', 'N/A')}/_cluster/health")
        
except Exception as e:
    print("❌ Connection failed with exception")
    logger.error(f"Connection failed with exception: {str(e)}")
    logger.error(f"Exception type: {type(e).__name__}")
    logger.error("=== URL encoding debug info ===")
    logger.error(f"Base URL: {getattr(reader, 'base_url', 'N/A')}")
    logger.error(f"URL type: {type(getattr(reader, 'base_url', ''))}")
    logger.debug(f"Full exception details: {e}", exc_info=True)

print("\n" + "-" * 50)
print("Test completed!")
logger.debug("Test execution completed")