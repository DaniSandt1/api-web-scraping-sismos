import requests
import boto3
import uuid
import os
from datetime import datetime

# La página https://ultimosismo.igp.gob.pe/productos/reportes-sismicos carga su tabla
# con JavaScript desde esta API JSON (la misma que usa la web del IGP).
URL_API_SISMOS_IGP = "https://ultimosismo.igp.gob.pe/api/ultimo-sismo/ajaxb/{anio}"
CANTIDAD_DE_SISMOS = 10


def obtener_sismos_del_anio(anio):
    respuesta_web = requests.get(
        URL_API_SISMOS_IGP.format(anio=anio),
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20
    )
    if respuesta_web.status_code != 200:
        return []
    return respuesta_web.json()


def lambda_handler(event, context):
    # 1. Web scraping: descargar los sismos del año actual
    anio_actual = datetime.now().year
    lista_de_sismos = obtener_sismos_del_anio(anio_actual)

    # Si es inicio de año y hay menos de 10 sismos, completar con el año anterior
    if len(lista_de_sismos) < CANTIDAD_DE_SISMOS:
        lista_de_sismos += obtener_sismos_del_anio(anio_actual - 1)

    if not lista_de_sismos:
        return {
            'statusCode': 404,
            'body': 'No se pudo obtener la información de sismos del IGP'
        }

    # 2. Ordenar del más reciente al más antiguo y quedarse con los 10 últimos
    lista_de_sismos.sort(
        key=lambda sismo: (str(sismo.get("fecha_local", "")), str(sismo.get("hora_local", ""))),
        reverse=True
    )
    ultimos_sismos = lista_de_sismos[:CANTIDAD_DE_SISMOS]

    # 3. Armar las filas a guardar (DynamoDB no acepta float, se guarda como texto)
    filas_a_guardar = []
    for numero_de_fila, sismo in enumerate(ultimos_sismos, start=1):
        fila_sismo = {
            'id': str(uuid.uuid4()),
            '#': numero_de_fila,
            'reporte_sismico': str(sismo.get("codigo", "")),
            'fecha_local': str(sismo.get("fecha_local", ""))[:10],
            'hora_local': str(sismo.get("hora_local", "")),
            'magnitud': str(sismo.get("magnitud", "")),
            'profundidad_km': str(sismo.get("profundidad", "")),
            'latitud': str(sismo.get("latitud", "")),
            'longitud': str(sismo.get("longitud", "")),
            'referencia': str(sismo.get("referencia", "")),
            'intensidad': str(sismo.get("intensidad", ""))
        }
        filas_a_guardar.append(fila_sismo)

    # 4. Guardar en DynamoDB (primero se borran los datos anteriores)
    dynamodb = boto3.resource('dynamodb')
    tabla_sismos = dynamodb.Table(os.environ["TABLE_NAME"])

    respuesta_scan = tabla_sismos.scan()
    with tabla_sismos.batch_writer() as escritor:
        for fila_antigua in respuesta_scan.get('Items', []):
            escritor.delete_item(Key={'id': fila_antigua['id']})

    with tabla_sismos.batch_writer() as escritor:
        for fila_sismo in filas_a_guardar:
            escritor.put_item(Item=fila_sismo)

    # 5. Respuesta
    return {
        'statusCode': 200,
        'body': filas_a_guardar
    }
