"""
Tests for ProxyManager, including static proxy pools and dynamic session-based rotating proxies.
"""

import pytest
from app.core.config import get_settings
from app.core.proxy_manager import ProxyManager


def test_proxy_pool_comma_separated():
    """Verify that multiple proxies separated by commas are correctly loaded into a pool."""
    manager = ProxyManager()
    settings = get_settings()
    
    # Temporarily set proxy_url with comma-separated values
    original_url = settings.proxy_url
    original_rotation = settings.proxy_rotation
    
    try:
        settings.proxy_url = "http://proxy1.com:8000, http://proxy2.com:8080 ,http://proxy3.com"
        manager.setup()
        
        assert manager.enabled is True
        assert manager.pool_size == 3
        
        # Test round-robin rotation
        assert manager.get_proxy() == "http://proxy1.com:8000"
        assert manager.get_proxy() == "http://proxy2.com:8080"
        assert manager.get_proxy() == "http://proxy3.com"
        assert manager.get_proxy() == "http://proxy1.com:8000"  # Back to start
    finally:
        settings.proxy_url = original_url
        settings.proxy_rotation = original_rotation


def test_proxy_dynamic_session():
    """Verify that session-based residential proxies are dynamically rotated when enabled."""
    manager = ProxyManager()
    settings = get_settings()
    
    original_url = settings.proxy_url
    original_rotation = settings.proxy_rotation
    
    try:
        settings.proxy_url = "http://user-session-placeholder:pass@gate.residential.com:1000"
        settings.proxy_rotation = True
        manager.setup()
        
        proxy1 = manager.get_proxy()
        proxy2 = manager.get_proxy()
        
        # Ensure session strings are dynamically randomized and not equal
        assert "-session-" in proxy1
        assert "-session-" in proxy2
        assert proxy1 != proxy2
        assert "@gate.residential.com:1000" in proxy1
        
        # Now verify with proxy_rotation = False
        settings.proxy_rotation = False
        proxy3 = manager.get_proxy()
        assert proxy3 == "http://user-session-placeholder:pass@gate.residential.com:1000"
    finally:
        settings.proxy_url = original_url
        settings.proxy_rotation = original_rotation


def test_proxy_remove_dynamic_match():
    """Verify that dead proxies can be removed successfully even if they have dynamic session strings."""
    manager = ProxyManager()
    settings = get_settings()
    
    original_url = settings.proxy_url
    original_rotation = settings.proxy_rotation
    
    try:
        settings.proxy_url = "http://user-session-placeholder:pass@gate.residential.com:1000"
        settings.proxy_rotation = True
        manager.setup()
        
        assert manager.pool_size == 1
        
        # Simulating a failed request using a dynamic session-generated proxy
        dynamic_proxy = "http://user-session-abcdef12:pass@gate.residential.com:1000"
        manager.remove_proxy(dynamic_proxy)
        
        # Should match and remove the base proxy from the pool
        assert manager.pool_size == 0
        assert manager.enabled is False
    finally:
        settings.proxy_url = original_url
        settings.proxy_rotation = original_rotation
