# test_opensearch_pipeline_v3.py
"""
OpenSearch Log Pipeline Test v3
FQDN varyasyonları ile host discovery
"""
import sys
import os
import json
import pandas as pd
from datetime import datetime, timedelta
import logging
from pathlib import Path

# Path ayarlarını düzelt
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent  # tests/Prod Tests -> MongoDB-LLM-assistant
sys.path.insert(0, str(project_root))

print(f"[DEBUG] Working directory: {os.getcwd()}")
print(f"[DEBUG] Project root: {project_root}")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bilinen host varyasyonları
KNOWN_DBSRV_HOSTS = [
    "DBSERVER004", "DBSERVER005", "DBSERVER006",  # ecommercebilling
    "DBSERVER007", "DBSERVER008", "DBSERVER009",  # ecommerce
    "DBSERVER010", "DBSERVER011", "DBSERVER012",  # ecommercelog
    "DBSERVER013", "DBSERVER014", "DBSERVER015",  # rs_ecfavmongo
]

def generate_host_variants(base_hostname):
    """Bir host için tüm olası varyantları üret"""
    variants = []
    
    # Base hostname
    variants.append(base_hostname)
    variants.append(base_hostname.lower())
    variants.append(base_hostname.upper())
    
    # FQDN varyantları
    domains = [
        ".example.com",
        ".internal.local",
        ".example.com"
    ]
    
    for domain in domains:
        variants.append(base_hostname + domain)
        variants.append(base_hostname.lower() + domain)
        variants.append(base_hostname.upper() + domain)
    
    return variants

def find_host_in_opensearch(reader, base_hostname):
    """Verilen host'un OpenSearch'teki gerçek ismini bul"""
    print(f"\n→ Searching variants for {base_hostname}...")
    
    # Tüm varyantları oluştur
    variants = generate_host_variants(base_hostname)
    
    for variant in variants:
        print(f"   Trying: {variant}")
        try:
            # Sadece 1 log ile hızlı kontrol
            df = reader.read_logs(
                limit=1,
                last_hours=72,  # Son 3 gün
                host_filter=variant
            )
            
            if not df.empty:
                print(f"   ✅ BULUNDU: {variant}")
                return variant
                
        except Exception as e:
            continue
    
    print(f"   ❌ {base_hostname} için aktif varyant bulunamadı")
    return None

def discover_all_mongodb_hosts(reader):
    """OpenSearch'teki TÜM MongoDB hostlarını keşfet"""
    print("\n" + "="*60)
    print("COMPREHENSIVE HOST DISCOVERY")
    print("="*60)
    
    print("→ Son 72 saatteki TÜM MongoDB hostları aranıyor...")
    
    try:
        # 72 saate çıkar
        hosts = reader.get_available_hosts(last_hours=72)
        
        if hosts:
            print(f"\n✅ {len(hosts)} aktif host bulundu!")
            
            # Host gruplandırma
            dbsrv_hosts = []
            prod_hosts = []
            test_hosts = []
            other_hosts = []
            
            for h in hosts:
                h_upper = h.upper()
                if 'DBSRV' in h_upper and 'MNG' in h_upper:
                    dbsrv_hosts.append(h)
                elif 'MONGOPROD' in h_upper:
                    prod_hosts.append(h)
                elif 'TEST' in h_upper and 'MONGO' in h_upper:
                    test_hosts.append(h)
                else:
                    other_hosts.append(h)
            
            # Detaylı rapor
            if dbsrv_hosts:
                print(f"\n🔸 DBSRV Production Hosts ({len(dbsrv_hosts)}):")
                for h in sorted(dbsrv_hosts)[:15]:
                    print(f"   - {h}")
                if len(dbsrv_hosts) > 15:
                    print(f"   ... ve {len(dbsrv_hosts)-15} host daha")
            
            if prod_hosts:
                print(f"\n🔸 Production Hosts ({len(prod_hosts)}):")
                for h in sorted(prod_hosts):
                    print(f"   - {h}")
            
            if test_hosts:
                print(f"\n🔸 Test Hosts ({len(test_hosts)}):")
                for h in sorted(test_hosts):
                    print(f"   - {h}")
            
            if other_hosts:
                print(f"\n🔸 Other MongoDB Hosts ({len(other_hosts)}):")
                for h in sorted(other_hosts)[:10]:
                    print(f"   - {h}")
                if len(other_hosts) > 10:
                    print(f"   ... ve {len(other_hosts)-10} host daha")
            
            return hosts, {
                'dbsrv': dbsrv_hosts,
                'prod': prod_hosts,
                'test': test_hosts,
                'other': other_hosts
            }
        else:
            print("❌ Hiç host bulunamadı!")
            return [], {}
            
    except Exception as e:
        print(f"❌ Host discovery hatası: {e}")
        import traceback
        traceback.print_exc()
        return [], {}

