import datetime
import conexion

class WMSRepository:
    def __init__(self):
        self.oracle_initialized = False
        if conexion:
            self.oracle_initialized = conexion.init_oracle_client()

    def get_reservas_by_values(self, values):
        """
        Busca las reservas (THRD_PARTY_BILL) en WMS que correspondan a los
        valores provistos (ya sean reservas o números de PKT).
        """
        if not conexion or not self.oracle_initialized:
            return None, "Oracle Client no inicializado"

        # Preparar términos de búsqueda (el valor limpio e incluyendo la versión con '00' si no la tiene)
        search_terms = []
        for val in values:
            search_terms.append(val)
            if not val.startswith('00'):
                search_terms.append('00' + val)
        
        # Eliminar duplicados manteniendo orden
        search_terms = list(dict.fromkeys(search_terms))

        conn = None
        cur = None
        try:
            conn = conexion.get_connection()
            cur = conn.cursor()

            placeholders = ', '.join(f':v{i}' for i in range(len(search_terms)))
            query = f"""
            SELECT DISTINCT PKTHD.THRD_PARTY_BILL
            FROM PKT_HDR PKTHD 
            INNER JOIN PKT_HDR_INTRNL PKTIN 
            ON PKTHD.PKT_CTRL_NBR = PKTIN.PKT_CTRL_NBR 
            WHERE PKTHD.THRD_PARTY_BILL IN ({placeholders})
               OR PKTHD.PKT_CTRL_NBR IN ({placeholders})
            """
            
            bind_params = {f'v{i}': val for i, val in enumerate(search_terms)}
            cur.execute(query, bind_params)
            rows = cur.fetchall()
            
            reservas = [r[0] for r in rows if r[0]]
            return reservas, None
            
        except Exception as e:
            return None, f"Error buscando reservas en WMS: {e}"
        finally:
            if cur:
                try:
                    cur.close()
                except:
                    pass
            if conn:
                try:
                    conn.close()
                except:
                    pass

    def get_pkts_by_reservas(self, reservas):
        """
        Busca todos los PKTs asociados a un conjunto de reservas en WMS.
        """
        if not conexion or not self.oracle_initialized:
            return None, "Oracle Client no inicializado"

        if not reservas:
            return [], None

        conn = None
        cur = None
        try:
            conn = conexion.get_connection()
            cur = conn.cursor()

            placeholders = ', '.join(f':r{i}' for i in range(len(reservas)))
            query = f"""
            SELECT PKTHD.WHSE, 
                   PKTHD.PKT_CTRL_NBR, 
                   PKTHD.CUST_DEPT, 
                   PKTHD.ORD_NBR, 
                   PKTIN.STAT_CODE, 
                   PKTHD.THRD_PARTY_BILL, 
                   PKTHD.CREATE_DATE_TIME 
            FROM PKT_HDR PKTHD 
            INNER JOIN PKT_HDR_INTRNL PKTIN 
            ON PKTHD.PKT_CTRL_NBR = PKTIN.PKT_CTRL_NBR 
            WHERE PKTHD.THRD_PARTY_BILL IN ({placeholders})
            """
            
            bind_params = {f'r{i}': res for i, res in enumerate(reservas)}
            cur.execute(query, bind_params)
            rows = cur.fetchall()

            results = []
            for r in rows:
                create_dt = r[6]
                if isinstance(create_dt, datetime.datetime):
                    create_dt_str = create_dt.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    create_dt_str = str(create_dt) if create_dt else ''
                results.append({
                    'whse': r[0],
                    'pkt_ctrl_nbr': r[1],
                    'cust_dept': r[2],
                    'ord_nbr': r[3],
                    'stat_code': int(r[4]) if r[4] is not None else None,
                    'thrd_party_bill': r[5],
                    'create_date_time': create_dt_str
                })
            return results, None

        except Exception as e:
            return None, f"Error buscando PKTs por reservas en WMS: {e}"
        finally:
            if cur:
                try:
                    cur.close()
                except:
                    pass
            if conn:
                try:
                    conn.close()
                except:
                    pass
