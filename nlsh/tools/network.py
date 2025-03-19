"""
Network information tool.

This module provides a tool for gathering network information.
"""

import os
import socket
import subprocess
import platform
from typing import List, Dict, Any, Tuple

from nlsh.tools.base import BaseTool


class NetworkInfo(BaseTool):
    """Lists open ports and active connections relevant to network commands."""
    
    def get_context(self):
        """Get network information.
        
        Returns:
            str: Formatted network information.
        """
        result = []
        
        # Get hostname and IP addresses
        hostname, ips = self._get_host_info()
        result.append(f"Hostname: {hostname}")
        
        if ips:
            result.append("IP Addresses:")
            for name, ip in ips:
                result.append(f"- {name}: {ip}")
        
        # Get listening ports
        listening_ports = self._get_listening_ports()
        if listening_ports:
            result.append("\nListening Ports:")
            for port_info in listening_ports:
                result.append(f"- {port_info}")
        
        # Get active connections
        active_connections = self._get_active_connections()
        if active_connections:
            result.append("\nActive Connections:")
            for conn_info in active_connections[:10]:  # Limit to 10 connections to avoid overwhelming
                result.append(f"- {conn_info}")
            
            if len(active_connections) > 10:
                result.append(f"  ... and {len(active_connections) - 10} more connections")
        
        # Get network interfaces
        interfaces = self._get_network_interfaces()
        if interfaces:
            result.append("\nNetwork Interfaces:")
            for iface in interfaces:
                result.append(f"- {iface}")
        
        return "\n".join(result)
    
    def _get_host_info(self) -> Tuple[str, List[Tuple[str, str]]]:
        """Get hostname and IP addresses.
        
        Returns:
            tuple: (hostname, list of (interface_name, ip_address) tuples)
        """
        hostname = socket.gethostname()
        ips = []
        
        try:
            # Get all IP addresses
            if platform.system() == "Linux" or platform.system() == "Darwin":
                # Use ifconfig on Linux and macOS
                cmd = ["ifconfig"] if platform.system() == "Darwin" else ["ip", "addr", "show"]
                output = subprocess.check_output(
                    cmd,
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                current_iface = None
                for line in output.splitlines():
                    if line.strip() and not line.startswith(" "):
                        # This is an interface line
                        current_iface = line.split(":")[0].strip()
                    elif "inet " in line and current_iface:
                        # This is an IPv4 address line
                        parts = line.strip().split()
                        for i, part in enumerate(parts):
                            if part == "inet":
                                ip = parts[i+1].split("/")[0]
                                if not ip.startswith("127."):  # Skip localhost
                                    ips.append((current_iface, ip))
                                break
                
            elif platform.system() == "Windows":
                # Use ipconfig on Windows
                output = subprocess.check_output(
                    ["ipconfig"],
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                current_iface = None
                for line in output.splitlines():
                    line = line.strip()
                    if line and ":" in line and not line.startswith("   "):
                        current_iface = line.split(":")[0].strip()
                    elif "IPv4 Address" in line and current_iface:
                        ip = line.split(":")[-1].strip()
                        ips.append((current_iface, ip))
        
        except (subprocess.SubprocessError, FileNotFoundError):
            # If the command fails, try a simpler approach
            try:
                # Get the primary IP address
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
                s.close()
                ips.append(("primary", ip))
            except:
                pass
        
        return hostname, ips
    
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
    
    def _get_active_connections(self) -> List[str]:
        """Get list of active network connections.
        
        Returns:
            list: List of connection information strings.
        """
        connections = []
        
        try:
            if platform.system() == "Linux" or platform.system() == "Darwin":
                # Use netstat on Linux and macOS
                cmd = ["netstat", "-tn"]
                
                output = subprocess.check_output(
                    cmd,
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                for line in output.strip().split("\n"):
                    if "ESTABLISHED" in line:
                        parts = line.split()
                        if len(parts) >= 4:
                            local = parts[3]
                            remote = parts[4]
                            connections.append(f"{local} -> {remote}")
                                
            elif platform.system() == "Windows":
                # Use netstat on Windows
                output = subprocess.check_output(
                    ["netstat", "-n"],
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                for line in output.strip().split("\n"):
                    if "ESTABLISHED" in line:
                        parts = line.split()
                        if len(parts) >= 3:
                            local = parts[1]
                            remote = parts[2]
                            connections.append(f"{local} -> {remote}")
                                    
        except (subprocess.SubprocessError, FileNotFoundError):
            # If the command fails, return an empty list
            pass
            
        return connections
    
    def _get_network_interfaces(self) -> List[str]:
        """Get list of network interfaces.
        
        Returns:
            list: List of interface information strings.
        """
        interfaces = []
        
        try:
            if platform.system() == "Linux":
                # Use ip on Linux
                output = subprocess.check_output(
                    ["ip", "link", "show"],
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                for line in output.strip().split("\n"):
                    if ":" in line and not line.startswith(" "):
                        parts = line.split(":", 2)
                        if len(parts) >= 2:
                            iface_num = parts[0].strip()
                            iface_name = parts[1].strip()
                            if "state UP" in line:
                                interfaces.append(f"{iface_name} (UP)")
                            elif "state DOWN" in line:
                                interfaces.append(f"{iface_name} (DOWN)")
                            else:
                                interfaces.append(iface_name)
                                
            elif platform.system() == "Darwin":
                # Use ifconfig on macOS
                output = subprocess.check_output(
                    ["ifconfig"],
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                for line in output.strip().split("\n"):
                    if ":" in line and not line.startswith("\t"):
                        parts = line.split(":", 1)
                        if len(parts) >= 1:
                            iface_name = parts[0].strip()
                            if "status: active" in output.split(iface_name)[1].split("\n\n")[0]:
                                interfaces.append(f"{iface_name} (UP)")
                            else:
                                interfaces.append(iface_name)
                                
            elif platform.system() == "Windows":
                # Use ipconfig on Windows
                output = subprocess.check_output(
                    ["ipconfig"],
                    stderr=subprocess.DEVNULL,
                    text=True
                )
                
                for line in output.strip().split("\n"):
                    if "adapter" in line.lower() and ":" in line:
                        iface_name = line.split(":")[0].strip()
                        interfaces.append(iface_name)
                                    
        except (subprocess.SubprocessError, FileNotFoundError):
            # If the command fails, return an empty list
            pass
            
        return interfaces
