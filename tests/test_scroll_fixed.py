from src.anomaly.log_reader import OpenSearchProxyReader

def test_scroll_after_fix():
    print("SCROLL FIX TEST - AFTER TIMEZONE FIX")
    print("=" * 50)
    
    reader = OpenSearchProxyReader()
    if not reader.connect():
        print("❌ OpenSearch bağlantısı başarısız!")
        return
    
    print("✅ OpenSearch bağlantısı başarılı\n")
    
    # Test 1: Scroll (limit=None) - artık çalışması gerekiyor!
    print("Test 1: Scroll mode (limit=None)")
    df = reader.read_logs(limit=None, last_hours=1)
    print(f"{'✅' if len(df) > 0 else '❌'} Logs retrieved: {len(df):,}")
    
    # Test 2: Normal limit ile karşılaştır
    print("\nTest 2: Normal mode (limit=1000)")
    df2 = reader.read_logs(limit=1000, last_hours=1)
    print(f"{'✅' if len(df2) > 0 else '❌'} Logs retrieved: {len(df2):,}")
    
    print("\n📊 SONUÇ:")
    if len(df) > 0:
        print("✅ SCROLL API DÜZELTME BAŞARILI!")
        print(f"   - Scroll mode: {len(df):,} logs")
        print(f"   - Normal mode: {len(df2):,} logs")
    else:
        print("❌ Scroll hala çalışmıyor, başka sorun var")

if __name__ == "__main__":
    test_scroll_after_fix()