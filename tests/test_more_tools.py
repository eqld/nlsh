"""
Tests for the additional system tools.
"""

import os
import re
import socket
import platform
import subprocess
from unittest.mock import patch, MagicMock, mock_open

import pytest

from nlsh.config import Config
from nlsh.tools.environment import EnvInspector
from nlsh.tools.shell import ShellHistoryInspector
from nlsh.tools.process import ProcessSniffer
from nlsh.tools.network import NetworkInfo


class TestEnvInspector:
    """Tests for the EnvInspector tool."""
    
    def test_get_context(self):
        """Test that get_context returns environment variables."""
        # Create a mock config
        config = MagicMock()
        
        # Create a mock environment
        mock_env = {
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/user",
            "SHELL": "/bin/bash",
            "USER": "testuser",
            "SECRET_TOKEN": "sensitive_data",
            "API_KEY": "another_sensitive_data"
        }
        
        with patch.dict(os.environ, mock_env, clear=True):
            # Create an instance of EnvInspector
            tool = EnvInspector(config)
            
            # Get the context
            context = tool.get_context()
            
            # Check that the context contains expected information
            assert isinstance(context, str)
            assert "Environment Variables:" in context
            # Use more flexible assertions that don't depend on exact formatting
            assert "PATH" in context
            assert "/usr/bin" in context
            assert "/bin" in context
            assert "SHELL" in context
            assert "/bin/bash" in context
            
            # Check that sensitive information is redacted
            assert "SECRET_TOKEN=[REDACTED]" in context or "SECRET_TOKEN" in context and "sensitive_data" not in context
            assert "API_KEY=[REDACTED]" in context or "API_KEY" in context and "another_sensitive_data" not in context
            assert "sensitive_data" not in context
            assert "another_sensitive_data" not in context


class TestShellHistoryInspector:
    """Tests for the ShellHistoryInspector tool."""
    
    def test_get_context_from_command(self):
        """Test getting history from shell command."""
        # Create a mock config
        config = MagicMock()
        config.get_shell.return_value = "bash"
        
        # Create a mock subprocess output
        mock_history_output = "  1  ls -la\n  2  cd /tmp\n  3  echo 'hello'\n"
        
        with patch('subprocess.check_output', return_value=mock_history_output):
            # Create an instance of ShellHistoryInspector
            tool = ShellHistoryInspector(config)
            
            # Get the context
            context = tool.get_context()
            
            # Check that the context contains expected information
            assert isinstance(context, str)
            assert "Recent command history:" in context
            assert "ls -la" in context
            assert "cd /tmp" in context
            assert "echo 'hello'" in context
    
    def test_get_context_from_file(self):
        """Test getting history from history file."""
        # Create a mock config
        config = MagicMock()
        config.get_shell.return_value = "bash"
        
        # Create a mock history file content
        mock_history_content = "ls -la\ncd /tmp\necho 'hello'\n"
        
        # Mock subprocess.check_output to fail so we fall back to file reading
        with patch('subprocess.check_output', side_effect=subprocess.SubprocessError), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=mock_history_content)):
            
            # Create an instance of ShellHistoryInspector
            tool = ShellHistoryInspector(config)
            
            # Get the context
            context = tool.get_context()
            
            # Check that the context contains expected information
            assert isinstance(context, str)
            assert "Recent command history:" in context
            assert "ls -la" in context
            assert "cd /tmp" in context
            assert "echo 'hello'" in context
    
    def test_get_context_no_history(self):
        """Test behavior when no history is available."""
        # Create a mock config
        config = MagicMock()
        config.get_shell.return_value = "unknown_shell"
        
        # Mock both methods to fail
        with patch('subprocess.check_output', side_effect=subprocess.SubprocessError), \
             patch('os.path.exists', return_value=False):
            
            # Create an instance of ShellHistoryInspector
            tool = ShellHistoryInspector(config)
            
            # Get the context
            context = tool.get_context()
            
            # Check that the context contains expected information
            assert isinstance(context, str)
            assert "Could not retrieve command history" in context


