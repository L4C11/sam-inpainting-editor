# Alap image: Python 3.10 slim verzió
FROM python:3.10-slim

# Rendszer szintű függőségek telepítése
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Munkakönyvtár beállítása
WORKDIR /app

# Függőségek másolása és telepítése
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# A teljes projekt másolása a konténerbe
COPY . .

# Helyi checkpoint mappa létrehozása (ide töltődik majd a SAM és SD modell)
RUN mkdir -p /app/checkpoints

# Port publikálása (Django alapértelmezett)
EXPOSE 8000

# Entrypoint script jogosultságainak beállítása
RUN chmod +x /app/entrypoint.sh

# Alapértelmezett parancs futtatása
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]