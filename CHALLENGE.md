# Xertica Challenge

## Problem Description
El equipo de compliance tarda en promedio 4.2 horas en resolver una alerta de fraude. 
El 68% de las alertas son falsos positivos, pero el equipo no puede reducir la revisión porque las regulaciones exigen trazabilidad total del proceso de decisión.
El CTO quiere reducir ese tiempo a menos de 30 minutos usando AI, manteniendo el
compliance regulatorio completo y sin eliminar el human in the loop para decisiones de
alto riesgo.

## Current Infrastructure
Stack existente: PostgreSQL (transacciones),
Elasticsearch (búsqueda de alertas),
Google Cloud Storage (documentos PDF de clientes), BigQuery con 3 años de histórico
transaccional, y un modelo XGBoost propio que genera las alertas iniciales.
Restricción crítica: Todo el procesamiento de datos personales debe permanecer en
Google Cloud (región us-central1 ). No se pueden enviar datos de clientes a APIs
externas sin anonimización previa.

## Regulatory Restrictions
Restricción regulatoria: Cada decisión tomada por el sistema de AI debe generar un audit
trail completo y legible por auditores humanos. "La IA lo decidió" no es una justificación
válida ante la UIAF. El sistema debe poder explicar por qué tomó cada decisión.

## Arquitectura del Sistema Agéntico
Diseña e implementa la arquitectura base del sistema multi-agente para el pipeline de
compliance. El sistema debe orquestar al menos 3 agentes especializados que trabajen
en paralelo y en secuencia.
Agentes requeridos:
1. Agente Investigador: Dado un ID de alerta, busca en BigQuery el historial de
   transacciones del cliente (últimos 90 días), extrae los documentos PDF relevantes de
   GCS, y construye un contexto estructurado del caso.
2. Agente de Análisis de Riesgo: Recibe el contexto del Agente Investigador y debe: 
   - Clasificar el nivel de riesgo en escala 1–10 con justificación explícita
   - Identificar patrones de comportamiento anómalo comparando contra el histórico
   - Producir un resumen en lenguaje natural para el analista humano.
3. Agente de Decisión: Con base en el análisis, decide si escala al humano, descarta la
   alerta, o solicita información adicional. Toda decisión debe incluir: nivel de confianza, regulaciones aplicables y el razonamiento paso a paso.

### Stack recomendado:
LangGraph o Google ADK para la orquestación del grafo de agentes
Vertex AI (Gemini) como LLM base — justifica si usas otra opción
Langfuse para observabilidad (trazas, latencias, costo estimado por alerta)
FastAPI como capa de API para exponer el pipeline

## Project Structure
compliance_agent/
├── agents/
│ ├── investigador.py # Agente 1
│ ├── risk_analyzer.py # Agente 2
│ └── decision_agent.py # Agente 3
├── graph/
│ └── pipeline.py # Orquestación LangGraph / ADK
├── tools/
│ ├── bigquery_tools.py # Consultas BigQuery como tools
│ └── gcs_tools.py # Extracción de PDFs de GCS
├── api/
│ └── main.py # FastAPI endpoints
├── observability/
│ └── langfuse_config.py # Configuración de trazabilidad
└── docker-compose.yml # Levantamiento local

**Note**: No es necesario conectarse a BigQuery o GCS reales. Puedes usar mocks o data
sintética. Lo que se evalúa es el diseño de la arquitectura, la calidad del código y la
solidez del razonamiento de los agentes.

## RAG + GraphRAG para Contexto Regulatorio
El Agente de Decisión necesita acceder al corpus regulatorio: circulares de la UIAF
(Colombia), disposiciones de la CNBV (México) y normativas de la SBS (Perú). Son
documentos largos con referencias cruzadas entre artículos.
Implementa un sistema de recuperación híbrido:
1. RAG clásico: Pipeline de indexación de documentos PDF → embeddings → vector
   store (pgvector o Weaviate). Incluir una estrategia de chunking justificada (¿por qué ese tamaño? ¿con qué overlap?).
