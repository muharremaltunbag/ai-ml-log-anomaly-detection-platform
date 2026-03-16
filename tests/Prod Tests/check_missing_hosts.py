#!/usr/bin/env python3
"""
MongoDB Host Inventory Check - OpenSearch vs Config Comparison

Bu script:
1. OpenSearch'ten (https://localhost:9200) gerçek MongoDB host'larını çeker
2. config/cluster_mapping.json ile karşılaştırır
3. Eksik, unmapped, ve fazla host'ları detaylı raporlar
4. JSON ve console output üretir

Author: Example Corp DBA Team
Date: 2025
"""


import sys
from pathlib import Path

# Path düzeltmesi
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
sys.path.insert(0, str(project_root))

print(f"[DEBUG] Project root: {project_root}")
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Any
from collections import defaultdict

# Import anomaly modüllerini
try:
    from src.anomaly.log_reader import (
        OpenSearchProxyReader,
        get_available_mongodb_hosts,
        load_cluster_mapping,
        normalize_hostname,
        get_cluster_for_host
    )
    print("✅ Log reader modülleri başarıyla yüklendi")
except ImportError as e:
    print(f"❌ HATA: Log reader modülleri yüklenemedi: {e}")
    print("Script'i proje ana dizininden çalıştırın veya PYTHONPATH'i ayarlayın")
    sys.exit(1)


