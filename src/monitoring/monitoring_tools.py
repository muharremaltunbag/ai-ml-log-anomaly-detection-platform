from typing import Dict, Any, List, Optional
from langchain.tools import Tool
import json
import logging
from .linux_monitor import LinuxMonitor

logger = logging.getLogger(__name__)

class MonitoringTools:
    """Linux Monitoring için LangChain Tool'ları"""
    
    def __init__(self, monitor: Optional[LinuxMonitor] = None):
        """
        MonitoringTools başlat
        
        Args:
            monitor: LinuxMonitor instance. None ise yeni oluşturulur.
        """
        self.monitor = monitor or LinuxMonitor()
        logger.info(f"MonitoringTools başlatıldı - Ortam: {self.monitor.environment}")
    
    def _format_result(self, result: Dict[str, Any], operation: str) -> str:
        """Sonuçları formatla"""
        try:
            if "error" in result:
                return json.dumps({
                    "durum": "hata",
                    "işlem": operation,
                    "açıklama": result.get("error", "Bilinmeyen hata"),
                    "sonuç": None
                }, ensure_ascii=False, indent=2)
            
            return json.dumps({
                "durum": "başarılı",
                "işlem": operation,
                "açıklama": f"{operation} işlemi tamamlandı",
                "sonuç": result
            }, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"Format hatası: {e}")
            return json.dumps({
                "durum": "hata",
                "işlem": operation,
                "açıklama": f"Format hatası: {str(e)}",
                "sonuç": str(result)
            }, ensure_ascii=False, indent=2)
    
    def check_server_status(self, args_input) -> str:
        """Sunucu durumunu kontrol et"""
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                except:
                    args_dict = {"node_name": args_input.strip()}
            else:
                args_dict = args_input
            
            node_name = args_dict.get("node_name", "")
            
            if not node_name:
                # Tüm sunucuların özet durumu
                nodes = self.monitor.get_available_nodes()
                status_list = []
                
                for node in nodes:
                    connected = self.monitor.is_node_connected(node)
                    server_info = self.monitor.servers.get(node, {})
                    
                    status_list.append({
                        "node": node,
                        "connected": connected,
                        "description": server_info.get("description", ""),
                        "tags": server_info.get("tags", [])
                    })
                
                result = {
                    "environment": self.monitor.environment,
                    "total_servers": len(nodes),
                    "servers": status_list
                }
            else:
                # Belirli sunucunun durumu
                if node_name not in self.monitor.get_available_nodes():
                    return self._format_result(
                        {"error": f"'{node_name}' sunucusu bulunamadı"},
                        "server_status"
                    )
                
                # Bağlantı kur ve temel bilgileri al
                connected = self.monitor.connect_to_node(node_name)
                
                if connected:
                    # Uptime bilgisi
                    success, uptime = self.monitor.execute_command(node_name, "uptime -p")
                    
                    # Hostname
                    success2, hostname = self.monitor.execute_command(node_name, "hostname")
                    
                    # OS bilgisi
                    success3, os_info = self.monitor.execute_command(node_name, "cat /etc/os-release | grep PRETTY_NAME | cut -d'=' -f2")
                    
                    server_info = self.monitor.servers.get(node_name, {})
                    
                    result = {
                        "node": node_name,
                        "status": "online",
                        "hostname": hostname.strip() if success2 else "unknown",
                        "os": os_info.strip().strip('"') if success3 else "unknown",
                        "uptime": uptime.strip() if success else "unknown",
                        "description": server_info.get("description", ""),
                        "tags": server_info.get("tags", []),
                        "host": server_info.get("host", ""),
                        "port": server_info.get("port", 22)
                    }
                else:
                    result = {
                        "node": node_name,
                        "status": "offline",
                        "error": "Bağlantı kurulamadı"
                    }
            
            return self._format_result(result, "server_status")
            
        except Exception as e:
            logger.error(f"Server status hatası: {e}")
            return self._format_result({"error": str(e)}, "server_status")
    
    def get_server_metrics(self, args_input) -> str:
        """Sunucu metriklerini al"""
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                except:
                    args_dict = {"node_name": args_input.strip()}
            else:
                args_dict = args_input
            
            node_name = args_dict.get("node_name", "")
            metric_type = args_dict.get("metric_type", "all")  # all, cpu, memory, disk, network
            
            if not node_name:
                return self._format_result(
                    {"error": "Sunucu adı belirtilmeli"},
                    "server_metrics"
                )
            
            if node_name not in self.monitor.get_available_nodes():
                return self._format_result(
                    {"error": f"'{node_name}' sunucusu bulunamadı"},
                    "server_metrics"
                )
            
            # Metrik tipine göre veri topla
            if metric_type == "all":
                result = self.monitor.get_all_metrics(node_name)
            elif metric_type == "cpu":
                result = self.monitor.get_cpu_usage(node_name)
            elif metric_type == "memory":
                result = self.monitor.get_memory_usage(node_name)
            elif metric_type == "disk":
                result = self.monitor.get_disk_usage(node_name)
            elif metric_type == "network":
                result = self.monitor.get_network_info(node_name)
            elif metric_type == "mongodb":
                result = self.monitor.get_mongodb_status(node_name)
            else:
                return self._format_result(
                    {"error": f"Geçersiz metrik tipi: {metric_type}"},
                    "server_metrics"
                )
            
            return self._format_result(result, "server_metrics")
            
        except Exception as e:
            logger.error(f"Server metrics hatası: {e}")
            return self._format_result({"error": str(e)}, "server_metrics")
    
    def find_resource_intensive_processes(self, args_input) -> str:
        """Kaynak tüketen işlemleri bul"""
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                except:
                    args_dict = {"node_name": args_input.strip()}
            else:
                args_dict = args_input
            
            node_name = args_dict.get("node_name", "")
            process_name = args_dict.get("process_name", None)
            
            if not node_name:
                return self._format_result(
                    {"error": "Sunucu adı belirtilmeli"},
                    "process_info"
                )
            
            if node_name not in self.monitor.get_available_nodes():
                return self._format_result(
                    {"error": f"'{node_name}' sunucusu bulunamadı"},
                    "process_info"
                )
            
            # İşlem bilgilerini al
            result = self.monitor.get_process_info(node_name, process_name)
            
            # En çok kaynak kullananları öne çıkar
            if "processes" in result and result["processes"]:
                # CPU ve Memory'ye göre sırala
                result["top_cpu_processes"] = sorted(
                    result["processes"], 
                    key=lambda x: x["cpu_percent"], 
                    reverse=True
                )[:5]
                
                result["top_memory_processes"] = sorted(
                    result["processes"], 
                    key=lambda x: x["mem_percent"], 
                    reverse=True
                )[:5]
            
            return self._format_result(result, "process_info")
            
        except Exception as e:
            logger.error(f"Process info hatası: {e}")
            return self._format_result({"error": str(e)}, "process_info")
    
    def execute_monitoring_command(self, args_input) -> str:
        """Özel monitoring komutu çalıştır"""
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                except:
                    return self._format_result(
                        {"error": "Geçerli JSON formatı gerekli"},
                        "execute_command"
                    )
            else:
                args_dict = args_input
            
            node_name = args_dict.get("node_name", "")
            command = args_dict.get("command", "")
            
            if not node_name or not command:
                return self._format_result(
                    {"error": "Sunucu adı ve komut belirtilmeli"},
                    "execute_command"
                )
            
            if node_name not in self.monitor.get_available_nodes():
                return self._format_result(
                    {"error": f"'{node_name}' sunucusu bulunamadı"},
                    "execute_command"
                )
            
            # Güvenlik kontrolü - Sadece izin verilen komutlar
            allowed_commands = [
                "uptime", "hostname", "date", "df", "free", 
                "ps", "top", "netstat", "ss", "ip", "ifconfig",
                "cat /proc/cpuinfo", "cat /proc/meminfo", "lscpu",
                "systemctl status", "service", "journalctl"
            ]
            
            # Komutun güvenli olup olmadığını kontrol et
            is_safe = any(command.startswith(cmd) for cmd in allowed_commands)
            
            if not is_safe:
                return self._format_result(
                    {"error": f"Güvenlik: Bu komuta izin verilmiyor - {command}"},
                    "execute_command"
                )
            
            # Komutu çalıştır
            success, output = self.monitor.execute_command(node_name, command)
            
            result = {
                "node": node_name,
                "command": command,
                "success": success,
                "output": output if success else None,
                "error": output if not success else None
            }
            
            return self._format_result(result, "execute_command")
            
        except Exception as e:
            logger.error(f"Execute command hatası: {e}")
            return self._format_result({"error": str(e)}, "execute_command")
    
    def get_servers_by_tag(self, args_input) -> str:
        """Tag'e göre sunucuları listele"""
        try:
            # Argümanları parse et
            if isinstance(args_input, str):
                try:
                    args_dict = json.loads(args_input)
                except:
                    args_dict = {"tag": args_input.strip()}
            else:
                args_dict = args_input
            
            tag = args_dict.get("tag", "")
            
            if not tag:
                # Tüm tag'leri listele
                all_tags = set()
                for server_config in self.monitor.servers.values():
                    all_tags.update(server_config.get("tags", []))
                
                result = {
                    "available_tags": sorted(list(all_tags)),
                    "environment": self.monitor.environment
                }
            else:
                # Belirli tag'e sahip sunucuları bul
                nodes = self.monitor.get_nodes_by_tag(tag)
                
                result = {
                    "tag": tag,
                    "servers": nodes,
                    "count": len(nodes),
                    "environment": self.monitor.environment
                }
            
            return self._format_result(result, "servers_by_tag")
            
        except Exception as e:
            logger.error(f"Servers by tag hatası: {e}")
            return self._format_result({"error": str(e)}, "servers_by_tag")


