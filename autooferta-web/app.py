#!/usr/bin/env python3
"""
AutoOferta — API web (FastAPI). Versión de despliegue (archivos planos).

    export ANTHROPIC_API_KEY=sk-ant-...
    uvicorn app:app --host 0.0.0.0 --port 8000

Sin ANTHROPIC_API_KEY arranca en MODO DEMO: /procesar devuelve la salida de ejemplo.
"""
import os
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

app = FastAPI(title="AutoOferta", version="1.0")
BASE = Path(__file__).parent
TRABAJO = BASE / "trabajos"; TRABAJO.mkdir(exist_ok=True)
DEMO_MODE = not os.environ.get("ANTHROPIC_API_KEY")


@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "index.html").read_text(encoding="utf-8")


@app.get("/salud")
def salud():
    return {"ok": True, "modo": "demo" if DEMO_MODE else "real"}


@app.post("/procesar")
async def procesar(pliego: UploadFile = File(...), perfil: UploadFile = File(...)):
    if not pliego.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "El pliego debe ser un PDF.")
    job_id = uuid.uuid4().hex[:12]
    carpeta = TRABAJO / job_id; carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "pliego.pdf").write_bytes(await pliego.read())
    perfil_data = json.loads((await perfil.read()).decode("utf-8"))

    if DEMO_MODE:
        analisis = json.loads((BASE / "demo_analisis.json").read_text(encoding="utf-8"))
        checklist = json.loads((BASE / "demo_checklist.json").read_text(encoding="utf-8"))
        (carpeta / "memoria_tecnica.docx").write_bytes((BASE / "demo_memoria.docx").read_bytes())
        return JSONResponse({"job_id": job_id, "modo": "demo", "analisis": analisis,
                             "checklist": checklist,
                             "memoria_descarga": f"/descargas/{job_id}/memoria_tecnica.docx"})

    from engine import procesar_licitacion
    try:
        res = procesar_licitacion(carpeta / "pliego.pdf", perfil_data, carpeta)
    except Exception as e:
        raise HTTPException(500, f"Error procesando el pliego: {e}")
    return JSONResponse({"job_id": job_id, "modo": "real", "analisis": res["analisis"],
                         "checklist": res["checklist"],
                         "memoria_descarga": f"/descargas/{job_id}/memoria_tecnica.docx"})


@app.get("/descargas/{job_id}/{fichero}")
def descargar(job_id: str, fichero: str):
    ruta = TRABAJO / job_id / fichero
    if not ruta.exists():
        raise HTTPException(404, "No encontrado.")
    return FileResponse(ruta)
