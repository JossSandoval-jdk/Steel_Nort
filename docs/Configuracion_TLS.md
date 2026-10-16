# Configuración HTTPS/TLS (S1-13)

**Estado:** *Documentado, no aplicado en la demo.* La aplicación funciona en HTTP en desarrollo (127.0.0.1) y en producción conviene poner un proxy reverso con TLS.

## 1. Arquitectura recomendada para producción

El sistema tiene tres componentes expuestos:
- **Backend FastAPI (v2):** puerto 8200 (HTTP). En producción, **no** exponer directamente el puerto 8200 al exterior; hacerlo detrás de un **reverse proxy** (Nginx/Apache) con HTTPS.
- **Frontend servidor Node (Express):** sirve `dist/` y hace proxy a `/api/v2` hacia el backend. También puede estar detrás del mismo proxy (recomendado) o servir directamente sobre HTTPS.
- **Vite dev (5173):** solo desarrollo.

Recomendación: **Nginx** como reverse proxy con certificado TLS (Let's Encrypt) y redirección de HTTP→HTTPS.

## 2. Opción A: Nginx (recomendada)

Ejemplo de configuración (fragmento):

```nginx
server {
    listen 80;
    server_name steelnort.local;

    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name steelnort.local;

    ssl_certificate     /etc/ssl/certs/steelnort.crt;
    ssl_certificate_key /etc/ssl/private/steelnort.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    # Frontend (Node o archivos estáticos)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API v2 detrás del proxy (conserva cabeceras)
    location /api/v2/ {
        proxy_pass http://127.0.0.1:8200/api/v2/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Con esto:
- El tráfico sale por **HTTPS** (443).
- FastAPI recibe el esquema correcto (`X-Forwarded-Proto=https`).
- Se mantiene la separación: proxy maneja TLS, backend sigue en HTTP interno (más seguro en red interna).

## 3. Opción B: Uvicorn con certificados (directo)

Para pruebas locales (no recomendado para producción), se puede arrancar Uvicorn con `--ssl-keyfile` y `--ssl-certfile`:

```powershell
uvicorn app.v2.main:app --host 0.0.0.0 --port 8200 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Los certificados deben generarse localmente (p.ej., `mkcert`) y **nunca** subirse al repositorio (ya están excluidos en `.gitignore`: `*.key`, `*.pem`, `*.crt`, `*.pfx`).

## 4. Configuración del frontend para HTTPS

- En desarrollo: se usa Vite + proxy (HTTP). No requiere cambios.
- En producción: el servidor Node Express puede servir sobre HTTPS si recibe tráfico TLS desde el proxy (ya lo hace con `X-Forwarded-*`). Si se quiere servir HTTPS directamente, hay que añadir `https.createServer` con los certificados.
- Variables relevantes (`frontend/server/.env.example`): no hay variables TLS obligatorias si va detrás de Nginx; el proxy gestiona el cifrado.

## 5. Notas de seguridad (coherentes con el proyecto)

- **Cabeceras ya presentes** (S1-10): `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`. Un proxy con TLS suele añadir `Strict-Transport-Security` (HSTS): recomendable añadirlo en Nginx (`add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;`).
- **CORS restringido** (S1-9): los orígenes permitidos están en `V2_CORS_ORIGINS`. Si el front pasa a HTTPS, añadir `https://localhost:5173`, `https://tu-dominio` según corresponda.
- **No se suben secretos ni certificados** al repo (cumple S1-11). El `.gitignore` ya excluye `*.key`, `*.pem`, `*.crt`, `*.pfx`.
- **Solo lectura para el recolector** (S1-12): usar `steelnort_monitor` (SQL Auth) con `db_datareader`, tal como documenta `docs/scripts_sql/login_lectura_steelnort_monitor.sql`.

## 6. Verificación (después de activar)

1. Acceder a `https://<dominio>/api/v2/salud` → debe responder 200 y la conexión debe ser cifrada (candado en navegador).
2. Revisar cabeceras: deben incluir `Strict-Transport-Security` (si se añade en proxy) y las ya existentes.
3. Login/auth siguen funcionando igual (JWT viaja por HTTPS).
4. El recolector y el backend interno siguen comunicándose por red interna (HTTP) o por HTTPS según la configuración; para la demo basta con HTTP interno.

**Conclusión:** para cumplir **RNF1 (comunicación segura)** en un entorno real basta con poner **Nginx + TLS** por delante. En la demo actual no se aplica (se deja documentado con esta configuración lista para usar), lo cual es honesto y suficiente para la evidencia.