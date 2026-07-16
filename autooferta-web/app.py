#!/usr/bin/env python3
"""
AutoOferta — API web (FastAPI). Versión de despliegue (archivos planos).

    export ANTHROPIC_API_KEY=sk-ant-...
    uvicorn app:app --host 0.0.0.0 --port 8000

Sin ANTHROPIC_API_KEY arranca en MODO DEMO: /procesar devuelve la salida de ejemplo.

Muro Fase 0: se pide email para usar la herramienta. 1 análisis gratis por email;
al agotarlo se invita a suscribirse. Cada uso queda registrado como lead.
"""
import os
import json
import uuid
import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

app = FastAPI(title="AutoOferta", version="1.1")
BASE = Path(__file__).parent
TRABAJO = BASE / "trabajos"; TRABAJO.mkdir(exist_ok=True)
DEMO_MODE = not os.environ.get("ANTHROPIC_API_KEY")

# --- Muro de prueba gratis -------------------------------------------------
FREE_LIMIT = int(os.environ.get("FREE_LIMIT", "1"))
STRIPE_URL = os.environ.get("STRIPE_URL", "https://buy.stripe.com/9B6aEX9pC5ZH1M30VNc7u01")
USOS_FILE = BASE / "usos.json"
LEADS_FILE = BASE / "leads.jsonl"


def _cargar_usos():
    try:
        return json.loads(USOS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _guardar_usos(usos):
    try:
        USOS_FILE.write_text(json.dumps(usos), encoding="utf-8")
    except Exception:
        pass


def _registrar_lead(email, perfil):
    try:
        fila = {
            "ts": datetime.datetime.utcnow().isoformat(),
            "email": email,
            "empresa": perfil.get("nombre", ""),
            "cif": perfil.get("cif", ""),
            "actividad": perfil.get("actividad", ""),
        }
        with LEADS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except Exception:
        pass


@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "landing.html").read_text(encoding="utf-8")


@app.get("/app", response_class=HTMLResponse)
def app_tool():
    return (BASE / "index.html").read_text(encoding="utf-8")


@app.get("/aviso-legal", response_class=HTMLResponse)
def aviso_legal():
    return (BASE / "aviso-legal.html").read_text(encoding="utf-8")


@app.get("/privacidad", response_class=HTMLResponse)
def privacidad():
    return (BASE / "privacidad.html").read_text(encoding="utf-8")


@app.get("/salud")
def salud():
    return {"ok": True, "modo": "demo" if DEMO_MODE else "real"}


@app.post("/procesar")
async def procesar(pliego: UploadFile = File(...), perfil: UploadFile = File(...)):
    if not pliego.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "El pliego debe ser un PDF.")
    perfil_data = json.loads((await perfil.read()).decode("utf-8"))

    # Muro: email obligatorio
    email = (perfil_data.get("email") or "").strip().lower()
    if "@" not in email or "." not in email:
        raise HTTPException(400, "Introduce un email válido para recibir los resultados.")

    # ¿Ha agotado su prueba gratis?
    usos = _cargar_usos()
    if usos.get(email, 0) >= FREE_LIMIT:
        return JSONResponse({
            "bloqueado": True,
            "mensaje": "Ya has usado tu análisis gratis. Suscríbete para seguir preparando "
                       "ofertas sin límite.",
            "suscripcion": STRIPE_URL,
        })

    job_id = uuid.uuid4().hex[:12]
    carpeta = TRABAJO / job_id; carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "pliego.pdf").write_bytes(await pliego.read())

    if DEMO_MODE:
        analisis = json.loads((BASE / "demo_analisis.json").read_text(encoding="utf-8"))
        checklist = json.loads((BASE / "demo_checklist.json").read_text(encoding="utf-8"))
        (carpeta / "memoria_tecnica.docx").write_bytes((BASE / "demo_memoria.docx").read_bytes())
        res = {"analisis": analisis, "checklist": checklist, "modo": "demo"}
    else:
        from engine import procesar_licitacion
        try:
            r = procesar_licitacion(carpeta / "pliego.pdf", perfil_data, carpeta)
        except Exception as e:
            raise HTTPException(500, f"Error procesando el pliego: {e}")
        res = {"analisis": r["analisis"], "checklist": r["checklist"], "modo": "real"}

    # Consumido con éxito: registra el uso y el lead
    usos[email] = usos.get(email, 0) + 1
    _guardar_usos(usos)
    _registrar_lead(email, perfil_data)

    return JSONResponse({
        "job_id": job_id, "modo": res["modo"], "analisis": res["analisis"],
        "checklist": res["checklist"],
        "memoria_descarga": f"/descargas/{job_id}/memoria_tecnica.docx",
        "usos_restantes": max(0, FREE_LIMIT - usos[email]),
    })


@app.get("/descargas/{job_id}/{fichero}")
def descargar(job_id: str, fichero: str):
    ruta = TRABAJO / job_id / fichero
    if not ruta.exists():
        raise HTTPException(404, "No encontrado.")
    return FileResponse(ruta)
