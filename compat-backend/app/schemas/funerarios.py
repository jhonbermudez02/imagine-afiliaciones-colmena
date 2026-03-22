from typing import List, Optional

from pydantic import BaseModel, Field


class AsignarSolicitudIn(BaseModel):
    usuario: str = Field(min_length=1)


class CambiarEstadoIn(BaseModel):
    usuario: str = Field(min_length=1)
    new_estado: str = Field(min_length=1)
    estado_actual: Optional[str] = None


class PagoReclamanteIn(BaseModel):
    id_reclamante: str = Field(min_length=1)
    forma_pago: Optional[str] = None
    banco: Optional[str] = None
    tipo_cuenta: Optional[str] = None
    numero_cuenta: Optional[str] = None
    valor: Optional[float] = None


class GuardarPagosReclamantesIn(BaseModel):
    usuario: str = Field(min_length=1)
    items: List[PagoReclamanteIn] = Field(min_length=1)
