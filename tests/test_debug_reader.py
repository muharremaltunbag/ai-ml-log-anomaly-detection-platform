from src.anomaly.log_reader import OpenSearchProxyReader
from datetime import datetime, timedelta

def debug_reader():
    """Log reader debug"""
    
    print("LOG READER DEBUG")
    print("=" * 50)
    
    # Test different configurations
    configs = [
        {"host_filter": None, "time_range": "last_hour"},
        {"host_filter": None, "time_range": "last_day"},
        {"host_filter": "lcwmongodb01n3.lcwaikiki.local", "time_range": "last_day"},
    ]
    
    for config in configs:
        print(f"\nConfig: {config}")
        print("-" * 30)
        
        reader = OpenSearchProxyReader(**config)
        
        # Login
        if reader._login():
            reader._select_tenant()
            
            # Get logs with different limits
            for limit in [100, 1000, None]:
                logs = reader.get_logs(limit=limit)
                print(f"  Limit {limit}: {len(logs)} logs")
                
                if logs and len(logs) < 50:
                    # Check log content
                    print(f"    First log keys: {list(logs[0].keys())}")
                    print(f"    Timestamp range: {logs[0].get('timestamp', 'N/A')} to {logs[-1].get('timestamp', 'N/A')}")

debug_reader()