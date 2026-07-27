"""
conexion_oracle.py - Gestión de conexiones Oracle
  - Conexión WMS : svr35001.falabella.com / wmosxdpr  (principal)
  - Conexión DAD : f1s01976.falabella.cl  / DADPEPR   (secundaria)
"""
import os
import oracledb

# ── THICK MODE ────────────────────────────────────────────────────────────
ORACLE_CLIENT_PATH = os.environ.get("ORACLE_CLIENT_LIB", r"C:\oracle\instantclient_11_2")
_thick_initialized = False

def init_oracle_client():
    global _thick_initialized
    if _thick_initialized:
        return True
    try:
        oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
        _thick_initialized = True
        print(f"[OK] Oracle Client inicializado: {ORACLE_CLIENT_PATH}")
        return True
    except Exception as e:
        print(f"[ERROR] init_oracle_client: {e}")
        return False

# ── DSN HELPERS ───────────────────────────────────────────────────────────
def _make_dsn(host_env, port_env, sid_env, host_default, port_default, sid_default):
    return oracledb.makedsn(
        os.environ.get(host_env, host_default),
        int(os.environ.get(port_env, port_default)),
        sid=os.environ.get(sid_env, sid_default),
    )

# ── CONFIGURACIÓN WMS (principal) ─────────────────────────────────────────
WMS_CONFIG = {
    "user":     os.environ.get("ORACLE_USER",     "PNAVARROV"),
    "password": os.environ.get("ORACLE_PASSWORD", ""),
    "dsn":      _make_dsn("ORACLE_HOST", "ORACLE_PORT", "ORACLE_SID",
                          "svr35001.falabella.com", "1531", "wmosxdpr"),
}

# ── CONFIGURACIÓN DAD (secundaria) ────────────────────────────────────────
DAD_CONFIG = {
    "user":     os.environ.get("DAD_USER",     "logistica_pr"),
    "password": os.environ.get("DAD_PASSWORD", ""),
    "dsn":      _make_dsn("DAD_HOST", "DAD_PORT", "odspepr",
                          "apros.falabella.cl", "1531", "odspepr"),
}

# ── CONEXIONES ────────────────────────────────────────────────────────────
def get_connection():
    """Retorna conexión a WMS (principal)."""
    try:
        return oracledb.connect(**WMS_CONFIG)
    except oracledb.DatabaseError as e:
        error, = e.args
        raise Exception(f"[WMS] Error {getattr(error, 'code', '')}: {getattr(error, 'message', str(error))}")

def get_connection_dad():
    """Retorna conexión a DAD (secundaria)."""
    try:
        return oracledb.connect(**DAD_CONFIG)
    except oracledb.DatabaseError as e:
        error, = e.args
        raise Exception(f"[DAD] Error {getattr(error, 'code', '')}: {getattr(error, 'message', str(error))}")

# ── TEST ──────────────────────────────────────────────────────────────────
def test_connection(config_name: str = "WMS"):
    if not init_oracle_client():
        print("No se pudo inicializar Oracle Client")
        return
    fn = get_connection if config_name == "WMS" else get_connection_dad
    try:
        conn = fn()
        cur = conn.cursor()
        cur.execute("SELECT USER, 'OK' FROM DUAL")
        user, status = cur.fetchone()
        print(f"[{config_name}] OK — Usuario: {user}")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[{config_name}] FALLO — {e}")

if __name__ == "__main__":
    print("=" * 50)
    test_connection("WMS")
    test_connection("DAD")
    print("=" * 50)