def test_dbsrv_hosts_specifically(reader):
    """Bilinen DBSRV hostlarını spesifik olarak test et"""
    print("\n" + "="*60)
    print("DBSRV HOST SPECIFIC TESTING")
    print("="*60)
    
    found_hosts = []
    
    for base_host in KNOWN_DBSRV_HOSTS[:5]:  # İlk 5 host'u test et
        actual_hostname = find_host_in_opensearch(reader, base_host)
        if actual_hostname:
            found_hosts.append(actual_hostname)
    
    if found_hosts:
        print(f"\n✅ {len(found_hosts)} DBSRV host bulundu:")
        for h in found_hosts:
            print(f"   • {h}")
        
        # Her birinden log oku
        all_logs = []
        for hostname in found_hosts[:3]:  # İlk 3'ünden log al
            print(f"\n→ {hostname} logları okunuyor...")
            try:
                df = reader.read_logs(
                    limit=200,
                    last_hours=24,
                    host_filter=hostname
                )
                
                if not df.empty:
                    print(f"   ✅ {len(df)} log okundu")
                    all_logs.append(df)
                else:
                    print(f"   ⚠️ Log bulunamadı")
                    
            except Exception as e:
                print(f"   ❌ Hata: {e}")
        
        if all_logs:
            combined_df = pd.concat(all_logs, ignore_index=True)
            print(f"\n✅ Toplam {len(combined_df)} DBSRV log birleştirildi")
            return combined_df
    
    return pd.DataFrame()

def analyze_logs(df):
    """Log analizi ve pattern tespiti"""
    if df.empty:
        return
    
    print("\n" + "="*60)
    print("LOG ANALYSIS")
    print("="*60)
    
    print(f"→ {len(df)} log analiz ediliyor...")
    
    # Severity dağılımı
    if 's' in df.columns:
        print("\n📊 Severity Dağılımı:")
        severity = df['s'].value_counts()
        for sev, count in severity.items():
            percent = (count/len(df))*100
            print(f"   {sev}: {count} ({percent:.1f}%)")
    
    # Component dağılımı
    if 'c' in df.columns:
        print("\n📊 Top Components:")
        components = df['c'].value_counts().head(5)
        for comp, count in components.items():
            print(f"   {comp}: {count}")
    
    # Kritik pattern'ler
    if 'msg' in df.columns:
        patterns = {
            'Slow query': df['msg'].str.contains('Slow query', na=False, case=False).sum(),
            'COLLSCAN': df['msg'].str.contains('COLLSCAN', na=False).sum(),
            'Auth Failed': df['msg'].str.contains('Checking authorization failed', na=False).sum(),
            'Index Build': df['msg'].str.contains('Index build', na=False, case=False).sum(),
            'Error': df['msg'].str.contains('error|Error|ERROR', na=False).sum(),
            'Out of Memory': df['msg'].str.contains('Out of memory|OOM', na=False, case=False).sum(),
            'Connection': df['msg'].str.contains('connection', na=False, case=False).sum()
        }
        
        print("\n🔍 Kritik Pattern Tespiti:")
        for pattern, count in patterns.items():
            if count > 0:
                print(f"   🔴 {pattern}: {count}")
            else:
                print(f"   🟢 {pattern}: 0")
    
    # Zaman aralığı
    if 't' in df.columns:
        timestamps = pd.to_datetime(df['t'].apply(lambda x: x.get('$date') if isinstance(x, dict) else x))
        print(f"\n⏰ Zaman Aralığı:")
        print(f"   İlk log: {timestamps.min()}")
        print(f"   Son log: {timestamps.max()}")
        print(f"   Süre: {timestamps.max() - timestamps.min()}")

def main():
    """Ana test fonksiyonu"""
    print("\n" + "="*60)
    print("MongoDB Log Anomaly Detection - DBSRV Host Test v3")
    print("Test Tarihi:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*60)
    
    try:
        # Import kontrolü
        try:
            from src.anomaly.log_reader import OpenSearchProxyReader
            print("✅ Module import başarılı")
        except ImportError as e:
            print(f"❌ Module import hatası: {e}")
            print("Alternatif import deneniyor...")
            # Direkt path ile dene
            sys.path.insert(0, str(project_root / "src"))
            from anomaly.log_reader import OpenSearchProxyReader
        
        # OpenSearch bağlantısı
        reader = OpenSearchProxyReader()
        print("\n→ OpenSearch'e bağlanılıyor...")
        
        if not reader.connect():
            print("❌ OpenSearch bağlantısı başarısız!")
            return False
        
        print("✅ OpenSearch bağlantısı başarılı!")
        
        # Host discovery
        all_hosts, grouped_hosts = discover_all_mongodb_hosts(reader)
        
        # DBSRV hostları spesifik test et
        dbsrv_logs = test_dbsrv_hosts_specifically(reader)
        
        # Log analizi
        if not dbsrv_logs.empty:
            analyze_logs(dbsrv_logs)
        
        # Eğer DBSRV'da log yoksa, keşfedilen diğer hostları dene
        if dbsrv_logs.empty and grouped_hosts.get('dbsrv'):
            print("\n→ Keşfedilen DBSRV hostlarından log okuma deneniyor...")
            for host in grouped_hosts['dbsrv'][:3]:
                df = reader.read_logs(limit=100, last_hours=24, host_filter=host)
                if not df.empty:
                    print(f"✅ {host} üzerinden {len(df)} log okundu!")
                    analyze_logs(df)
                    break
        
        # Sonuç
        print("\n" + "="*60)
        print("TEST SONUCU")
        print("="*60)
        print(f"✅ Test tamamlandı!")
        print(f"   • {len(all_hosts)} host keşfedildi")
        if not dbsrv_logs.empty:
            print(f"   • {len(dbsrv_logs)} DBSRV log işlendi")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Kritik hata: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)