"""
Process monitoring tool.

This module provides a tool for identifying running processes.
"""

import os
import subprocess
import platform
from typing import List, Dict, Any

from nlsh.tools.base import BaseTool


class ProcessSniffer(BaseTool):
    """Identifies running processes that might conflict with generated commands."""
    
    # List of important process attributes to capture
    PROCESS_ATTRIBUTES = ["pid", "name", "cmd", "user", "status"]
    
    # List of important processes to highlight (e.g., servers, databases)
    IMPORTANT_PROCESS_PATTERNS = [
        "nginx", "apache", "httpd", "mysql", "postgres", "mongodb",
        "redis", "memcached", "docker", "containerd", "node", "python",
        "java", "tomcat", "gunicorn", "uwsgi", "php-fpm", "ruby",
        "elasticsearch", "cassandra", "kafka", "zookeeper", "rabbitmq",
        "supervisord", "systemd", "init", "cron", "ssh", "sshd"
    ]
    
    def get_context(self):
        """Get information about running processes.
        
        Returns:
            str: Formatted process information.
        """
        # Get list of processes
        processes = self._get_processes()
        
        # Filter and format the processes
        important_processes = self._filter_important_processes(processes)
        
        # Format the output
        if not important_processes:
            return "No important processes detected."
            
        result = ["Important running processes:"]
        for proc in important_processes:
            proc_info = []
            if "name" in proc:
                proc_info.append(proc["name"])
            if "pid" in proc:
                proc_info.append(f"PID: {proc['pid']}")
            if "user" in proc:
                proc_info.append(f"User: {proc['user']}")
            if "status" in proc:
                proc_info.append(f"Status: {proc['status']}")
                
            result.append(f"- {', '.join(proc_info)}")
            
            # Add command line if available
            if "cmd" in proc and proc["cmd"]:
                cmd = proc["cmd"]
                # Truncate very long command lines
                if len(cmd) > 100:
                    cmd = cmd[:97] + "..."
                result.append(f"  Command: {cmd}")
                
        # Add listening ports if available
        ports = self._get_listening_ports()
        if ports:
            result.append("\nListening ports:")
            for port_info in ports:
                result.append(f"- {port_info}")
                
        return "\n".join(result)
    
    def _get_processes(self) -> List[Dict[str, Any]]:
        """Get list of running processes.
        
        Returns:
            list: List of process dictionaries.
        """
        processes = []
        
        try:
            if platform.system() == "Linux" or platform.system() == "Darwin":
                # Use ps on Linux and macOS
                output = subprocess.check_output(
                    ["ps", "-eo", "pid,user,stat,comm,args"],
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                lines = output.strip().split("\n")
                headers = lines[0].strip().lower().split()
                
                for line in lines[1:]:
                    parts = line.strip().split(None, 4)
                    if len(parts) >= 5:
                        process = {
                            "pid": parts[0],
                            "user": parts[1],
                            "status": parts[2],
                            "name": parts[3],
                            "cmd": parts[4]
                        }
                        processes.append(process)
                        
            elif platform.system() == "Windows":
                # Use WMIC on Windows
                output = subprocess.check_output(
                    ["wmic", "process", "get", "ProcessId,Name,CommandLine,Status,Caption"],
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                lines = output.strip().split("\n")
                # Parse the header line to get column positions
                header_line = lines[0].strip().lower()
                
                for line in lines[1:]:
                    if not line.strip():
                        continue
                        
                    # Very basic parsing - this could be improved
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        process = {
                            "pid": parts[0],
                            "name": parts[1],
                            "cmd": " ".join(parts[2:]) if len(parts) > 2 else ""
                        }
                        processes.append(process)
                        
        except (subprocess.SubprocessError, FileNotFoundError):
            # If the command fails, return an empty list
            pass
            
        return processes
    
    def _filter_important_processes(self, processes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter processes to only include important ones.
        
        Args:
            processes: List of all processes.
            
        Returns:
            list: List of important processes.
        """
        important = []
        
        for proc in processes:
            # Check if the process name or command matches any important pattern
            name = proc.get("name", "").lower()
            cmd = proc.get("cmd", "").lower()
            
            if any(pattern in name or pattern in cmd for pattern in self.IMPORTANT_PROCESS_PATTERNS):
                important.append(proc)
                
        return important
    
    def _get_listening_ports(self) -> List[str]:
        """Get list of listening ports.
        
        Returns:
            list: List of port information strings.
        """
        ports = []
        
        try:
            if platform.system() == "Linux" or platform.system() == "Darwin":
                # Use netstat on Linux and macOS
                cmd = ["netstat", "-tuln"]
                if platform.system() == "Linux":
                    cmd.append("p")  # Add process info on Linux
                    
                output = subprocess.check_output(
                    cmd,
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                for line in output.strip().split("\n"):
                    if "LISTEN" in line:
                        # Extract the local address (IP:port)
                        parts = line.split()
                        for part in parts:
                            if ":" in part and any(c.isdigit() for c in part):
                                local_addr = part
                                # Extract just the port number
                                port = local_addr.split(":")[-1]
                                if port.isdigit():
                                    # Add process name if available (Linux only)
                                    if platform.system() == "Linux" and len(parts) > 6:
                                        process = parts[6].split("/")[1] if "/" in parts[6] else parts[6]
                                        ports.append(f"Port {port} - {process}")
                                    else:
                                        ports.append(f"Port {port}")
                                break
                                
            elif platform.system() == "Windows":
                # Use netstat on Windows
                output = subprocess.check_output(
                    ["netstat", "-ano"],
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                for line in output.strip().split("\n"):
                    if "LISTENING" in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            local_addr = parts[1]
                            # Extract just the port number
                            port = local_addr.split(":")[-1]
                            if port.isdigit():
                                # Add process ID
                                if len(parts) >= 5:
                                    pid = parts[4]
                                    ports.append(f"Port {port} - PID {pid}")
                                else:
                                    ports.append(f"Port {port}")
                                    
        except (subprocess.SubprocessError, FileNotFoundError):
            # If the command fails, return an empty list
            pass
            
        return ports
