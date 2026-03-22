from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from app.core.observability import get_logger

logger = get_logger("app.ai.nova.llm")

PROMPT_TEMPLATES: dict[str, str] = {
    "operacion": (
        "Eres un asistente operativo de procesos legacy clonados. "
        "Responde de forma accionable, breve y con foco en pasos ejecutables, en lenguaje claro y humano. "
        "Evita sonar robótico: usa frases naturales, precisas y sin tecnicismos innecesarios."
    ),
    "afiliaciones_arl": (
        "Eres un asistente operativo de Afiliaciones ARL (Colombia) en contexto cerrado. "
        "Responde SOLO con datos del contexto disponible (BD, OCR, RAG y XLSX cargados). "
        "Si no hay evidencia suficiente, responde exactamente: 'Sin evidencia en contexto operativo para confirmar ese dato.' "
        "Prioriza: lote TXT, OCR de adjuntos, importación contrato/sede/trabajadores, validaciones y 926. "
        "Para consultas de Excel CPS-F-216, aplica lectura por capas: "
        "Capa 1=Formulario de Afiliación (trámite, empleador, fechas críticas); "
        "Capa 2=Sedes y Trabajadores (conteos por sede, total, validaciones FALSE); "
        "Capa 3=Tablas de verdad (Listado Actividades Economicas, Codigos ORP, subtipos); "
        "Capa 4=Auditoría (inconsistencias y alertas con evidencia). "
        "Regla OCR: si PDF no tiene texto parseable, trátalo como escaneado y aplica OCR por visión; reporta modo y confianza. "
        "Estilo obligatorio: directo, técnico, breve y accionable, pero con redacción humana y clara; sin relleno ni lenguaje comercial. "
        "Si el usuario pide crítica de presentación/redacción/contexto, incluye un bloque final llamado 'Crítica de presentación' "
        "con tres partes: 'Qué está bien', 'Qué confunde' y 'Cómo mejorarlo', en bullets concretos y accionables. "
        "No uses introducciones, disculpas, ni explicación de capacidades. "
        "Siempre que aplique, devuelve salida estructurada con: Resumen ejecutivo, Datos del empleador, Fechas críticas, "
        "Conteo de trabajadores, Validaciones (OK/REVISAR/ALERTA), Inconsistencias, Evidencia, Recomendación final."
    ),
    "funerarios": (
        "Eres un asistente operativo del sistema de Auxilios Funerarios y Notificaciones. "
        "Responde en pasos concretos, usando terminología funcional del sistema: "
        "reclamantes, trámites, estados, cierre masivo, reversión y cargues."
    ),
    "analitica": (
        "Eres un analista funcional. Resume hallazgos y riesgos, "
        "explica supuestos y propone validaciones concretas."
    ),
    "cumplimiento": (
        "Eres un asistente de cumplimiento. Prioriza privacidad, trazabilidad y controles "
        "de seguridad operativa."
    ),
}


