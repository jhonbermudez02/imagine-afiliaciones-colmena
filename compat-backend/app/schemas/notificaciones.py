from typing import List, Optional

from pydantic import BaseModel, Field


class ConsultarAfiliadoIn(BaseModel):
    tipo_id: str = Field(min_length=1)
    id: str = Field(min_length=1)
    tipo_solicitud: str = Field(min_length=1)


class CambiarEstadoNotIn(BaseModel):
    tramite: str = Field(min_length=1)
    usuario: str = Field(min_length=1)
    new_estado: str = Field(min_length=1)


class BeneficiarioIn(BaseModel):
    tipoid_beneficiario: str = Field(min_length=1)
    identificacion: str = Field(min_length=1)
    nombre_beneficiario: str = Field(min_length=1)
    direccion: Optional[str] = None
    telefono_beneficiario: Optional[str] = None


class NotificarSolicitudIn(BaseModel):
    tramite: str = Field(min_length=1)
    tipo_solicitud: str = Field(min_length=1)
    fecha_solicitud: str = Field(min_length=1)
    estado_solicitud: str = Field(min_length=1)
    tipoid_afiliado: str = Field(min_length=1)
    id_afiliado: str = Field(min_length=1)
    nombre_afiliado: str = Field(min_length=1)
    idoficina: Optional[str] = None
    oficina: Optional[str] = None
    idregional: Optional[str] = None
    regional: Optional[str] = None
    usuario: str = Field(min_length=1)
    beneficiarios: List[BeneficiarioIn] = Field(min_length=1)


class ValidarTramiteIn(BaseModel):
    tramite: str = Field(min_length=1)
    id_prestacion: int = Field(gt=0)
    usuario: str = Field(min_length=1)


class RechazarTramiteIn(BaseModel):
    tramite: str = Field(min_length=1)
    id_prestacion: int = Field(gt=0)
    razon_rechazo: str = Field(min_length=1)
    usuario: str = Field(min_length=1)


class FinalizarTramiteIn(BaseModel):
    tramite: str = Field(min_length=1)
    usuario: str = Field(min_length=1)


class GuardarPostEstadoIn(BaseModel):
    id_estado_post: int = Field(gt=0)
    marca: bool
    usuario: str = Field(min_length=1)


class GuardarPostGestionIn(BaseModel):
    tipo_gestion: int = Field(gt=0)
    usuario: str = Field(min_length=1)
    observacion_g: Optional[str] = None


class ValidarImagenIn(BaseModel):
    tramite: str = Field(min_length=1)
    ax: str = Field(min_length=1)
    pn: int = Field(gt=0)
    valor: int


class TraerImagenesValidarIn(BaseModel):
    tramite: str = Field(min_length=1)
    id_prestacion: int = Field(gt=0)
    tipo_solicitud: str = Field(min_length=1)


class ConsultarImagenesIn(BaseModel):
    tramite: str = Field(min_length=1)
    id_prestacion: int = Field(gt=0)
    tipo_solicitud: str = Field(min_length=1)


class EliminarImagenExistenteIn(BaseModel):
    pn: int = Field(gt=0)


class ActualizarCategoriaIn(BaseModel):
    pn: int = Field(gt=0)
    val: int = Field(gt=0)


class ActualizarCategoriaNewIn(BaseModel):
    pn: str = Field(min_length=1)
    val: str = Field(min_length=1)
    indexado: str = Field(min_length=1)


class TraerGestionPostPrestacionIn(BaseModel):
    tipo_gestion: int = Field(gt=0)
    usuario: str = Field(min_length=1)


class BloqueoCreateIn(BaseModel):
    estado: int = Field(ge=0, le=1)
    usuario: str = Field(min_length=1)
