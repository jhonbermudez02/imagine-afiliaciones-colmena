FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Driver ODBC de Microsoft para SQL Server (alias SR03EPSDB y cualquier otro mssql+pyodbc).
# Va aparte del apt-get de arriba porque necesita el repositorio de Microsoft, que a su vez
# necesita curl/gnupg ya instalados. ACCEPT_EULA es obligatorio para msodbcsql18: sin el,
# el paquete abre un dialogo y la build se queda colgada.
# El nombre del driver que se usa en la URL es "ODBC Driver 18 for SQL Server".
RUN apt-get update && apt-get install -y --no-install-recommends gnupg2 apt-transport-https ca-certificates \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
