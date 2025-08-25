from src.anomaly.log_reader import OpenSearchProxyReader

def test_scroll_fixed():
    print("SCROLL FIX TEST - FINAL")
    print("=" * 50)
    
    reader = OpenSearchProxyReader()
    reader.connect()
    
    # Scroll test
    print("\nScroll test (limit=None):")
    df = reader.read_logs(limit=None, last_hours=24)  # 24 saat daha fazla veri
    print(f"✅ Logs retrieved: {len(df):,}")
    
    if len(df) > 0:
        print(f"First timestamp: {df.iloc[0].get('t', {}).get('$date', 'N/A')}")
        print(f"Last timestamp: {df.iloc[-1].get('t', {}).get('$date', 'N/A')}")
        
        # Host dağılımı
        if 'host' in df.columns:
            print(f"\nTop 5 hosts:")
            for host, count in df['host'].value_counts().head().items():
                print(f"  - {host}: {count:,} logs")

test_scroll_fixed()