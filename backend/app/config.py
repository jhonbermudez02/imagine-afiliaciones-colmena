from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NOVA API - Sistema de Afiliaciones"
    app_version: str = "2.0"
    qdrant_url: str = "http://qdrant:6333"
    ollama_url: str = "http://ollama:11434"
    database_url: str = "postgresql://afi_user:afi_pass@postgres:5432/afiliaciones"
    frontend_url: str = "http://localhost:3000"
    model_name: str = "llama3.2:1b"
    embedding_model: str = "nomic-embed-text"
    reranker_model: str = "bbjson/bge-reranker-base"
    reranker_enabled: bool = True
    reranker_top_k: int = 6
    knowledge_dir: str = "/data/knowledge"
    qdrant_collection: str = "nova_knowledge"
    qdrant_state_path: str = "/data/qdrant/active_collection.txt"
    cases_dir: str = "/data/cases"
    document_registry_path: str = "/data/cases/document_registry.json"
    lote_counter_path: str = "/data/cases/lote_counter.json"
    compare_926_history_path: str = "/data/evals/compare_926_history.json"
    legacy_project_root: str = "/Users/escobar/Downloads/sst/migracion_py_react"
    legacy_state_path: str = "/tmp/afiliaciones_engine_state.json"
    legacy_backend_url: str = "http://host.docker.internal:8011/api/v1/afiliaciones"
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
