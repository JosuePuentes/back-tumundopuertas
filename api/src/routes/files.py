from fastapi import APIRouter
import os
import boto3
from botocore.config import Config
from fastapi import Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

# Configuración de Cloudflare R2 desde variables de entorno
R2_BUCKET = os.getenv("VITE_R2_BUCKET")
R2_ACCOUNT_ID = os.getenv("VITE_R2_ACCOUNT_ID")
R2_ACCESS_KEY_ID = os.getenv("VITE_R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("VITE_R2_SECRET_ACCESS_KEY")

# Validar que todas las variables estén presentes
missing_vars = []
for var, val in [
    ("VITE_R2_BUCKET", R2_BUCKET),
    ("VITE_R2_ACCOUNT_ID", R2_ACCOUNT_ID),
    ("VITE_R2_ACCESS_KEY_ID", R2_ACCESS_KEY_ID),
    ("VITE_R2_SECRET_ACCESS_KEY", R2_SECRET_ACCESS_KEY),
]:
    if not val:
        missing_vars.append(var)
if missing_vars:
    raise RuntimeError(f"Faltan variables de entorno para Cloudflare R2: {', '.join(missing_vars)}")

R2_ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

s3_client = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT_URL,
    aws_access_key_id=R2_ACCESS_KEY_ID,
    aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    region_name="auto",
    config=Config(signature_version="s3v4")
)

router = APIRouter()

@router.post("/presigned-url")
async def get_presigned_url(request: Request):
    """
    Endpoint para generar una URL prefirmada para Cloudflare R2.
    """
    data = await request.json()
    object_name = data.get('object_name')
    operation = data.get('operation', 'get_object')
    expires_in = data.get('expires_in', 3600)
    content_type = data.get('content_type')

    if not object_name:
        return JSONResponse(status_code=400, content={"error": "Missing 'object_name' in request body"})

    try:
        if operation == 'get_object':
            presigned_url = s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': R2_BUCKET,
                    'Key': object_name
                },
                ExpiresIn=expires_in
            )
        elif operation == 'put_object':
            if not content_type:
                return JSONResponse(status_code=400, content={"error": "For 'put_object' operation, 'content_type' is required."})
            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': R2_BUCKET,
                    'Key': object_name,
                    'ContentType': content_type
                },
                ExpiresIn=expires_in
            )
        else:
            return JSONResponse(status_code=400, content={"error": "Invalid 'operation'. Must be 'get_object' or 'put_object'."})
        
        return {"presigned_url": presigned_url}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to generate presigned URL: {str(e)}"})

@router.post("/upload")
async def upload_file(request: Request):
    """
    Endpoint para subir archivos (comprobantes).
    En realidad, los archivos se suben usando presigned URLs desde el frontend.
    Este endpoint puede usarse para registrar la referencia del archivo en la BD.
    """
    try:
        data = await request.json()
        file_url = data.get("file_url")
        file_name = data.get("file_name")
        pedido_id = data.get("pedido_id")  # Opcional: asociar a un pedido
        
        if not file_url:
            return JSONResponse(status_code=400, content={"error": "file_url es requerido"})
        
        # Aquí puedes guardar la referencia del archivo en una colección si lo necesitas
        # Por ejemplo: archivos_collection.insert_one({"file_url": file_url, "file_name": file_name, "pedido_id": pedido_id})
        
        return {
            "message": "Archivo registrado exitosamente",
            "file_url": file_url,
            "file_name": file_name
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Error al registrar archivo: {str(e)}"})