def create_monitoring_tools(monitor: Optional[LinuxMonitor] = None) -> List[Tool]:
    """Monitoring tool'larını oluştur"""
    
    monitoring = MonitoringTools(monitor)
    
    tools = [
        Tool(
            name="check_server_status",
            description="""Linux sunucu durumunu kontrol et.
            Argüman: {"node_name": "sunucu_adı"} veya boş (tüm sunucular)
            Örnek: {"node_name": "mongodb-node1"}""",
            func=monitoring.check_server_status
        ),
        
        Tool(
            name="get_server_metrics",
            description="""Sunucu metriklerini al (CPU, Memory, Disk, Network).
            Argüman: {"node_name": "sunucu_adı", "metric_type": "all|cpu|memory|disk|network|mongodb"}
            Örnek: {"node_name": "mongodb-node1", "metric_type": "cpu"}""",
            func=monitoring.get_server_metrics
        ),
        
        Tool(
            name="find_resource_intensive_processes",
            description="""Kaynak tüketen işlemleri bul.
            Argüman: {"node_name": "sunucu_adı", "process_name": "opsiyonel_işlem_adı"}
            Örnek: {"node_name": "mongodb-node1", "process_name": "mongod"}""",
            func=monitoring.find_resource_intensive_processes
        ),
        
        Tool(
            name="execute_monitoring_command",
            description="""Güvenli monitoring komutu çalıştır.
            Argüman: {"node_name": "sunucu_adı", "command": "komut"}
            Örnek: {"node_name": "mongodb-node1", "command": "uptime"}""",
            func=monitoring.execute_monitoring_command
        ),
        
        Tool(
            name="get_servers_by_tag",
            description="""Tag'e göre sunucuları listele.
            Argüman: {"tag": "tag_adı"} veya boş (tüm tag'ler)
            Örnek: {"tag": "mongodb"}""",
            func=monitoring.get_servers_by_tag
        )
    ]
    
    return tools