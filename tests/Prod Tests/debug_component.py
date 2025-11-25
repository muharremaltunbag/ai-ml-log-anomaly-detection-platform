# tests/debug_component.py

import sys
from pathlib import Path

# Path düzeltmesi
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.anomaly.log_reader import OpenSearchProxyReader

# Veri çek ve component field'ı kontrol et
reader = OpenSearchProxyReader()
reader.connect()
df = reader.read_logs(limit=100, last_hours=1)

print("\n📊 DataFrame Info:")
print(f"Columns: {df.columns.tolist()}")

if 'c' in df.columns:
    print(f"\n🔍 Component field analysis:")
    print(f"  Total rows: {len(df)}")
    print(f"  Non-null 'c' values: {df['c'].notna().sum()}")
    print(f"  Unique components: {df['c'].nunique()}")
    print(f"  Sample components: {df['c'].value_counts().head()}")
    
    # Null olanları kontrol et
    null_count = df['c'].isna().sum()
    if null_count > 0:
        print(f"  ⚠️ NULL components: {null_count} ({null_count/len(df)*100:.1f}%)")
        
    # Sample messages with components
    sample = df[df['c'].notna()].head(3)
    for idx, row in sample.iterrows():
        print(f"\n  Example: Component='{row['c']}', Message='{row['msg'][:50]}'")
else:
    print("❌ 'c' field not in DataFrame!")

# Host field kontrolü
if 'host' in df.columns:
    print(f"\n🖥️ Host field analysis:")
    print(f"  Non-null hosts: {df['host'].notna().sum()}")
    print(f"  Sample hosts: {df['host'].value_counts().head()}")