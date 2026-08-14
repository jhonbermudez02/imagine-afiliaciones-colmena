from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NOVA API - Sistema de Afiliaciones"
    app_version: str = "2.0"
    qdrant_url: str = "http://imagine_qdrant:6333"
    database_url: str = "postgresql://afi_user:afi_pass@imagine_db:5432/afiliaciones"
    frontend_url: str = "http://localhost:8105"
    model_name: str = "local-deterministic"
    embedding_model: str = "local-hash-embedding-v1"
    reranker_model: str = "bbjson/bge-reranker-base"
    reranker_enabled: bool = True
    reranker_top_k: int = 6
    ocr_engine: str = "tesseract"
    ocr_languages: str = "spa+eng"
    # Con contencion de CPU en la maquina (varios procesos tesseract en paralelo +
    # el resto del escritorio compitiendo por nucleos), un timeout de 45s por
    # intento hacia que la ruta rapida sola (2 variantes x hasta 2 idiomas) pudiera
    # tardar hasta 180s antes de siquiera llegar a la ruta exhaustiva/al tope de
    # tiempo por pagina. 15s ya es holgado para un OCR de una sola pagina normal.
    ocr_timeout_seconds: int = 15
    knowledge_dir: str = "/data/knowledge"
    qdrant_collection: str = "nova_knowledge"
    qdrant_state_path: str = "/data/qdrant/active_collection.txt"
    cases_dir: str = "/data/cases"
    document_registry_path: str = "/data/cases/document_registry.json"
    lote_counter_path: str = "/data/cases/lote_counter.json"
    compare_926_history_path: str = "/data/evals/compare_926_history.json"
    notification_recipients_path: str = "/data/evals/pilot_notification_recipients.json"
    notification_log_path: str = "/data/evals/notification_log.jsonl"
    notification_enabled: bool = False
    notification_sender_email: str = "hdescobarmesa@gmail.com"
    notification_sender_name: str = "Imagine S.A.S."
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    legacy_project_root: str = "/compat-backend"
    legacy_state_path: str = "/tmp/afiliaciones_engine_state.json"
    legacy_backend_url: str = "http://imagine_compat_backend:8000/api/v1/afiliaciones"
    legacy_delivery_enabled: bool = True
    legacy_delivery_execute_sql: bool = True
    # --- Ingreso desde el portal Yii 1.1 (SSO por token firmado) ---
    # Secreto compartido con Yii para firmar el token de traspaso (HMAC-SHA256). Vacío
    # deshabilita /sso/yii por completo: sin secreto no hay forma de validar nada, y
    # aceptar tokens sin firma sería peor que no tener la ruta.
    sso_shared_secret: str = ""
    # Ventana de validez del token de traspaso. Solo tiene que sobrevivir al clic en el
    # menú; cuanto más corta, menos margen para reusarlo desde el historial o los logs.
    sso_token_ttl_seconds: int = 90
    # Duración de la sesión propia (la cookie que se entrega al canjear el token).
    sso_session_ttl_seconds: int = 12 * 60 * 60
    sso_cookie_name: str = "afi_session"
    # Secure=false permite probar por http:// en local. En producción va en true (la app
    # queda detrás del reverse proxy con TLS).
    sso_cookie_secure: bool = True
    # Login manual (selector de perfil + operador). Es el único acceso en esta máquina;
    # en producción se apaga para que la entrada sea exclusivamente por el portal.
    manual_login_enabled: bool = True

    search_limit: int = 4
    chunk_size: int = 900
    chunk_overlap: int = 120

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        protected_namespaces=(),
    )


settings = Settings()
