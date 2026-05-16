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
    ocr_timeout_seconds: int = 45
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
