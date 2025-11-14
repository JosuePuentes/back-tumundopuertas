"""
Sistema de caché simple para optimizar consultas frecuentes.
Usa un diccionario en memoria con TTL (Time To Live).
"""
from datetime import datetime, timedelta
from typing import Any, Optional, Dict
import threading

class SimpleCache:
    """Caché simple con TTL (Time To Live) en memoria"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Obtener valor del caché si existe y no ha expirado"""
        with self._lock:
            if key not in self._cache:
                return None
            
            entry = self._cache[key]
            expires_at = entry.get("expires_at")
            
            # Si expiró, eliminar y retornar None
            if expires_at and datetime.now() > expires_at:
                del self._cache[key]
                return None
            
            return entry.get("value")
    
    def set(self, key: str, value: Any, ttl_seconds: int = 60):
        """Guardar valor en caché con TTL en segundos"""
        with self._lock:
            expires_at = datetime.now() + timedelta(seconds=ttl_seconds)
            self._cache[key] = {
                "value": value,
                "expires_at": expires_at,
                "created_at": datetime.now()
            }
    
    def delete(self, key: str):
        """Eliminar entrada del caché"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    def clear(self):
        """Limpiar todo el caché"""
        with self._lock:
            self._cache.clear()
    
    def cleanup_expired(self):
        """Limpiar entradas expiradas"""
        with self._lock:
            now = datetime.now()
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.get("expires_at") and now > entry.get("expires_at")
            ]
            for key in expired_keys:
                del self._cache[key]

# Instancia global del caché
cache = SimpleCache()

# Claves de caché comunes
CACHE_KEY_EMPLEADOS = "empleados_list"
CACHE_KEY_ASIGNACIONES = "asignaciones_activas"
CACHE_KEY_ASIGNACIONES_MODULO = "asignaciones_modulo_{modulo}"