2. Graph layer:
   Modelar las relaciones entre artículos regulatorios (ej: "el Artículo 15 hace
   referencia al Artículo 8", "esta circular deroga la anterior"). Usar Neo4j, FalkorDB o
   Spanner Graph. El grafo debe mejorar la precisión cuando una consulta requiere
   razonamiento sobre múltiples artículos relacionados.
3. Hybrid retrieval: Implementa una estrategia que combine búsqueda densa
   (embeddings) + sparse (BM25) + grafo para responder preguntas como: "
   ¿Qué
   artículos aplican para una transferencia internacional de $50,000 USD desde una
   persona jurídica?"

## Pregunta de diseño (responder en el README):
¿Cómo evaluarías la calidad de tu sistema RAG? Define al menos 2 métricas concretas
(con fórmula o descripción precisa) que usarías para medir si el sistema recupera los
artículos correctos. ¿Usarías RAGAS, DeepEval u otro framework? Justifica tu decisión.

## Traducción al Negocio — El Documento del CTO
El CTO de FinServ LATAM tiene una reunión con su board en 48 horas. Necesita presentar
la solución de AI para compliance y conseguir aprobación de presupuesto. Tú eres el
Tech Lead que diseñó la arquitectura.
Entregable: Un documento de máximo 2 páginas (PDF o Markdown bien formateado) que
responda:
1. El problema en números:
   ¿Cuánto le cuesta actualmente el proceso manual a FinServ?
   Construye un modelo de costo con los datos del escenario. Haz tus supuestos
   explícitos.
2. La solución propuesta:
   Explica la arquitectura técnica en términos que un CFO pueda
   entender. Sin siglas sueltas ni tecnicismos sin explicar.
3. ROI proyectado: Si el sistema reduce el tiempo de resolución de 4.2h a 30min,
   ¿cuál
   es el ahorro estimado en 12 meses? ¿Cuál es el costo de implementación? Presenta un
   break-even claro.
4. El riesgo principal: Identifica el principal riesgo técnico o regulatorio de implementar
   este sistema y propón una mitigación concreta.

**Note**: Evaluamos el razonamiento, no los números exactos. Un modelo de costo con
supuestos explícitos y bien estructurado vale mucho más que cifras precisas sin contexto. El board necesita confianza, no exactitud contable.

## Infraestructura como Código + CI/CD 
Define la infraestructura necesaria para llevar este sistema a producción en GCP. No
necesitas ejecutarla — necesitas que sea funcional, versionable y reproducible.
1. Terraform (mínimo viable): Define al menos los recursos críticos: Cloud Run para la
   API, un bucket de GCS para documentos, una instancia de Cloud SQL o AlloyDB para el
   vector store, y los permisos IA
   M mínimos necesarios. Incluye un variables.tf bien
   comentado.
2. Pipeline CI/CD: Define un workflow de GitHub Actions que ejecute tests, construya la
   imagen Docker, la publique en Artifact Registry y haga deploy a Cloud Run. El pipeline
   debe fallar si la cobertura de tests cae por debajo del 60%.
3. Observabilidad en producción: Describe en texto o diagrama qué métricas
   monitorearías. Incluye al menos: latencia p95 del pipeline completo, costo por alerta
   procesada, tasa de escalación al humano, y cómo detectarías drift del LLM.

# Pregunta Abierta — Sistema en Producción
Responde esta sección en el README. No hay una respuesta correcta única — lo que
evaluamos es la profundidad y el rigor de tu razonamiento.
- El escenario: Después de 3 semanas en producción, el sistema tiene una tasa de escalación al humano
    del 12% (el target era 15% — el equipo está contento). Sin embargo, un auditor externo
    detecta que el sistema está sistemáticamente sub-escalando alertas de personas
    políticamente expuestas (PEPs): las está resolviendo de forma automática cuando la
    regulación exige escalarlas siempre.

Responde:
1. ¿Cómo habrías detectado este problema antes de que lo encontrara el auditor? ¿Qué
   monitoreo habrías implementado desde el día 1?
2. ¿Cuál es la causa raíz más probable del error? ¿Falla del prompt, del RAG, del agente
      de decisión, o del diseño del sistema?
3. ¿Cómo lo corriges? Da una solución técnica concreta.
4. ¿Qué cambiarías en tu arquitectura inicial con este aprendizaje?

# Deliverables
- Código funcional — Arquitectura agéntica
  Código Python ejecutable localmente con docker-compose up . Mocks de
  BigQuery/GCS son aceptados. Los 3 agentes deben estar implementados.
- Sistema RAG + GraphRAG
  Implementación funcional con al menos 5 documentos de ejemplo. Incluir
  notebook de evaluación con las métricas definidas en el README.
- Documento ejecutivo — El Documento del CTO
  PDF o Markdown. Máximo 2 páginas. Legible para un CFO sin background
  técnico.
- Infraestructura como Código + CI/CD
  Archivos Terraform (aunque no ejecutados) y workflow de GitHub Actions.
  Comentados y bien estructurados.
- README principal con respuesta a la pregunta abierta
  Sección dedicada en el README. Se valora profundidad sobre extensión.
  Mínimo 400 palabras para el Challenge 05.
- "Mi flujo con AI" — sección en el README
  Describe cómo usaste herramientas como Claude Code, Gemini CLI, Cursor o
  similares durante el desarrollo. Usarlas no solo está permitido — es parte del perfil
  que buscamos.

# **NOTE**
Tienes dudas sobre el escenario del cliente? Anótalas y documenta tus supuestos. No
necesitas preguntar para avanzar — en proyectos reales tampoco siempre hay alguien
disponible para resolver cada duda.
