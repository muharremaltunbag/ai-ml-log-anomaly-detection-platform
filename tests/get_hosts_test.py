# tests/get_hosts_test.py 
from src.anomaly.log_reader import get_available_mongodb_hosts

hosts = get_available_mongodb_hosts(last_hours=24)
print("Total hosts:", len(hosts))
print("\nİlk 30 host:")
for i, host in enumerate(hosts[:30], 1):
    print(f"{i}. {host}")