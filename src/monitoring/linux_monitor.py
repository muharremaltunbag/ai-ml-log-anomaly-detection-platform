import paramiko
import logging
import json
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import re
from pathlib import Path
from dotenv import load_dotenv

# .env dosyasını yükle
load_dotenv()

logger = logging.getLogger(__name__)

class LinuxMonitor:
    """Linux sistemlerini SSH üzerinden izleme sınıfı - Configurable Version"""
    
    def __init__(self, environment: Optional[str] = None, config_path: Optional[str] = None):
        """
        LinuxMonitor başlat
        
        Args:
            environment: Ortam adı (test, production, staging). None ise .env'den alınır
            config_path: Config dosya yolu. None ise .env'den alınır
        """
        # Ortam ve config bilgilerini al
        self.environment = environment or os.getenv('MONITORING_ENV', 'test')
        self.config_path = config_path or os.getenv('MONITORING_CONFIG_PATH', 'config/monitoring_servers.json')
        self.default_timeout = int(os.getenv('MONITORING_DEFAULT_TIMEOUT', '10'))
        
        # SSH client'ları sakla
        self.ssh_clients = {}
        
        # Config'i yükle
        self.config = self._load_config()
        
        # Ortam config'ini al
        if self.environment not in self.config['environments']:
            raise ValueError(f"'{self.environment}' ortamı config dosyasında bulunamadı")
            
        self.env_config = self.config['environments'][self.environment]
        self.servers = self.env_config['servers']
        self.ssh_config = self.env_config.get('ssh_config', {})
        self.commands = self.config.get('monitoring_commands', {})
        
        logger.info(f"LinuxMonitor başlatıldı - Ortam: {self.environment}, Sunucu sayısı: {len(self.servers)}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Config dosyasını yükle"""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                raise FileNotFoundError(f"Config dosyası bulunamadı: {self.config_path}")
                
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            logger.info(f"Config dosyası yüklendi: {self.config_path}")
            return config
            
        except Exception as e:
            logger.error(f"Config yükleme hatası: {e}")
            raise
    
    def _resolve_path(self, path: str, server_config: Dict[str, Any]) -> str:
        """Path içindeki placeholder'ları çöz"""
        # {key_base_path} gibi placeholder'ları değiştir
        if '{key_base_path}' in path:
            base_path = self.ssh_config.get('key_base_path', '')
            path = path.replace('{key_base_path}', base_path)
            
        # ~ karakterini genişlet
        if path.startswith('~'):
            path = os.path.expanduser(path)
            
        return path
    
    def connect_to_node(self, node_name: str) -> bool:
        """Belirtilen node'a SSH bağlantısı kur"""
        try:
            if node_name not in self.servers:
                logger.error(f"Bilinmeyen node: {node_name}")
                return False
                
            server_config = self.servers[node_name]
            
            # SSH client oluştur
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Bağlantı parametrelerini hazırla
            connect_params = {
                'hostname': server_config['host'],
                'port': server_config.get('port', 22),
                'username': server_config.get('user', self.ssh_config.get('default_user', 'root')),
                'timeout': server_config.get('timeout', self.ssh_config.get('default_timeout', self.default_timeout))
            }
            
            # Authentication yöntemi
            if 'key_file' in server_config:
                key_path = self._resolve_path(server_config['key_file'], server_config)
                if os.path.exists(key_path):
                    connect_params['key_filename'] = key_path
                else:
                    logger.warning(f"SSH anahtarı bulunamadı: {key_path}")
                    
            elif 'password' in server_config:
                connect_params['password'] = server_config['password']
            
            # Bağlan
            ssh.connect(**connect_params)
            
            self.ssh_clients[node_name] = ssh
            logger.info(f"{node_name} bağlantısı başarılı ({server_config['host']}:{server_config.get('port', 22)})")
            return True
            
        except Exception as e:
            logger.error(f"{node_name} bağlantı hatası: {e}")
            return False
    
    def disconnect_from_node(self, node_name: str):
        """Node bağlantısını kapat"""
        if node_name in self.ssh_clients:
            try:
                self.ssh_clients[node_name].close()
                del self.ssh_clients[node_name]
                logger.info(f"{node_name} bağlantısı kapatıldı")
            except Exception as e:
                logger.error(f"{node_name} bağlantı kapatma hatası: {e}")
    
    def execute_command(self, node_name: str, command: str) -> Tuple[bool, str]:
        """Belirtilen node'da komut çalıştır"""
        try:
            if node_name not in self.ssh_clients:
                if not self.connect_to_node(node_name):
                    return False, "Bağlantı kurulamadı"
            
            ssh = self.ssh_clients[node_name]
            stdin, stdout, stderr = ssh.exec_command(command)
            
            output = stdout.read().decode('utf-8').strip()
            error = stderr.read().decode('utf-8').strip()
            
            if error and not output:
                logger.warning(f"{node_name} komut hatası: {error}")
                return False, error
                
            return True, output
            
        except Exception as e:
            logger.error(f"{node_name} komut çalıştırma hatası: {e}")
            return False, str(e)
    
    def get_cpu_usage(self, node_name: str) -> Dict[str, Any]:
        """CPU kullanımını al"""
        try:
            # Config'den komutları al veya varsayılan kullan
            cpu_commands = self.commands.get('cpu', {})
            
            # CPU yüzdesi
            cpu_cmd = cpu_commands.get('usage', "top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'")
            success, cpu_percent = self.execute_command(node_name, cpu_cmd)
            
            # CPU sayısı
            count_cmd = cpu_commands.get('count', 'nproc')
            success2, cpu_count = self.execute_command(node_name, count_cmd)
            
            # Yük ortalamaları
            load_cmd = cpu_commands.get('load', "uptime | awk -F'load average:' '{print $2}'")
            success3, load_avg = self.execute_command(node_name, load_cmd)
            
            if not all([success, success2, success3]):
                return {"error": "CPU bilgisi alınamadı"}
            
            loads = [float(x.strip()) for x in load_avg.split(',')]
            
            return {
                "cpu_percent": float(cpu_percent),
                "cpu_count": int(cpu_count),
                "load_average": {
                    "1min": loads[0],
                    "5min": loads[1],
                    "15min": loads[2]
                },
                "node": node_name,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"{node_name} CPU bilgisi hatası: {e}")
            return {"error": str(e)}
    
    def get_memory_usage(self, node_name: str) -> Dict[str, Any]:
        """Bellek kullanımını al"""
        try:
            mem_cmd = self.commands.get('memory', {}).get('info', 'free -b | grep Mem')
            success, output = self.execute_command(node_name, mem_cmd)
            
            if not success:
                return {"error": "Bellek bilgisi alınamadı"}
            
            parts = output.split()
            total = int(parts[1])
            used = int(parts[2])
            free = int(parts[3])
            available = int(parts[6]) if len(parts) > 6 else free
            
            return {
                "total_mb": round(total / 1024 / 1024, 2),
                "used_mb": round(used / 1024 / 1024, 2),
                "free_mb": round(free / 1024 / 1024, 2),
                "available_mb": round(available / 1024 / 1024, 2),
                "percent": round((used / total) * 100, 2),
                "node": node_name,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"{node_name} bellek bilgisi hatası: {e}")
            return {"error": str(e)}
    
    def get_disk_usage(self, node_name: str, path: str = "/") -> Dict[str, Any]:
        """Disk kullanımını al"""
        try:
            disk_cmd = self.commands.get('disk', {}).get('usage', 'df -B1 {path} | tail -1')
            disk_cmd = disk_cmd.format(path=path)
            success, output = self.execute_command(node_name, disk_cmd)
            
            if not success:
                return {"error": "Disk bilgisi alınamadı"}
            
            parts = output.split()
            filesystem = parts[0]
            total = int(parts[1])
            used = int(parts[2])
            available = int(parts[3])
            percent = parts[4].rstrip('%')
            
            return {
                "filesystem": filesystem,
                "mount_point": path,
                "total_gb": round(total / 1024 / 1024 / 1024, 2),
                "used_gb": round(used / 1024 / 1024 / 1024, 2),
                "available_gb": round(available / 1024 / 1024 / 1024, 2),
                "percent": float(percent),
                "node": node_name,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"{node_name} disk bilgisi hatası: {e}")
            return {"error": str(e)}
    
    def get_network_info(self, node_name: str) -> Dict[str, Any]:
        """Ağ bilgilerini al"""
        try:
            net_commands = self.commands.get('network', {})
            
            # IP adresleri
            ip_cmd = net_commands.get('ip_addresses', 'ip -4 addr show | grep inet | grep -v 127.0.0.1')
            success, ip_output = self.execute_command(node_name, ip_cmd)
            
            # Ağ arayüzleri
            if_cmd = net_commands.get('interfaces', 'ls /sys/class/net | grep -v lo')
            success2, if_output = self.execute_command(node_name, if_cmd)
            
            if not all([success, success2]):
                return {"error": "Ağ bilgisi alınamadı"}
            
            # IP adreslerini parse et
            ip_addresses = []
            for line in ip_output.split('\n'):
                if 'inet' in line:
                    match = re.search(r'inet (\d+\.\d+\.\d+\.\d+/\d+)', line)
                    if match:
                        ip_addresses.append(match.group(1))
            
            interfaces = if_output.strip().split('\n')
            
            return {
                "interfaces": interfaces,
                "ip_addresses": ip_addresses,
                "node": node_name,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"{node_name} ağ bilgisi hatası: {e}")
            return {"error": str(e)}
    
    def get_process_info(self, node_name: str, process_name: Optional[str] = None) -> Dict[str, Any]:
        """İşlem bilgilerini al"""
        try:
            proc_commands = self.commands.get('process', {})
            
            if process_name:
                # Belirli bir işlemi ara
                cmd_template = proc_commands.get('find_process', 'ps aux | grep {process_name} | grep -v grep')
                cmd = cmd_template.format(process_name=process_name)
            else:
                # En çok CPU/bellek kullanan işlemler
                cmd = proc_commands.get('top_cpu', 'ps aux --sort=-%cpu,-%mem | head -11 | tail -10')
            
            success, output = self.execute_command(node_name, cmd)
            
            if not success:
                return {"error": "İşlem bilgisi alınamadı"}
            
            processes = []
            for line in output.split('\n'):
                if line.strip():
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        processes.append({
                            "user": parts[0],
                            "pid": parts[1],
                            "cpu_percent": float(parts[2]),
                            "mem_percent": float(parts[3]),
                            "command": parts[10]
                        })
            
            return {
                "process_count": len(processes),
                "processes": processes,
                "node": node_name,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"{node_name} işlem bilgisi hatası: {e}")
            return {"error": str(e)}
    
    def get_mongodb_status(self, node_name: str) -> Dict[str, Any]:
        """MongoDB durumunu kontrol et"""
        try:
            mongo_commands = self.commands.get('mongodb', {})
            
            # MongoDB çalışıyor mu?
            status_cmd = mongo_commands.get('status', 'ps aux | grep mongod | grep -v grep')
            success, mongo_ps = self.execute_command(node_name, status_cmd)
            
            is_running = bool(mongo_ps.strip())
            
            result = {
                "is_running": is_running,
                "node": node_name,
                "timestamp": datetime.now().isoformat()
            }
            
            if is_running:
                # MongoDB versiyonu
                version_cmd = mongo_commands.get('version', 'mongod --version | head -1')
                success2, version = self.execute_command(node_name, version_cmd)
                
                # Port bilgisi
                port_cmd = mongo_commands.get('port', 'netstat -tlnp 2>/dev/null | grep mongod || ss -tlnp | grep mongod')
                success3, port_info = self.execute_command(node_name, port_cmd)
                
                if success2:
                    result["version"] = version.strip()
                if success3:
                    result["port_info"] = port_info.strip()
                    
                # MongoDB process bilgisi
                parts = mongo_ps.split(None, 10)
                if len(parts) >= 11:
                    result["process"] = {
                        "pid": parts[1],
                        "cpu_percent": float(parts[2]),
                        "mem_percent": float(parts[3])
                    }
            
            return result
            
        except Exception as e:
            logger.error(f"{node_name} MongoDB durum hatası: {e}")
            return {"error": str(e)}
    
    def get_all_metrics(self, node_name: str) -> Dict[str, Any]:
        """Tüm metrikleri topla"""
        try:
            server_info = self.servers.get(node_name, {})
            
            return {
                "node": node_name,
                "description": server_info.get('description', ''),
                "tags": server_info.get('tags', []),
                "environment": self.environment,
                "cpu": self.get_cpu_usage(node_name),
                "memory": self.get_memory_usage(node_name),
                "disk": self.get_disk_usage(node_name),
                "network": self.get_network_info(node_name),
                "mongodb": self.get_mongodb_status(node_name),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"{node_name} metrik toplama hatası: {e}")
            return {"error": str(e), "node": node_name}
    
    def get_available_nodes(self) -> List[str]:
        """Mevcut node'ları listele"""
        return list(self.servers.keys())
    
    def get_nodes_by_tag(self, tag: str) -> List[str]:
        """Belirli tag'e sahip node'ları listele"""
        nodes = []
        for node_name, config in self.servers.items():
            if tag in config.get('tags', []):
                nodes.append(node_name)
        return nodes
    
    def is_node_connected(self, node_name: str) -> bool:
        """Node bağlantı durumunu kontrol et"""
        if node_name not in self.ssh_clients:
            return False
            
        try:
            # Basit bir komut çalıştırarak bağlantıyı test et
            self.ssh_clients[node_name].exec_command("echo test")
            return True
        except:
            return False
    
    def disconnect_all(self):
        """Tüm bağlantıları kapat"""
        for node_name in list(self.ssh_clients.keys()):
            self.disconnect_from_node(node_name)
        
        logger.info("Tüm SSH bağlantıları kapatıldı")
    
    def get_environment_info(self) -> Dict[str, Any]:
        """Mevcut ortam bilgilerini döndür"""
        return {
            "environment": self.environment,
            "description": self.env_config.get('description', ''),
            "server_count": len(self.servers),
            "servers": list(self.servers.keys()),
            "config_path": self.config_path
        }