class TestProcessSniffer:
    """Tests for the ProcessSniffer tool."""
    
    def test_get_context(self):
        """Test that get_context returns process information."""
        # Create a mock config
        config = MagicMock()
        
        # Create a mock process list output
        mock_ps_output = """  PID USER     STAT COMMAND ARGS
  123 user     S    nginx   nginx -g 'daemon off;'
  456 user     S    python  python3 server.py
  789 user     S    bash    bash
"""
        
        # Create a mock netstat output for listening ports
        mock_netstat_output = """Proto Recv-Q Send-Q Local Address           Foreign Address         State
tcp        0      0 0.0.0.0:80              0.0.0.0:*               LISTEN
tcp        0      0 0.0.0.0:443             0.0.0.0:*               LISTEN
"""
        
        with patch('platform.system', return_value='Linux'), \
             patch('subprocess.check_output', side_effect=[mock_ps_output, mock_netstat_output]):
            
            # Create an instance of ProcessSniffer
            tool = ProcessSniffer(config)
            
            # Get the context
            context = tool.get_context()
            
            # Check that the context contains expected information
            assert isinstance(context, str)
            assert "Important running processes:" in context
            assert "nginx" in context
            assert "python" in context
            assert "Listening ports:" in context
            assert "Port 80" in context
            assert "Port 443" in context
    
    def test_get_context_no_processes(self):
        """Test behavior when no important processes are found."""
        # Create a mock config
        config = MagicMock()
        
        # Create a mock process list with no important processes
        mock_ps_output = """  PID USER     STAT COMMAND ARGS
  789 user     S    bash    bash
"""
        
        # Create an empty netstat output
        mock_netstat_output = ""
        
        with patch('platform.system', return_value='Linux'), \
             patch('subprocess.check_output', side_effect=[mock_ps_output, mock_netstat_output]):
            
            # Create an instance of ProcessSniffer
            tool = ProcessSniffer(config)
            
            # Get the context
            context = tool.get_context()
            
            # Check that the context contains expected information
            assert isinstance(context, str)
            assert "No important processes detected" in context


class TestNetworkInfo:
    """Tests for the NetworkInfo tool."""
    
    def test_get_context(self):
        """Test that get_context returns network information."""
        # Create a mock config
        config = MagicMock()
        
        # Mock hostname and IP addresses
        hostname = "testhost"
        
        # Mock ifconfig/ip output
        mock_ip_output = """1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    link/ether 00:00:00:00:00:00 brd ff:ff:ff:ff:ff:ff
    inet 192.168.1.100/24 brd 192.168.1.255 scope global dynamic eth0
       valid_lft 86389sec preferred_lft 86389sec
"""
        
        # Mock netstat output for listening ports
        mock_netstat_output = """Proto Recv-Q Send-Q Local Address           Foreign Address         State
tcp        0      0 0.0.0.0:80              0.0.0.0:*               LISTEN
tcp        0      0 0.0.0.0:443             0.0.0.0:*               LISTEN
"""
        
        # Mock netstat output for active connections
        mock_netstat_conn_output = """Proto Recv-Q Send-Q Local Address           Foreign Address         State
tcp        0      0 192.168.1.100:54321     93.184.216.34:443       ESTABLISHED
tcp        0      0 192.168.1.100:54322     93.184.216.34:80        ESTABLISHED
"""
        
        # Mock ip link output
        mock_ip_link_output = """1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UP mode DEFAULT group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP mode DEFAULT group default qlen 1000
    link/ether 00:00:00:00:00:00 brd ff:ff:ff:ff:ff:ff
"""
        
        with patch('socket.gethostname', return_value=hostname), \
             patch('platform.system', return_value='Linux'), \
             patch('subprocess.check_output', side_effect=[mock_ip_output, mock_netstat_output, mock_netstat_conn_output, mock_ip_link_output]):
            
            # Create an instance of NetworkInfo
            tool = NetworkInfo(config)
            
            # Get the context
            context = tool.get_context()
            
            # Check that the context contains expected information
            assert isinstance(context, str)
            assert f"Hostname: {hostname}" in context
            assert "IP Addresses:" in context
            # Use more flexible assertions that don't depend on exact formatting
            assert "192.168.1.100" in context
            assert "Listening Ports:" in context
            assert "Port 80" in context
            assert "Port 443" in context
            assert "Active Connections:" in context
            assert "192.168.1.100:54321" in context
            assert "93.184.216.34:443" in context
            assert "Network Interfaces:" in context
            assert "eth0" in context
    
    def test_get_context_fallback(self):
        """Test fallback behavior when commands fail."""
        # Create a mock config
        config = MagicMock()
        
        # Mock hostname
        hostname = "testhost"
        
        # Mock socket connection for fallback IP detection
        mock_socket = MagicMock()
        mock_socket.getsockname.return_value = ("192.168.1.100", 0)
        
        with patch('socket.gethostname', return_value=hostname), \
             patch('platform.system', return_value='Linux'), \
             patch('subprocess.check_output', side_effect=subprocess.SubprocessError), \
             patch('socket.socket', return_value=mock_socket):
            
            # Create an instance of NetworkInfo
            tool = NetworkInfo(config)
            
            # Get the context
            context = tool.get_context()
            
            # Check that the context contains expected information
            assert isinstance(context, str)
            assert f"Hostname: {hostname}" in context
            assert "IP Addresses:" in context
            assert "192.168.1.100" in context
