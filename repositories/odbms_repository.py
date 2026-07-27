import conexion

class ODBMSRepository:
    def __init__(self):
        self.oracle_initialized = False
        if conexion:
            self.oracle_initialized = conexion.init_oracle_client()

    def get_pedido_detalles(self, order_id):
        """
        Ejecuta la Query 3 en ODBMS (conexión DAD) para traer todos los detalles
        del pedido dado (asociaciones SKU, estados y cantidades).
        """
        if not conexion or not self.oracle_initialized:
            return None, "Oracle Client no inicializado"

        query = """
        SELECT S.SOD_REQ_HDR_ID AS PEDIDO, 
               TRIM(PR.PRD_LVL_NUMBER) AS SKU, 
               TRIM(C.REQ_STATUS_DESC) AS ESTADOPEDIDO,
               DECODE(A.ASG_STATUS, '1', 'PDTE.', '2', 'DESPACHADO', '3', 'CANCELADO', A.ASG_STATUS) AS EST_PKT,
               (A.REQ_ORC_CD_QTY - NVL(A.ASG_QTY_CANCEL, 0) - NVL(A.ASG_QTY_GUIA, 0)) AS CANTIDADPENDIENTE,
               TRIM(A.ASG_NUM_DOC) AS DIST_PKT,
               O2.ORG_LVL_NUMBER AS BODEGA
        FROM (((((SODREOEE S 
        INNER JOIN PRDMSTEE PR ON PR.PRD_LVL_CHILD = S.PRD_LVL_CHILD)
        INNER JOIN ORGMSTEE O1 ON S.ORG_LVL_CHILD = O1.ORG_LVL_CHILD
        LEFT JOIN ORGMSTEE O2 ON S.WHS_LVL_CHILD = O2.ORG_LVL_CHILD)
        INNER JOIN SODRQSCD C ON C.REQ_STATUS = S.REQ_STATUS)))
        LEFT JOIN ((ASGREOWW A 
        LEFT JOIN ORGMSTEE O3 ON A.WHS_LVL_CHILD = O3.ORG_LVL_CHILD)
        INNER JOIN ORGMSTEE O4 ON A.ORG_LVL_CHILD = O4.ORG_LVL_CHILD)
        ON A.SOD_REQ_HDR_ID = S.SOD_REQ_HDR_ID AND A.PRD_LVL_CHILD = S.PRD_LVL_CHILD
        WHERE S.SOD_REQ_HDR_ID = :order_id
        """

        conn = None
        cur = None
        try:
            conn = conexion.get_connection_dad()
            cur = conn.cursor()
            cur.execute(query, {'order_id': order_id})
            rows = cur.fetchall()

            results = []
            for r in rows:
                results.append({
                    'pedido': r[0],
                    'sku': r[1],
                    'estadopedido': r[2],
                    'est_pkt': r[3],
                    'cantidadpendiente': float(r[4]) if r[4] is not None else 0.0,
                    'dist_pkt': r[5] if r[5] else '',
                    'bodega': r[6] if r[6] else ''
                })
            return results, None
        except Exception as e:
            return None, f"Error consultando detalles del pedido en ODBMS: {e}"
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

    def get_sku_stock(self, cc, sku):
        """
        Ejecuta la Query 4 en ODBMS (conexión DAD) para validar saldo disponible para un SKU y bodega.
        """
        if not conexion or not self.oracle_initialized:
            return None, "Oracle Client no inicializado"

        query = """
        SELECT SF.CC, SF.TIENDA, SF.SKU, SF.DESCRIP, SF.DISPONIBLE, SF.RSV_CLIENTE, SF.ASIGNADO, SF.RESERVADO, SF.EN_PROCESO, SF.DISPO_DAD,
        SUM(SF.DISPONIBLE + SF.RSV_CLIENTE + SF.ASIGNADO + SF.RESERVADO + SF.EN_PROCESO + SF.DISPO_DAD) AS TOTAL
        FROM (
            SELECT O.ORG_LVL_NUMBER CC, TRIM(P.PRD_LVL_NUMBER) SKU, TRIM(P.PRD_NAME_FULL) DESCRIP, TRIM(O.ORG_NAME_FULL) TIENDA,
            SUM(DECODE(I.INV_TYPE_CODE, '01', I.ON_HAND_QTY, 0)) AS DISPONIBLE,
            SUM(DECODE(I.INV_TYPE_CODE, '09', I.ON_HAND_QTY, 0)) AS RSV_CLIENTE,
            SUM(DECODE(I.INV_TYPE_CODE, '10', I.ON_HAND_QTY, 0)) AS ASIGNADO,
            SUM(DECODE(I.INV_TYPE_CODE, '11', I.ON_HAND_QTY, 0)) AS RESERVADO,
            SUM(DECODE(I.INV_TYPE_CODE, '13', I.ON_HAND_QTY, 0)) AS EN_PROCESO,
            SUM(DECODE(I.INV_TYPE_CODE, '14', I.ON_HAND_QTY, 0)) AS DISPO_DAD
            FROM INVBALEE I, PRDMSTEE P, ORGMSTEE O
            WHERE P.PRD_LVL_CHILD = I.PRD_LVL_CHILD
              AND I.ORG_LVL_CHILD = O.ORG_LVL_CHILD
              AND I.INV_TYPE_CODE IN ('01','09','10','11','13','14')
              AND O.ORG_LVL_NUMBER = :cc
              AND P.PRD_LVL_NUMBER = :sku
            GROUP BY O.ORG_LVL_NUMBER, TRIM(P.PRD_LVL_NUMBER), TRIM(P.PRD_NAME_FULL), TRIM(O.ORG_NAME_FULL)
        ) SF
        GROUP BY SF.CC, SF.TIENDA, SF.SKU, SF.DESCRIP, SF.DISPONIBLE, SF.RSV_CLIENTE, SF.ASIGNADO, SF.RESERVADO, SF.EN_PROCESO, SF.DISPO_DAD
        """

        conn = None
        cur = None
        try:
            conn = conexion.get_connection_dad()
            cur = conn.cursor()
            cur.execute(query, {'cc': cc, 'sku': sku})
            row = cur.fetchone()
            if row:
                return {
                    'cc': row[0],
                    'tienda': row[1],
                    'sku': row[2],
                    'descrip': row[3],
                    'disponible': float(row[4]) if row[4] is not None else 0.0,
                    'rsv_cliente': float(row[5]) if row[5] is not None else 0.0,
                    'asignado': float(row[6]) if row[6] is not None else 0.0,
                    'reservado': float(row[7]) if row[7] is not None else 0.0,
                    'en_proceso': float(row[8]) if row[8] is not None else 0.0,
                    'dispo_dad': float(row[9]) if row[9] is not None else 0.0,
                    'total': float(row[10]) if row[10] is not None else 0.0
                }, None
            return None, None
        except Exception as e:
            return None, f"Error consultando stock en ODBMS: {e}"
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
