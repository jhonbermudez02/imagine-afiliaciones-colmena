"""Tipos de documento de identidad validos en las hojas de trabajadores.

Vive aqui, y no en cada modulo, porque esta lista estaba repetida OCHO veces entre
`api/v1/afiliaciones.py` y `services/nova/orchestrator.py`, y todas omitian PE (Permiso
Especial de Permanencia). El efecto no era un error visible sino una perdida silenciosa:
en `_parse_trabajadores_from_sede_clean` la pertenencia a esta lista es lo que distingue
una fila de TRABAJADOR de una de centro de trabajo, asi que un trabajador con PE se
descartaba y nunca llegaba a importarse. El sintoma aparecia despues, en el prebuild,
como un descuadre entre el 'Total salarios' del Excel y la suma de los trabajadores
importados, con un mensaje que culpaba a la formula del Excel.

Debe mantenerse alineada con ALLOWED_DOCUMENT_TYPES de backend/app/xlsx_rules.py, que es
la que valida el Excel del lado de nova.
"""

TIPOS_DOCUMENTO_TRABAJADOR: frozenset[str] = frozenset(
    {
        "CC",  # Cedula de ciudadania
        "CD",  # Carne diplomatico
        "CE",  # Cedula de extranjeria
        "NI",  # NIT
        "PA",  # Pasaporte
        "PE",  # Permiso Especial de Permanencia
        "PT",  # Permiso por Proteccion Temporal
        "RC",  # Registro civil
        "SC",  # Salvoconducto
        "TI",  # Tarjeta de identidad
    }
)