class HostInventoryChecker:
    """MongoDB host envanteri kontrolcüsü"""
    
    def __init__(self):
        self.opensearch_hosts = []
        self.config_hosts = set()
        self.cluster_mapping = {}
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "opensearch_url": "https://localhost:9200",
            "summary": {},
            "missing_hosts": [],
            "unmapped_hosts": [],
            "extra_in_config": [],
            "cluster_breakdown": {}
        }
    
    def fetch_opensearch_hosts(self, last_hours: int = 24) -> List[str]:
        """OpenSearch'ten gerçek host listesini çek"""
        print(f"\n🔍 OpenSearch'ten son {last_hours} saatteki aktif MongoDB host'ları çekiliyor...")
        print(f"   URL: https://localhost:9200")
        
        try:
            # OpenSearch'e bağlan
            reader = OpenSearchProxyReader()
            print("   ⏳ Bağlantı kuruluyor...")
            
            if not reader.connect():
                print("   ❌ OpenSearch bağlantısı başarısız!")
                return []
            
            print("   ✅ Bağlantı başarılı!")
            
            # Host'ları çek
            print(f"   ⏳ Host'lar getiriliyor (db-mongodb-* index'inden)...")
            hosts = reader.get_available_hosts(last_hours=last_hours)
            
            if hosts:
                print(f"   ✅ {len(hosts)} aktif MongoDB host bulundu!")
                self.opensearch_hosts = sorted(hosts)
                return self.opensearch_hosts
            else:
                print("   ⚠️  Hiç host bulunamadı!")
                return []
                
        except Exception as e:
            print(f"   ❌ HATA: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def load_config_hosts(self) -> Dict[str, Any]:
        """Config dosyasından host'ları yükle"""
        print("\n📂 Config dosyası yükleniyor...")
        
        try:
            mapping = load_cluster_mapping()
            self.cluster_mapping = mapping
            
            if not mapping or 'cluster_mappings' not in mapping:
                print("   ⚠️  cluster_mapping.json bulunamadı veya boş!")
                return {}
            
            # Tüm config'deki host'ları topla
            all_config_hosts = set()
            
            # Cluster mappings'ten host'ları al
            for cluster_name, hosts in mapping.get('cluster_mappings', {}).items():
                for host in hosts:
                    all_config_hosts.add(normalize_hostname(host))
            
            # Standalone host'ları ekle
            for host in mapping.get('standalone_hosts', []):
                all_config_hosts.add(normalize_hostname(host))
            
            self.config_hosts = all_config_hosts
            
            print(f"   ✅ Config'den {len(all_config_hosts)} host yüklendi")
            print(f"   📊 Cluster sayısı: {len(mapping.get('cluster_mappings', {}))}")
            print(f"   📊 Standalone host: {len(mapping.get('standalone_hosts', []))}")
            
            return mapping
            
        except Exception as e:
            print(f"   ❌ HATA: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def compare_hosts(self):
        """Host listelerini karşılaştır ve farkları bul"""
        print("\n🔬 Host listeleri karşılaştırılıyor...")
        
        # OpenSearch host'larını normalize et
        opensearch_normalized = {normalize_hostname(h): h for h in self.opensearch_hosts}
        
        # Eksik host'lar (OpenSearch'te var, config'de yok)
        missing = []
        for normalized, original in opensearch_normalized.items():
            if normalized not in self.config_hosts:
                # Cluster'ını bulmaya çalış (benzer isimlerden)
                suggested_cluster = self._suggest_cluster(normalized)
                missing.append({
                    "hostname": original,
                    "normalized": normalized,
                    "suggested_cluster": suggested_cluster,
                    "log_count": "unknown"  # Opsiyonel: log sayısı eklenebilir
                })
        
        self.results["missing_hosts"] = missing
        
        # Unmapped host'lar (OpenSearch'te var, hangi cluster'a ait olduğu bilinmiyor)
        unmapped = []
        for normalized, original in opensearch_normalized.items():
            if normalized in self.config_hosts:
                # Cluster'ını kontrol et
                cluster = get_cluster_for_host(original)
                if cluster is None:
                    unmapped.append({
                        "hostname": original,
                        "normalized": normalized,
                        "reason": "No cluster mapping found"
                    })
        
        self.results["unmapped_hosts"] = unmapped
        
        # Fazla host'lar (Config'de var, OpenSearch'te aktif değil)
        extra = []
        for config_host in self.config_hosts:
            if config_host not in opensearch_normalized:
                # Orijinal halini bul
                original_host = self._find_original_hostname(config_host)
                cluster = get_cluster_for_host(original_host) if original_host else None
                extra.append({
                    "hostname": original_host or config_host,
                    "normalized": config_host,
                    "cluster": cluster,
                    "status": "not_active_in_opensearch"
                })
        
        self.results["extra_in_config"] = extra
        
        # Summary
        self.results["summary"] = {
            "total_opensearch_hosts": len(self.opensearch_hosts),
            "total_config_hosts": len(self.config_hosts),
            "missing_count": len(missing),
            "unmapped_count": len(unmapped),
            "extra_count": len(extra),
            "match_rate": f"{((len(self.config_hosts) - len(missing)) / max(len(self.opensearch_hosts), 1) * 100):.1f}%"
        }
        
        print(f"   ✅ Karşılaştırma tamamlandı!")
    
    def _suggest_cluster(self, hostname: str) -> str:
        """Host adından cluster tahmini yap"""
        hostname_lower = hostname.lower()
        
        # Pattern matching ile cluster tahmini
        patterns = {
            "ecomfix": "ecommercefix",
            "mongo-prod-01": "mongo-prod-01",
            "ntfc": "ntfcmongo",
            "pplaz": "rs_pplaz",
            "test": "testmongo",
            "dev": "rsdevmongo",
            "dbserver-001": "ecommercemp",
            "dbserver-002": "ecommercemp",
            "dbserver-003": "ecommercemp",
            "dbserver-004": "ecommercebilling",
            "dbserver-005": "ecommercebilling",
            "dbserver-006": "ecommercebilling",
            "dbserver-007": "ecommerce",
            "dbserver-008": "ecommerce",
            "dbserver-009": "ecommerce",
            "dbserver-010": "ecommercelog",
            "dbserver-011": "ecommercelog",
            "dbserver-012": "ecommercelog",
            "dbserver-013": "rs_ecfavmongo",
            "dbserver-014": "rs_ecfavmongo",
            "dbserver-015": "rs_ecfavmongo",
            "ecazgldb": "ecazgldb",
            "ppl": "ppl",
            "kzn": "kznmongors",
            "kz": "kzmongors",
            "ru": "rs_rumongo"
        }
        
        for pattern, cluster in patterns.items():
            if pattern in hostname_lower:
                return cluster
        
        return "unknown"
    
    def _find_original_hostname(self, normalized: str) -> str:
        """Normalize edilmiş host'un orijinal halini bul"""
        # cluster_mappings'te ara
        for cluster_name, hosts in self.cluster_mapping.get('cluster_mappings', {}).items():
            for host in hosts:
                if normalize_hostname(host) == normalized:
                    return host
        
        # standalone_hosts'ta ara
        for host in self.cluster_mapping.get('standalone_hosts', []):
            if normalize_hostname(host) == normalized:
                return host
        
        return normalized
    
    def generate_cluster_breakdown(self):
        """Cluster bazında detaylı breakdown"""
        print("\n📊 Cluster bazlı analiz yapılıyor...")
        
        breakdown = {}
        
        # Her cluster için analiz
        for cluster_name, config_hosts in self.cluster_mapping.get('cluster_mappings', {}).items():
            cluster_info = {
                "cluster_name": cluster_name,
                "display_name": self.cluster_mapping.get('cluster_display_names', {}).get(cluster_name, cluster_name),
                "environment": self._get_environment(cluster_name),
                "config_hosts": config_hosts,
                "config_count": len(config_hosts),
                "active_hosts": [],
                "inactive_hosts": [],
                "missing_hosts": []
            }
            
            # Config'deki her host'u kontrol et
            for host in config_hosts:
                normalized = normalize_hostname(host)
                # OpenSearch'te aktif mi?
                opensearch_match = None
                for os_host in self.opensearch_hosts:
                    if normalize_hostname(os_host) == normalized:
                        opensearch_match = os_host
                        break
                
                if opensearch_match:
                    cluster_info["active_hosts"].append(host)
                else:
                    cluster_info["inactive_hosts"].append(host)
            
            # OpenSearch'te olan ama config'de olmayan host'ları bul
            for missing in self.results["missing_hosts"]:
                if missing["suggested_cluster"] == cluster_name:
                    cluster_info["missing_hosts"].append(missing["hostname"])
            
            cluster_info["active_count"] = len(cluster_info["active_hosts"])
            cluster_info["inactive_count"] = len(cluster_info["inactive_hosts"])
            cluster_info["missing_count"] = len(cluster_info["missing_hosts"])
            cluster_info["health_status"] = self._calculate_health(cluster_info)
            
            breakdown[cluster_name] = cluster_info
        
        self.results["cluster_breakdown"] = breakdown
        print(f"   ✅ {len(breakdown)} cluster analiz edildi")
    
    def _get_environment(self, cluster_name: str) -> str:
        """Cluster'ın environment'ini bul"""
        env_mapping = self.cluster_mapping.get('environment_mapping', {})
        for env, clusters in env_mapping.items():
            if cluster_name in clusters:
                return env
        return "unknown"
    
    def _calculate_health(self, cluster_info: Dict) -> str:
        """Cluster health status hesapla"""
        if cluster_info["missing_count"] > 0:
            return "⚠️ INCOMPLETE"
        elif cluster_info["inactive_count"] > 0:
            return "⚡ PARTIAL"
        else:
            return "✅ HEALTHY"
    
    def print_report(self):
        """Console'a detaylı rapor yazdır"""
        print("\n" + "="*80)
        print("🔍 MONGODB HOST INVENTORY REPORT")
        print("="*80)
        print(f"📅 Timestamp: {self.results['timestamp']}")
        print(f"🌐 OpenSearch: {self.results['opensearch_url']}")
        print("="*80)
        
        # Summary
        summary = self.results["summary"]
        print(f"\n📊 ÖZET:")
        print(f"   • OpenSearch'teki toplam host: {summary['total_opensearch_hosts']}")
        print(f"   • Config'deki toplam host: {summary['total_config_hosts']}")
        print(f"   • Eşleşme oranı: {summary['match_rate']}")
        print(f"   • Config'de EKSIK host: {summary['missing_count']}")
        print(f"   • Unmapped host: {summary['unmapped_count']}")
        print(f"   • Config'de FAZLA (aktif değil): {summary['extra_count']}")
        
        # Missing hosts
        if self.results["missing_hosts"]:
            print(f"\n❌ CONFIG'DE EKSİK HOST'LAR ({len(self.results['missing_hosts'])} adet):")
            print("   (OpenSearch'te aktif ama cluster_mapping.json'da tanımlı değil)")
            print()
            for i, host_info in enumerate(self.results["missing_hosts"], 1):
                print(f"   {i}. {host_info['hostname']}")
                print(f"      └─ Önerilen cluster: {host_info['suggested_cluster']}")
                print(f"      └─ Normalized: {host_info['normalized']}")
        
        # Unmapped hosts
        if self.results["unmapped_hosts"]:
            print(f"\n⚠️  UNMAPPED HOST'LAR ({len(self.results['unmapped_hosts'])} adet):")
            print("   (Config'de var ama cluster mapping'i belirsiz)")
            print()
            for i, host_info in enumerate(self.results["unmapped_hosts"], 1):
                print(f"   {i}. {host_info['hostname']}")
                print(f"      └─ Sebep: {host_info['reason']}")
        
        # Extra in config
        if self.results["extra_in_config"]:
            print(f"\n🔍 CONFIG'DE FAZLA HOST'LAR ({len(self.results['extra_in_config'])} adet):")
            print("   (Config'de tanımlı ama OpenSearch'te aktif değil - son 24 saat)")
            print()
            for i, host_info in enumerate(self.results["extra_in_config"], 1):
                print(f"   {i}. {host_info['hostname']}")
                print(f"      └─ Cluster: {host_info.get('cluster', 'unknown')}")
                print(f"      └─ Durum: {host_info['status']}")
        
        # Cluster breakdown
        if self.results["cluster_breakdown"]:
            print(f"\n📊 CLUSTER BAZLI DETAY:")
            print()
            for cluster_name, info in sorted(self.results["cluster_breakdown"].items()):
                print(f"   🔹 {info['display_name']} ({info['environment']})")
                print(f"      └─ Durum: {info['health_status']}")
                print(f"      └─ Config'deki host sayısı: {info['config_count']}")
                print(f"      └─ Aktif host: {info['active_count']}")
                print(f"      └─ İnaktif host: {info['inactive_count']}")
                print(f"      └─ Eksik host: {info['missing_count']}")
                
                if info['missing_hosts']:
                    print(f"      └─ Eksik olan host'lar:")
                    for host in info['missing_hosts']:
                        print(f"         • {host}")
                print()
        
        print("="*80)
        
        # OpenSearch'teki TÜM host'ları listele
        if self.opensearch_hosts:
            print(f"\n📋 OPENSEARCH'TEKİ TÜM MONGODB HOST'LARI ({len(self.opensearch_hosts)} adet):")
            print("   (Son 24 saatte aktif olan sunucular)")
            print()
            for i, host in enumerate(self.opensearch_hosts, 1):
                cluster = get_cluster_for_host(host)
                status = "✅" if normalize_hostname(host) in self.config_hosts else "❌"
                print(f"   {status} {i}. {host} → Cluster: {cluster or 'UNMAPPED'}")
        
        print("\n" + "="*80)
    
    def save_json_report(self, output_file: str = "host_inventory_report.json"):
        """JSON rapor dosyası oluştur"""
        try:
            output_path = Path(output_file)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            print(f"\n💾 JSON rapor kaydedildi: {output_path.absolute()}")
            return True
        except Exception as e:
            print(f"\n❌ JSON rapor kaydedilemedi: {e}")
            return False
    
    def generate_config_patch(self) -> Dict[str, Any]:
        """Eksik host'ları eklemek için config patch'i oluştur"""
        if not self.results["missing_hosts"]:
            print("\n✅ Eksik host yok, config güncellemesi gerekmiyor!")
            return {}
        
        print(f"\n🔧 Config güncellemesi hazırlanıyor...")
        
        patch = {
            "timestamp": datetime.now().isoformat(),
            "description": "Missing hosts to be added to cluster_mapping.json",
            "updates": []
        }
        
        # Cluster bazında grupla
        cluster_updates = defaultdict(list)
        for missing in self.results["missing_hosts"]:
            cluster = missing["suggested_cluster"]
            if cluster != "unknown":
                cluster_updates[cluster].append(missing["hostname"])
        
        # Update listesini oluştur
        for cluster, hosts in cluster_updates.items():
            patch["updates"].append({
                "cluster": cluster,
                "action": "add_hosts",
                "hosts": hosts
            })
        
        # Patch'i kaydet
        try:
            patch_file = Path("config_patch.json")
            with open(patch_file, 'w', encoding='utf-8') as f:
                json.dump(patch, f, indent=2, ensure_ascii=False)
            print(f"   ✅ Config patch kaydedildi: {patch_file.absolute()}")
        except Exception as e:
            print(f"   ⚠️  Config patch kaydedilemedi: {e}")
        
        return patch


def main():
    """Ana fonksiyon"""
    print("="*80)
    print("🚀 MONGODB HOST INVENTORY CHECKER")
    print("="*80)
    print("Example Corp - MongoDB Log Anomaly Detection System")
    print("OpenSearch Host Inventory vs Config Comparison Tool")
    print("="*80)
    
    # Checker'ı oluştur
    checker = HostInventoryChecker()
    
    # 1. OpenSearch'ten host'ları çek
    opensearch_hosts = checker.fetch_opensearch_hosts(last_hours=24)
    
    if not opensearch_hosts:
        print("\n❌ HATA: OpenSearch'ten host listesi alınamadı!")
        print("   Lütfen .env dosyasını kontrol edin:")
        print("   - OPENSEARCH_URL")
        print("   - OPENSEARCH_USER")
        print("   - OPENSEARCH_PASS")
        return 1
    
    # 2. Config'den host'ları yükle
    config_mapping = checker.load_config_hosts()
    
    if not config_mapping:
        print("\n❌ HATA: Config dosyası yüklenemedi!")
        return 1
    
    # 3. Karşılaştırma yap
    checker.compare_hosts()
    
    # 4. Cluster breakdown
    checker.generate_cluster_breakdown()
    
    # 5. Raporları oluştur
    checker.print_report()
    checker.save_json_report("host_inventory_report.json")
    
    # 6. Config patch oluştur (eğer eksik host varsa)
    if checker.results["missing_hosts"]:
        checker.generate_config_patch()
        print("\n⚠️  UYARI: Config güncellemesi gerekiyor!")
        print("   → config_patch.json dosyasını inceleyin")
        print("   → cluster_mapping.json'ı güncelleyin")
    else:
        print("\n✅ Config dosyası güncel! Tüm host'lar tanımlı.")
    
    print("\n" + "="*80)
    print("✅ Analiz tamamlandı!")
    print("="*80)
    
    return 0


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  İşlem kullanıcı tarafından iptal edildi!")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ BEKLENMEYEN HATA: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)