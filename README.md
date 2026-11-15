# pedidos-nl2sql

Preguntas en lenguaje natural sobre datos de pedidos. Un LLM traduce la pregunta a SQL, la SQL se
**valida** antes de ejecutarse (solo lectura y solo tablas permitidas) y el resultado se devuelve
por una API con FastAPI.

> Prueba técnica en curso: este README se completa a medida que avanza el proyecto.

## Cómo ejecutarlo

_Pendiente._

## Arquitectura

_Pendiente._

## Decisiones

- **Entorno: Python 3.12 + uv.** `uv sync` instala exactamente las versiones de `uv.lock`, así que
  quien revise obtiene el mismo entorno con un solo comando.
- **Base de datos: SQLite.** Viene con Python, así que no añade dependencias ni infraestructura
  para quien revise. Además permite una garantía fuerte en la API: la conexión es de solo lectura
  (`mode=ro`) y un *authorizer* hace que el propio motor rechace cualquier acción que no sea leer
  las tablas permitidas, aunque el validador fallara. Con unos miles de filas el rendimiento no
  importa. En contra: no tiene tipos `DATE` ni `DECIMAL`. Las fechas se guardan como texto ISO con
  un `CHECK` y los importes como `REAL`, redondeados en las vistas. En producción usaría
  PostgreSQL con un rol de solo lectura.
- **LLM: Gemini, capa gratuita de Google AI Studio.** Es gratuita y sin tarjeta, y basta para una
  prueba. A cambio, Google puede usar el contenido de las peticiones para mejorar sus productos. Aquí
  es aceptable porque los datos son sintéticos y al modelo solo se le envía el esquema, nunca filas
  de clientes. En producción usaría la capa de pago o Vertex AI. El proveedor está detrás de una
  interfaz, así que cambiar a otro LLM es escribir otra implementación, sin tocar el resto.
- **Gemini se llama por HTTP con httpx, sin el SDK oficial.** `google-genai` arrastra `google-auth`
  y `cryptography`, unos 5 MB de binarios nativos, para lo que es una sola petición POST. Con httpx
  controlo directamente los timeouts y los errores, y en los tests se simula sin red.
- **Dependencias mínimas.** Seis dependencias directas, ninguna con binarios pesados. Al empezar,
  mi conexión a PyPI iba a ~10 KB/s, y DuckDB + pandas + numpy (~50 MB) no eran viables.

## Limitaciones conocidas

_Pendiente._

## Qué haría con más tiempo

_Pendiente._

## Cómo he usado la IA

Herramientas: **Claude Code** (Claude Opus 5.5) como asistente de programación, y **Gemini** como
el LLM que usa la API en tiempo de ejecución.

| Fase | Qué le pedí | Qué acepté | Qué corregí o decidí yo |
|---|---|---|---|
| Plan | Un plan para hacer la prueba en 3 horas como máximo | Arquitectura (validación de la SQL en tres capas), fases y orden de commits | Cambiar el LLM de Claude a Gemini (capa gratuita), porque no tengo clave de Anthropic |
| Entorno | Instalar las dependencias del plan (DuckDB + pandas) | Su diagnóstico: PyPI iba a ~10 KB/s y esas librerías pesan ~50 MB | Elegí SQLite + Python estándar en lugar de DuckDB + pandas: no hay que descargar nada y el motor puede imponer la lista de tablas permitidas |
| Entorno | Instalar el SDK de Gemini (`google-genai`) | La descarga de `cryptography` (4,5 MB, dependencia del SDK) falló 9 veces; propuso llamar a la API REST con httpx | Aceptado: una petición POST no justifica 5 MB de dependencias nativas |

## Tiempo invertido

_Pendiente._