class LlmService:
    def __init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", os.getenv("AI_LLM_PROVIDER", "local-deterministic")).strip().lower()
        self.base_url = os.getenv("LLM_BASE_URL", os.getenv("AI_LLM_BASE_URL", "http://localhost:1234/v1")).rstrip("/")
        self.api_key = os.getenv("LLM_API_KEY", os.getenv("AI_LLM_API_KEY", "")).strip()
        self.model = os.getenv("LLM_MODEL", os.getenv("AI_LLM_MODEL", "local-model"))
        self.embed_model = os.getenv("LLM_EMBED_MODEL", os.getenv("AI_LLM_EMBED_MODEL", "")).strip()
        self.temperature = float(os.getenv("LLM_TEMPERATURE", os.getenv("AI_LLM_TEMPERATURE", "0.2")))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", os.getenv("AI_LLM_MAX_TOKENS", "700")))

    def templates(self) -> dict[str, str]:
        return PROMPT_TEMPLATES

    def _local_fallback(self, question: str, context_blocks: list[str], template: str) -> str:
        if context_blocks:
            lines = [f"{idx}. {blk[:220]}{'...' if len(blk) > 220 else ''}" for idx, blk in enumerate(context_blocks[:3], 1)]
            return "Encontré esto en el contexto operativo:\n" + "\n".join(lines)
        q_low = question.lower()
        if template == "afiliaciones_arl":
            if "926" in q_low:
                return (
                    "Para sacar el 926 sin perder trazabilidad, te recomiendo este orden:\n"
                    "1) Cargar y entregar lote TXT.\n"
                    "2) Ejecutar OCR de adjuntos.\n"
                    "3) Importar contrato/sede/trabajadores.\n"
                    "4) Ejecutar validaciones (legacy + prebuild).\n"
                    "5) Generar archivo 926 y comparar contra XLSX/BD."
                )
            return (
                "Para responderte con datos reales necesito el lote o el idtrámite. "
                "Ejemplo: 'valida lote 1001 para generar 926'."
            )
        if "cierre masivo" in q_low:
            return (
                "Para cierre masivo: valida el origen (fiducia/asulado), ejecuta cierre, "
                "verifica respuesta 200 y luego revisa consistencia en estados y trazabilidad."
            )
        if "reversion" in q_low or "reversión" in q_low:
            return "Para reversión masiva: ejecuta la opción de reversión, valida logs y confirma estados finales de reclamantes."
        if "notificacion" in q_low or "notificación" in q_low:
            return "En Notificaciones valida datos obligatorios, estado destino y guarda gestión/post estado con confirmación exitosa."
        if "validacion jefe" in q_low or "validación jefe" in q_low:
            return (
                "Validación Jefe: carga pendientes, filtra por trámite/documento, revisa soportes y valor reconocido, "
                "luego aprueba/rechaza y confirma que el caso salga de la bandeja."
            )
        if "validacion pagos" in q_low or "validación pagos" in q_low:
            return (
                "Validación Pagos: verifica forma de pago, banco, cuenta y valor; después aprueba/rechaza con causal "
                "y recarga la bandeja."
            )
        if "bloqueo" in q_low:
            return (
                "Bloqueo Solicitudes en este módulo es control global (Activo/Inactivo). "
                "Consulta estado actual y, si aplica, activa/desactiva con usuario para dejar trazabilidad."
            )
        if "auditoria" in q_low or "auditoría" in q_low:
            return "Auditoría: consulta por trámite/solicitud, revisa usuario-fecha-estado anterior/nuevo y exporta evidencia."
        if "documento" in q_low or "documentos" in q_low:
            return "Documentos: ingresa trámite/solicitud, clasifica imágenes y guarda; si no hay datos, valida identificadores."
        if "926" in q_low:
            return "Para 926: sincroniza lote y luego genera el archivo; usa JSON como entrada y el TXT 926 como salida."
        return (
            "Puedo ayudarte en Funerarios, Notificaciones y Administración. "
            "Indícame el módulo y acción (por ejemplo: 'validación jefe', 'bloqueo solicitudes', 'auditoría', "
            "'post estado', 'cierre masivo') y te doy pasos exactos."
        )

    def _openai_compatible_chat(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        choices = data.get("choices") if isinstance(data, dict) else None
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = msg.get("content") if isinstance(msg, dict) else None
            if isinstance(content, str) and content.strip():
                return content.strip()
            content_alt = choices[0].get("text") if isinstance(choices[0], dict) else None
            if isinstance(content_alt, str) and content_alt.strip():
                return content_alt.strip()
        raise ValueError("Respuesta vacia desde provider LLM.")

    def generate(
        self,
        *,
        question: str,
        template: str,
        context_blocks: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        selected_template = template if template in PROMPT_TEMPLATES else "operacion"
        system_prompt = PROMPT_TEMPLATES[selected_template]
        context_text = "\n\n".join(context_blocks[:5]).strip()
        user_prompt = question if not context_text else f"Pregunta:\n{question}\n\nContexto:\n{context_text}"

        provider_uses_openai_api = self.provider in {"openai-compatible", "openai", "vllm", "lmstudio"}
        if provider_uses_openai_api:
            try:
                answer = self._openai_compatible_chat(system_prompt, user_prompt)
                return {
                    "ok": True,
                    "provider": "openai-compatible",
                    "template": selected_template,
                    "system_prompt": system_prompt,
                    "answer": answer,
                }
            except Exception as exc:
                logger.warning(f'llm_provider_failed provider="openai-compatible" error="{exc}"')

        answer = self._local_fallback(question, context_blocks, selected_template)
        return {
            "ok": True,
            "provider": "local-deterministic",
            "template": selected_template,
            "system_prompt": system_prompt,
            "answer": answer,
        }
