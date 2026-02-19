#!/usr/bin/env python3
"""
System Reset Script - MongoDB LLM Assistant
============================================
Sistemi sifirdan baslatmak icin tum gecici verileri guvenli sekilde temizler:
  1. ML modelleri (models/*.pkl, storage/models/*.pkl)
  2. Anomali analizleri (output/*, storage/exports/anomaly/*)
  3. Storage deposu (storage/temp/*, storage/backups/*, storage/uploads/*)
  4. Cache dosyalari (cache/*, frequency baseline)
  5. Chat gecmisi (MongoDB query_history, in-memory conversation)
  6. MongoDB koleksiyonlari (anomaly_history, model_registry, analysis_cache, user_feedback)
  7. Log dosyalari (logs/*, temp_logs/*)
  8. Metrik dosyalari (metrics/*)

Guvenlik:
  - Config dosyalari DOKUNULMAZ
  - Kaynak kodu DOKUNULMAZ
  - .git klasoru DOKUNULMAZ
  - Her islem oncesi onay istenir
  - Silinen dosyalar loglanir

Kullanim:
  python system_reset.py              # Interaktif mod (her kategori icin onay)
  python system_reset.py --all        # Hepsini sil (tek onay)
  python system_reset.py --dry-run    # Nelerin silinecegini goster, silme
  python system_reset.py --skip-db    # MongoDB islemlerini atla
"""

import os
import sys
import glob
import shutil
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

# Proje root dizini
PROJECT_ROOT = Path(__file__).parent.resolve()

# Logging ayarlari
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SystemReset")


# ============================================================
# Temizlenecek kategoriler ve hedef yollar
# ============================================================

CLEANUP_CATEGORIES = {
    "ml_models": {
        "label": "ML Modelleri",
        "description": "Egitilmis Isolation Forest modelleri ve yedekleri",
        "targets": [
            {"pattern": "models/*.pkl", "type": "file"},
            {"pattern": "models/**/*.pkl", "type": "file"},
            {"pattern": "storage/models/*.pkl", "type": "file"},
            {"pattern": "storage/models/**/*.pkl", "type": "file"},
            {"pattern": "models_backup_*", "type": "dir"},
        ]
    },
    "anomaly_output": {
        "label": "Anomali Analizleri",
        "description": "Onceki anomali tespit sonuclari (CSV, JSON)",
        "targets": [
            {"pattern": "output/*.csv", "type": "file"},
            {"pattern": "output/*.json", "type": "file"},
            {"pattern": "storage/exports/anomaly/*.json", "type": "file"},
            {"pattern": "storage/exports/anomaly/*.pkl", "type": "file"},
            {"pattern": "storage/exports/anomaly/*.csv", "type": "file"},
        ]
    },
    "storage_depot": {
        "label": "Storage Deposu",
        "description": "Gecici dosyalar, yedekler, yuklemeler",
        "targets": [
            {"pattern": "storage/temp/*", "type": "file"},
            {"pattern": "storage/backups/*", "type": "any"},
            {"pattern": "storage/uploads/*", "type": "any"},
        ]
    },
    "cache": {
        "label": "Cache Dosyalari",
        "description": "Feature cache, frekans baseline, analiz cache",
        "targets": [
            {"pattern": "cache/**/*", "type": "any"},
            {"pattern": "cache/*", "type": "any"},
        ]
    },
    "logs": {
        "label": "Log Dosyalari",
        "description": "Uygulama ve anomali tespit loglari",
        "targets": [
            {"pattern": "logs/*.log", "type": "file"},
            {"pattern": "temp_logs/*", "type": "any"},
        ]
    },
    "metrics": {
        "label": "Metrik Dosyalari",
        "description": "Performans metrikleri",
        "targets": [
            {"pattern": "metrics/*.json", "type": "file"},
        ]
    },
    "pycache": {
        "label": "Python Cache",
        "description": "__pycache__ dizinleri",
        "targets": [
            {"pattern": "**/__pycache__", "type": "dir"},
        ]
    },
}

# MongoDB'de temizlenecek koleksiyonlar
MONGODB_COLLECTIONS = [
    "anomaly_history",
    "model_registry",
    "user_feedback",
    "analysis_cache",
    "query_history",
    "user_preferences",
]


def find_targets(category_key: str) -> List[Tuple[str, str]]:
    """
    Bir kategori icin silinecek dosya/dizinleri bulur.

    Returns:
        List of (absolute_path, type) tuples
    """
    category = CLEANUP_CATEGORIES[category_key]
    found = []

    for target in category["targets"]:
        pattern = str(PROJECT_ROOT / target["pattern"])
        items = glob.glob(pattern, recursive=True)

        for item in items:
            # .git ve config klasorlerini koru
            if "/.git/" in item or "/.git" == item:
                continue
            if "/config/" in item:
                continue

            if target["type"] == "file" and os.path.isfile(item):
                found.append((item, "file"))
            elif target["type"] == "dir" and os.path.isdir(item):
                found.append((item, "dir"))
            elif target["type"] == "any":
                if os.path.isfile(item):
                    found.append((item, "file"))
                elif os.path.isdir(item):
                    found.append((item, "dir"))

    # Tekrarlari kaldir
    seen = set()
    unique = []
    for path, ftype in found:
        if path not in seen:
            seen.add(path)
            unique.append((path, ftype))

    return unique


