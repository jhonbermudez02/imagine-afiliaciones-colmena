from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def _txt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


@dataclass
class RutaInclusionAdjuntosSettings:
    destino_root: str = "/imagenes4/img11"
    destino_subpath: str = "Pia/00000002"
    source_legacy_prefix: str = "D:\\PortalSoporteMasivoRutaInclusion\\723\\"
    source_repo_prefix: str = "/imagine_arch/TransaccionesPortal/"
    transfer_mode: str = "move"

    @classmethod
    def from_env(cls) -> "RutaInclusionAdjuntosSettings":
        return cls(
            destino_root=os.getenv("RUTA_INCLUSION_DESTINO_ROOT", "/imagenes4/img11"),
            destino_subpath=os.getenv("RUTA_INCLUSION_DESTINO_SUBPATH", "Pia/00000002"),
            source_legacy_prefix=os.getenv(
                "RUTA_INCLUSION_SOURCE_LEGACY_PREFIX",
                "D:\\PortalSoporteMasivoRutaInclusion\\723\\",
            ),
            source_repo_prefix=os.getenv(
                "RUTA_INCLUSION_SOURCE_REPO_PREFIX",
                "/imagine_arch/TransaccionesPortal/",
            ),
            transfer_mode=os.getenv("RUTA_INCLUSION_TRANSFER_MODE", "move").strip().lower() or "move",
        )


class RutaInclusionAdjuntosService:
    def __init__(self, settings: RutaInclusionAdjuntosSettings | None = None) -> None:
        self.settings = settings or RutaInclusionAdjuntosSettings.from_env()

    @staticmethod
    def _normalize_sep(path: str) -> str:
        return path.replace("\\", "/")

    def resolve_origen(self, ruta_adjunto: str) -> str:
        raw = _txt(ruta_adjunto)
        if not raw:
            return ""
        normalized = self._normalize_sep(raw)
        legacy_prefix = self._normalize_sep(self.settings.source_legacy_prefix).rstrip("/") + "/"
        if normalized.startswith(legacy_prefix):
            tail = normalized[len(legacy_prefix) :]
            repo_prefix = self.settings.source_repo_prefix.rstrip("/") + "/"
            return repo_prefix + tail
        return normalized

    def destino_dir(self, fecha: datetime | None = None) -> Path:
        dt = fecha or datetime.now()
        yyyyMMdd = dt.strftime("%Y%m%d")
        return Path(self.settings.destino_root) / yyyyMMdd / self.settings.destino_subpath

    def destino_file(self, source_path: str, fecha: datetime | None = None) -> Path:
        name = Path(self._normalize_sep(source_path)).name
        return self.destino_dir(fecha=fecha) / name

    def stage_adjunto(
        self,
        source_path: str,
        fecha: datetime | None = None,
        overwrite: bool = True,
        mode: str | None = None,
    ) -> dict[str, Any]:
        src = Path(source_path)
        dst = self.destino_file(source_path, fecha=fecha)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not src.exists():
            return {"ok": False, "source": str(src), "dest": str(dst), "error": "source_not_found"}
        if dst.exists() and not overwrite:
            return {"ok": True, "source": str(src), "dest": str(dst), "status": "exists"}
        transfer_mode = (mode or self.settings.transfer_mode or "move").strip().lower()
        if transfer_mode == "copy":
            shutil.copy2(src, dst)
            return {"ok": True, "source": str(src), "dest": str(dst), "status": "copied", "mode": "copy"}
        shutil.move(str(src), str(dst))
        return {"ok": True, "source": str(src), "dest": str(dst), "status": "moved", "mode": "move"}

    def stage_many(
        self,
        rows: list[dict[str, Any]],
        fecha: datetime | None = None,
        overwrite: bool = True,
        mode: str | None = None,
    ) -> dict[str, Any]:
        out_rows: list[dict[str, Any]] = []
        copied = 0
        missing = 0
        for row in rows:
            id_adj = _txt(row.get("idadjuntostipotramite"))
            id_row = _txt(row.get("idarchivosadjuntostramite"))
            origen_raw = _txt(row.get("rutaadjunto"))
            origen_resuelto = self.resolve_origen(origen_raw)
            staged = self.stage_adjunto(origen_resuelto, fecha=fecha, overwrite=overwrite, mode=mode)
            item = {
                "idarchivosadjuntostramite": id_row,
                "idadjuntostipotramite": id_adj,
                "rutaadjunto_origen": origen_raw,
                "rutaadjunto_resuelta": origen_resuelto,
                **staged,
            }
            if staged.get("ok"):
                copied += 1
            else:
                missing += 1
            out_rows.append(item)
        return {
            "ok": missing == 0,
            "count": len(out_rows),
            "copied_or_moved": copied,
            "missing": missing,
            "mode": (mode or self.settings.transfer_mode or "move").strip().lower(),
            "rows": out_rows,
        }

    def cleanup_retention(self, keep_days: int = 180, dry_run: bool = True) -> dict[str, Any]:
        root = Path(self.settings.destino_root)
        if not root.exists():
            return {"ok": True, "root": str(root), "deleted_dirs": [], "message": "root_not_exists"}
        cutoff = datetime.now() - timedelta(days=keep_days)
        deleted: list[str] = []
        scanned = 0
        for child in root.iterdir():
            if not child.is_dir():
                continue
            scanned += 1
            try:
                dt = datetime.strptime(child.name, "%Y%m%d")
            except ValueError:
                continue
            if dt < cutoff:
                if not dry_run:
                    shutil.rmtree(child, ignore_errors=True)
                deleted.append(str(child))
        return {
            "ok": True,
            "root": str(root),
            "keep_days": keep_days,
            "dry_run": dry_run,
            "scanned_dirs": scanned,
            "deleted_count": len(deleted),
            "deleted_dirs": deleted[:500],
        }
