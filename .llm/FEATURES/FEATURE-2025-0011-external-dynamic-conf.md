# FEATURE-2025-0011: Externalized & Dynamic Configuration (Spring Cloud Style)

  * **Date:** 2025-09-18
  * **Status:** Draft
  * **Priority:** High
  * **Related:** FEATURE-2025-0010 (Dynamic Container: Events, Scopes, Hot-Reload)

-----

## 1\) Summary

Introduce a **proceso de arranque en dos fases (bootstrap)** que permite a la aplicación conectarse a una fuente de configuración externa (como un Servidor de Configuración, HashiCorp Vault, etc.) **antes** de que se cree el contenedor de aplicación principal.

Una vez obtenida la configuración inicial, establece un mecanismo (ej. polling o un watcher) para detectar cambios en la fuente externa. Cuando se detecta un cambio, publica un `ConfigurationChangedEvent` en el bus de eventos del contenedor, activando las capacidades de "hot-reload" definidas en la feature anterior.

-----

## 2\) Goals

  * **Desacoplar la configuración** del artefacto desplegado (ej. imagen de Docker).
  * **Centralizar la gestión** de la configuración para múltiples servicios y entornos.
  * **Habilitar cambios de configuración dinámicos** en toda una flota de servicios sin necesidad de redespliegues.
  * Soportar múltiples *backends* de configuración (Git, Vault, Consul, archivos locales) a través de una interfaz `ConfigSource` extensible.

-----

## 3\) User Impact / Stories

  * *Como desarrollador*, mi aplicación no necesita saber de dónde viene la configuración. En mi entorno local, la lee de un fichero `config.yml`, pero en producción, se conecta automáticamente al Config Server corporativo.
  * *Como SRE/DevOps*, puedo rotar una contraseña de base de datos en Vault, y todos los microservicios afectados la recogerán automáticamente en el siguiente ciclo de actualización, sin reiniciar.
  * *Como arquitecto*, puedo definir una estrategia de configuración unificada para todo el ecosistema de microservicios.

-----

## 4\) Public API / UX Contract

### 1\. El Proceso de "Bootstrap"

Se introduce un fichero de configuración de arranque, por ejemplo `bootstrap.yml`, que se lee antes que cualquier otro. Este fichero contiene **solo** la información necesaria para conectar con la fuente de configuración externa.

**`bootstrap.yml` de ejemplo:**

```yaml
pico:
  application:
    name: order-service
  cloud:
    config:
      uri: http://config-server:8888
      profile: prod
      fail-fast: true
```

### 2\. Nuevas `ConfigSource` de Bootstrap

Se introducen implementaciones especiales de `ConfigSource` que saben cómo interactuar con sistemas externos y detectar cambios.

  * `ConfigServerSource(uri, app_name, profile)`
  * `VaultSource(uri, token, path)`
  * `ConsulSource(...)`

### 3\. Integración Transparente

El código de la aplicación **no cambia**. Un componente sigue pidiendo la configuración de la misma manera. Toda la complejidad de la carga remota y la recarga dinámica es gestionada por el framework.

```python
@component
class DatabaseConnector:
    # Esta configuración ahora puede venir de un Config Server y actualizarse en caliente
    def __init__(self, config: AppConfig):
        self.connection_string = config.get("db.connection_string")
```

-----

## 5\) Cómo Funciona: El Arranque en Dos Fases

1.  **Fase 1: Contexto de Bootstrap**

      * Al iniciar, el framework busca `bootstrap.yml`.
      * Crea un "mini-contenedor" de arranque, muy ligero.
      * Lee la configuración de `bootstrap.yml` para instanciar la `ConfigSource` adecuada (ej. `ConfigServerSource`).
      * Esta `ConfigSource` se conecta al servidor externo y **descarga todas las propiedades** de la aplicación.
      * Inicia un proceso en segundo plano (ej. un *poller* o un *watcher*) que periódicamente comprobará si hay cambios en el servidor.

2.  **Fase 2: Contexto de Aplicación**

      * Las propiedades descargadas en la fase 1 se usan para **configurar y crear el contenedor de aplicación principal**, con todas sus dependencias, interceptores, etc.
      * La aplicación arranca y funciona normalmente con esta configuración.
      * Cuando el *watcher* de la fase 1 detecta un cambio en el Config Server, publica un `ConfigurationChangedEvent` en el bus de eventos del contenedor principal.
      * El mecanismo de "Hot-Reload" (definido en la FEATURE-0010) recibe este evento y se encarga de recargar los componentes afectados.

-----

## 6\) Veredicto

Esta característica es la que **hace tangible y útil** todo el potencial dinámico del contenedor. Es el puente entre el runtime adaptativo de la aplicación y su entorno operativo.

Con esto, el círculo se cierra y el framework ofrece una solución completa que abarca las tres capas de una aplicación moderna:

1.  **Definición del Grafo (DI):** Quién necesita qué (`@role`, `@provides`).
2.  **Definición del Comportamiento (AOP):** Cómo deben actuar los componentes (`@infra`, `Select`).
3.  **Definición de la Configuración (Runtime):** Cómo se adapta la aplicación a su entorno (`EventBus`, `Scopes`, `Externalized Config`).