def get_file_size(path: str) -> int:
    """Dosya veya dizin boyutunu byte olarak hesaplar."""
    if os.path.isfile(path):
        return os.path.getsize(path)
    elif os.path.isdir(path):
        total = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total += os.path.getsize(fp)
        return total
    return 0


def format_size(size_bytes: int) -> str:
    """Byte'i okunabilir formata cevirir."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def delete_items(items: List[Tuple[str, str]], dry_run: bool = False) -> Dict[str, int]:
    """
    Dosya/dizinleri siler.

    Returns:
        {"deleted": count, "failed": count, "total_bytes": freed_bytes}
    """
    stats = {"deleted": 0, "failed": 0, "total_bytes": 0}

    for path, ftype in items:
        size = get_file_size(path)

        if dry_run:
            rel_path = os.path.relpath(path, PROJECT_ROOT)
            logger.info(f"  [DRY-RUN] Silinecek: {rel_path} ({format_size(size)})")
            stats["deleted"] += 1
            stats["total_bytes"] += size
            continue

        try:
            if ftype == "file":
                os.remove(path)
            elif ftype == "dir":
                shutil.rmtree(path)

            rel_path = os.path.relpath(path, PROJECT_ROOT)
            logger.info(f"  Silindi: {rel_path} ({format_size(size)})")
            stats["deleted"] += 1
            stats["total_bytes"] += size
        except Exception as e:
            logger.warning(f"  Silinemedi: {path} - {e}")
            stats["failed"] += 1

    return stats


def clean_mongodb(dry_run: bool = False, skip_db: bool = False) -> Dict[str, int]:
    """
    MongoDB koleksiyonlarini temizler.

    Returns:
        {"cleared": count, "failed": count, "total_docs": deleted_docs}
    """
    stats = {"cleared": 0, "failed": 0, "total_docs": 0}

    if skip_db:
        logger.info("  MongoDB islemleri atlanıyor (--skip-db)")
        return stats

    try:
        from pymongo import MongoClient
    except ImportError:
        logger.warning("  pymongo yuklu degil, MongoDB temizligi atlanıyor.")
        return stats

    # Connection string'i config'den al
    connection_string = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/')
    database_name = os.getenv('MONGODB_STORAGE_DB', 'anomaly_detection')

    try:
        client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
        # Baglanti testi
        client.admin.command('ping')
    except Exception as e:
        logger.warning(f"  MongoDB'ye baglanılamadı: {e}")
        logger.info("  MongoDB temizligi atlanıyor.")
        return stats

    db = client[database_name]
    existing_collections = db.list_collection_names()

    for coll_name in MONGODB_COLLECTIONS:
        if coll_name not in existing_collections:
            logger.info(f"  '{coll_name}' koleksiyonu mevcut degil, atlanıyor.")
            continue

        try:
            doc_count = db[coll_name].count_documents({})

            if dry_run:
                logger.info(f"  [DRY-RUN] Temizlenecek: {coll_name} ({doc_count} dokuman)")
                stats["cleared"] += 1
                stats["total_docs"] += doc_count
                continue

            result = db[coll_name].delete_many({})
            deleted = result.deleted_count
            logger.info(f"  Temizlendi: {coll_name} ({deleted} dokuman silindi)")
            stats["cleared"] += 1
            stats["total_docs"] += deleted

        except Exception as e:
            logger.warning(f"  '{coll_name}' temizlenemedi: {e}")
            stats["failed"] += 1

    client.close()
    return stats


def print_summary(all_stats: Dict[str, Dict], mongodb_stats: Dict[str, int], dry_run: bool):
    """Temizlik ozetini yazdirir."""
    prefix = "[DRY-RUN] " if dry_run else ""

    print(f"\n{'=' * 60}")
    print(f"  {prefix}SISTEM SIFIRLAMA OZETI")
    print(f"{'=' * 60}")

    total_files = 0
    total_bytes = 0
    total_failed = 0

    for cat_key, stats in all_stats.items():
        label = CLEANUP_CATEGORIES[cat_key]["label"]
        count = stats["deleted"]
        size = format_size(stats["total_bytes"])
        failed = stats["failed"]

        status = f"{count} oge silindi ({size})"
        if failed > 0:
            status += f" | {failed} HATA"

        print(f"  {label:.<30s} {status}")
        total_files += count
        total_bytes += stats["total_bytes"]
        total_failed += failed

    # MongoDB ozeti
    if mongodb_stats["cleared"] > 0 or mongodb_stats["failed"] > 0:
        mongo_status = f"{mongodb_stats['cleared']} koleksiyon ({mongodb_stats['total_docs']} dokuman)"
        if mongodb_stats["failed"] > 0:
            mongo_status += f" | {mongodb_stats['failed']} HATA"
        print(f"  {'MongoDB':.<30s} {mongo_status}")

    print(f"{'=' * 60}")
    print(f"  TOPLAM: {total_files} dosya/dizin ({format_size(total_bytes)})")

    if mongodb_stats["total_docs"] > 0:
        print(f"  MongoDB: {mongodb_stats['total_docs']} dokuman")

    if total_failed > 0:
        print(f"  HATALAR: {total_failed}")

    print(f"{'=' * 60}")

    if not dry_run:
        print("\n  Sistem sifirlanmistir.")
        print("  Bir sonraki analizde modeller otomatik olarak yeniden egitilecektir.")
        print("  Storage dizinleri ilk kullanimda otomatik olusturulacaktir.\n")


def confirm_action(message: str) -> bool:
    """Kullanicidan onay ister."""
    try:
        response = input(f"\n{message} (evet/hayir): ").strip().lower()
        return response == "evet"
    except (EOFError, KeyboardInterrupt):
        print("\nIptal edildi.")
        return False


def run_reset(args):
    """Ana temizlik akisini yonetir."""
    dry_run = args.dry_run
    skip_db = args.skip_db
    run_all = args.all

    mode_label = "DRY-RUN (sadece gosterim)" if dry_run else "GERCEK SILME"

    print(f"\n{'=' * 60}")
    print(f"  MongoDB LLM Assistant - Sistem Sifirlama")
    print(f"  Mod: {mode_label}")
    print(f"  Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Proje: {PROJECT_ROOT}")
    print(f"{'=' * 60}")

    # Oncelikle nelerin silinecegini tara
    print("\n  Tarama yapiliyor...\n")
    scan_results = {}
    total_items = 0

    for cat_key in CLEANUP_CATEGORIES:
        items = find_targets(cat_key)
        scan_results[cat_key] = items
        total_items += len(items)

        label = CLEANUP_CATEGORIES[cat_key]["label"]
        if items:
            total_size = sum(get_file_size(p) for p, _ in items)
            print(f"  [{len(items):>3d} oge] {label}: {format_size(total_size)}")
        else:
            print(f"  [  0 oge] {label}: temiz")

    if not skip_db:
        print(f"  [  ?    ] MongoDB: koleksiyonlar kontrol edilecek")

    if total_items == 0 and skip_db:
        print("\n  Silinecek bir sey bulunamadi. Sistem zaten temiz.")
        return

    # Toplu onay veya kategori bazli onay
    if not dry_run:
        if run_all:
            if not confirm_action("UYARI: Tum veriler silinecek. Bu islem geri alinamaz. Onayliyor musunuz?"):
                print("Iptal edildi.")
                return
        else:
            print("\n  Her kategori icin ayri onay istenecektir.")

    # Temizlik islemi
    all_stats = {}

    for cat_key, category in CLEANUP_CATEGORIES.items():
        items = scan_results[cat_key]

        if not items:
            all_stats[cat_key] = {"deleted": 0, "failed": 0, "total_bytes": 0}
            continue

        label = category["label"]
        desc = category["description"]

        if not dry_run and not run_all:
            total_size = sum(get_file_size(p) for p, _ in items)
            if not confirm_action(
                f"{label} ({len(items)} oge, {format_size(total_size)}) - {desc}\n  Silinsin mi?"
            ):
                logger.info(f"  {label} atlandi.")
                all_stats[cat_key] = {"deleted": 0, "failed": 0, "total_bytes": 0}
                continue

        print(f"\n--- {label} temizleniyor ---")
        stats = delete_items(items, dry_run=dry_run)
        all_stats[cat_key] = stats

    # MongoDB temizligi
    print(f"\n--- MongoDB temizleniyor ---")

    if not dry_run and not run_all and not skip_db:
        if not confirm_action("MongoDB koleksiyonlari (chat gecmisi, anomali gecmisi vb.) temizlensin mi?"):
            logger.info("  MongoDB atlandi.")
            mongodb_stats = {"cleared": 0, "failed": 0, "total_docs": 0}
        else:
            mongodb_stats = clean_mongodb(dry_run=dry_run, skip_db=skip_db)
    else:
        mongodb_stats = clean_mongodb(dry_run=dry_run, skip_db=skip_db)

    # Ozet
    print_summary(all_stats, mongodb_stats, dry_run)


def main():
    parser = argparse.ArgumentParser(
        description="MongoDB LLM Assistant - Sistem Sifirlama Scripti",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ornekler:
  python system_reset.py              Interaktif mod (her kategori icin onay)
  python system_reset.py --all        Hepsini sil (tek onay)
  python system_reset.py --dry-run    Nelerin silinecegini goster, silme
  python system_reset.py --skip-db    MongoDB islemlerini atla
  python system_reset.py --all --dry-run   Hepsini goster ama silme
        """
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Tum kategorileri tek onay ile sil"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Sadece nelerin silinecegini goster, gercekte silme"
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="MongoDB islemlerini atla"
    )

    args = parser.parse_args()
    run_reset(args)


if __name__ == "__main__":
    main()
