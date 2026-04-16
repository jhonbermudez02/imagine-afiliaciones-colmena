import json
import logging
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import settings

logger = logging.getLogger(__name__)


def _load_recipients() -> List[Dict[str, str]]:
    path = Path(settings.notification_recipients_path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    recipients = data.get("recipients") if isinstance(data, dict) else data
    if not isinstance(recipients, list):
        return []
    out: List[Dict[str, str]] = []
    for item in recipients:
        if not isinstance(item, dict):
            continue
        email = str(item.get("email") or "").strip().lower()
        if not email:
            continue
        out.append(
            {
                "name": str(item.get("name") or "").strip(),
                "email": email,
            }
        )
    return out


def _resolve_notification_status(payload: Dict[str, Any]) -> Dict[str, Any]:
    analysis = payload.get("analysis") or {}
    workflow = analysis.get("workflow_run") or {}
    decision = analysis.get("decision") or {}
    precheck_report = workflow.get("executive_report_precheck") or analysis.get("reporte_ejecutivo") or {}
    resumen = precheck_report.get("resumen_ejecutivo") or {}
    empresa = resumen.get("empresa") or ((analysis.get("xlsx_profile") or {}).get("profile") or {}).get("empresa") or payload.get("label") or "Contrato"
    nit = resumen.get("nit") or ((analysis.get("xlsx_profile") or {}).get("profile") or {}).get("nit") or "n/d"
    fecha = resumen.get("fecha_proceso_human") or precheck_report.get("fecha_proceso_human") or payload.get("updated_at") or datetime.now(timezone.utc).isoformat()
    workflow_status = str(workflow.get("status") or "").strip().lower()
    recommended_status = str(decision.get("recommended_status") or "").strip().lower()
    approved = workflow_status != "stopped_prevalidacion" and recommended_status == "aprobable"
    estado = "APROBADO" if approved else "RECHAZADO EN PREVALIDACIÓN"
    blockers = list(decision.get("blockers") or [])
    if not blockers:
        errores = list(resumen.get("errores") or [])
        blockers = [str(item).strip() for item in errores if str(item).strip()]
    next_step = decision.get("next_step") or "Revisar el resumen ejecutivo y corregir antes de radicar."
    return {
        "approved": approved,
        "estado": estado,
        "empresa": empresa,
        "nit": nit,
        "fecha": fecha,
        "blockers": blockers[:3],
        "next_step": next_step,
    }


def _build_message(payload: Dict[str, Any], recipients: List[Dict[str, str]]) -> EmailMessage:
    status = _resolve_notification_status(payload)
    subject = f"[Imagine] {status['estado']} - {status['empresa']}"
    body_lines = [
        f"Empresa: {status['empresa']}",
        f"NIT: {status['nit']}",
        f"Fecha: {status['fecha']}",
        f"Estado: {status['estado']}",
        "",
    ]
    if status["blockers"]:
        body_lines.append("Motivos principales:")
        body_lines.extend([f"- {item}" for item in status["blockers"]])
        body_lines.append("")
    body_lines.extend(
        [
            f"Siguiente paso: {status['next_step']}",
            "",
            "Notificación automática del Portal Radicación de Afiliaciones ARL.",
        ]
    )
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.notification_sender_name} <{settings.notification_sender_email}>"
    message["To"] = ", ".join(item["email"] for item in recipients)
    message.set_content("\n".join(body_lines))
    return message


def _append_notification_log(entry: Dict[str, Any]) -> None:
    path = Path(settings.notification_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def send_case_notification(payload: Dict[str, Any]) -> Dict[str, Any]:
    recipients = _load_recipients()
    status = _resolve_notification_status(payload)
    log_entry: Dict[str, Any] = {
        "case_id": payload.get("id"),
        "empresa": status["empresa"],
        "nit": status["nit"],
        "estado": status["estado"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "recipients": [item["email"] for item in recipients],
    }
    if not settings.notification_enabled:
        log_entry["delivery"] = "disabled"
        _append_notification_log(log_entry)
        return {"ok": False, "delivery": "disabled", "recipients": len(recipients), "status": status}
    if not recipients:
        log_entry["delivery"] = "no_recipients"
        _append_notification_log(log_entry)
        return {"ok": False, "delivery": "no_recipients", "recipients": 0, "status": status}
    smtp_username = settings.smtp_username or settings.notification_sender_email
    smtp_password = settings.smtp_password
    if not smtp_password:
        log_entry["delivery"] = "pending_smtp_password"
        _append_notification_log(log_entry)
        return {"ok": False, "delivery": "pending_smtp_password", "recipients": len(recipients), "status": status}

    message = _build_message(payload, recipients)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
        log_entry["delivery"] = "sent"
        _append_notification_log(log_entry)
        return {"ok": True, "delivery": "sent", "recipients": len(recipients), "status": status}
    except Exception as exc:
        logger.error("No pude enviar la notificación del caso %s: %s", payload.get("id"), exc)
        log_entry["delivery"] = "error"
        log_entry["error"] = str(exc)
        _append_notification_log(log_entry)
        return {"ok": False, "delivery": "error", "error": str(exc), "recipients": len(recipients), "status": status}


def send_tester_activity_summary(summary: Dict[str, Any], recipients: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    recipients = recipients or _load_recipients()
    log_entry: Dict[str, Any] = {
        "type": "tester_activity_summary",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "date": summary.get("date"),
        "recipients": [item["email"] for item in recipients],
    }
    if not settings.notification_enabled:
        log_entry["delivery"] = "disabled"
        _append_notification_log(log_entry)
        return {"ok": False, "delivery": "disabled", "recipients": len(recipients)}
    if not recipients:
        log_entry["delivery"] = "no_recipients"
        _append_notification_log(log_entry)
        return {"ok": False, "delivery": "no_recipients", "recipients": 0}
    smtp_username = settings.smtp_username or settings.notification_sender_email
    smtp_password = settings.smtp_password
    if not smtp_password:
        log_entry["delivery"] = "pending_smtp_password"
        _append_notification_log(log_entry)
        return {"ok": False, "delivery": "pending_smtp_password", "recipients": len(recipients)}

    top = summary.get("top_testers") or []
    inactive = summary.get("inactive_testers") or []
    lines = [
        f"Resumen diario de actividad de pruebas · {summary.get('date') or 'n/d'}",
        "",
        f"Total de eventos: {summary.get('total_events', 0)}",
        f"Testers activos: {summary.get('active_testers', 0)}",
        f"Testers sin actividad: {summary.get('inactive_count', 0)}",
        "",
        "Ranking de actividad:",
    ]
    if top:
        for idx, item in enumerate(top, start=1):
            lines.append(
                f"{idx}. {item.get('name') or item.get('email')} · eventos={item.get('total_actions', 0)} · "
                f"contratos={item.get('cases_created', 0)} · ejecuciones={item.get('workflow_started', 0)} · "
                f"busquedas={item.get('searches', 0)} · comentarios={item.get('feedback_notes', 0)}"
            )
    else:
        lines.append("Sin actividad registrada.")
    lines.extend(["", "Sin actividad:"])
    if inactive:
        lines.extend([f"- {item.get('name') or item.get('email')}" for item in inactive])
    else:
        lines.append("- Ninguno")

    message = EmailMessage()
    message["Subject"] = f"[Imagine] Resumen diario de pruebas - {summary.get('date') or ''}".strip()
    message["From"] = f"{settings.notification_sender_name} <{settings.notification_sender_email}>"
    message["To"] = ", ".join(item["email"] for item in recipients)
    message.set_content("\n".join(lines))
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
        log_entry["delivery"] = "sent"
        _append_notification_log(log_entry)
        return {"ok": True, "delivery": "sent", "recipients": len(recipients)}
    except Exception as exc:
        logger.error("No pude enviar el resumen diario de actividad: %s", exc)
        log_entry["delivery"] = "error"
        log_entry["error"] = str(exc)
        _append_notification_log(log_entry)
        return {"ok": False, "delivery": "error", "error": str(exc), "recipients": len(recipients)}
