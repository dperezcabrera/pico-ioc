# ADR-006: Eager Startup Validation ✅

**Status:** Accepted

## Context

Dependency Injection containers often defer resolving dependencies until a component is actually requested at runtime. This can lead to unexpected `ProviderNotFoundError` or `CircularDependencyError` exceptions durante la operación (por ejemplo, en medio de una petición de usuario), lo que es disruptivo y difícil de depurar, especialmente en entornos de producción. Priorizamos la estabilidad de la aplicación, la predictibilidad y detectar errores de configuración lo antes posible. 💣➡️😌

---

## Decisión

Decidimos implementar una validación anticipada (eager validation) durante el proceso `init()`:

1. Descubrimiento y selección: Tras descubrir todos los componentes (`@component`, `@factory`, `@provides`, `@configured`) y seleccionar los proveedores efectivos según perfiles, condiciones y reglas (`Registrar.select_and_bind`), el método `Registrar._validate_bindings` realiza un análisis estático del posible grafo de dependencias resultante.
2. Inspección de dependencias: Para cada componente registrado (excluyendo los marcados explícitamente con `lazy=True`), el validador inspecciona las anotaciones de tipos del constructor (`__init__`) o del método de fábrica/proveedor (`@provides`) del que proviene.
3. Verificación de proveedores: Para cada dependencia requerida (identificada por su anotación de tipo o por una clave de cadena), se verifica si existe un proveedor correspondiente en el `ComponentFactory` finalizado. También se manejan inyecciones de listas (por ejemplo, `Annotated[List[Type], Qualifier]`) comprobando que exista al menos un proveedor que coincida con los criterios (a menos que la lista sea opcional o tenga un valor por defecto).
4. Fallo temprano: Si alguna dependencia requerida no puede satisfacerse para un componente no perezoso, `init()` lanza inmediatamente un `InvalidBindingError`, listando todas las dependencias insatisfechas detectadas durante el escaneo de validación. Las dependencias circulares a menudo se detectan en esta fase de análisis o en el primer intento real de resolución, lanzando un `CircularDependencyError`. 💥

---

## Alcance y limitaciones

- Qué se valida:
  - Firmas de `__init__` y de métodos/funciones anotadas con `@provides`.
  - Anotaciones de tipos conforme a PEP 484/PEP 593 (incluyendo `Annotated[...]`, `Optional[T]`/`T | None`, parámetros con valor por defecto).
  - Inyecciones múltiples/colección (por ejemplo, `List[T]` con calificador) exigiendo al menos un proveedor cuando el parámetro es requerido.
- Qué no se valida:
  - Ejecución de constructores ni lógica en tiempo de ejecución dentro de los métodos de fábrica/proveedores.
  - Proveedores registrados dinámicamente después de `init()` o componentes cargados por plugins tras el arranque.
  - Dependencias sólo alcanzables a través de componentes marcados con `lazy=True` (sus árboles no se recorren).
  - Condiciones dependientes de estado en tiempo de ejecución que no hayan sido resueltas antes de `Registrar.select_and_bind`.

---

## Detalles de implementación

- Orden de ejecución:
  - Descubrimiento de componentes y reglas.
  - Resolución de perfiles/condiciones y selección de proveedores con `Registrar.select_and_bind`.
  - Construcción del mapa final de proveedores en `ComponentFactory`.
  - `Registrar._validate_bindings` recorre los componentes no perezosos y valida sus dependencias.
- Resolución de dependencias requeridas:
  - Parámetros sin valor por defecto y no anotados como opcionales se consideran requeridos.
  - Dependencias identificadas por tipo, clave de cadena o calificador (por ejemplo, mediante `Annotated[..., Qualifier]`) deben tener al menos un proveedor seleccionado.
  - Para colecciones (`List[T]`, `Iterable[T]`), se exige al menos un proveedor coincidente salvo que el parámetro sea opcional o tenga valor por defecto.
- Tratamiento de opcionales y valores por defecto:
  - Parámetros `Optional[T]` o `T | None` y/o con valor por defecto no provocan error si no hay proveedor.
  - Para colecciones, un valor por defecto (p. ej., lista vacía) desactiva el requisito de existencia de proveedores.
- Componentes perezosos:
  - Componentes con `lazy=True` no se validan en profundidad; su resolución y posibles errores asociados se difieren hasta el primer acceso.
- Detección de ciclos:
  - Se generan aristas del grafo entre componentes no perezosos según sus dependencias requeridas. Si se detecta un ciclo evidente, se lanza `CircularDependencyError`. Algunos ciclos pueden manifestarse en la primera resolución real si no son deducibles estáticamente.
- Reporte de errores:
  - `InvalidBindingError` agrega y deduplica todas las dependencias faltantes detectadas, indicando componente de origen, parámetro y criterio (tipo/clave/calificador) no satisfecho para facilitar la depuración.

---

## Alternativas consideradas

- Resolución bajo demanda (lazy-only):
  - Pros: arranque más rápido.
  - Contras: fallos en producción en momentos no deterministas, peor experiencia de depuración, menor confianza en despliegues.
- Validación parcial:
  - Pros: compromiso entre coste de arranque y seguridad.
  - Contras: deja ventanas de error no detectadas para componentes críticos.
- Validación externa en tiempo de compilación/linter:
  - Pros: feedback temprano en CI.
  - Contras: no siempre tiene visibilidad de perfiles/condiciones activas ni del conjunto real de proveedores en tiempo de ejecución.

---

## Consecuencias

Positivas 👍
- Reduce significativamente errores de cableado en tiempo de ejecución: La mayoría de problemas comunes como componentes faltantes, typos en claves o dependencias insatisfechas se detectan en el arranque, antes de atender peticiones.
- Mejora la confianza del desarrollador: Un `init()` exitoso garantiza en gran medida que el grafo de dependencias núcleo es resoluble (salvo errores de tiempo de ejecución dentro de los constructores/métodos). ✅
- Reporte de errores claro: `InvalidBindingError` lista todos los problemas detectados durante la validación, acelerando la depuración. 🕵️‍♀️

Negativas 👎
- Ligero aumento del tiempo de arranque: La validación añade una sobrecarga a `init()` al inspeccionar firmas y consultar el mapa de proveedores. Suele ser despreciable, pero puede notarse en aplicaciones extremadamente grandes. ⏱️
- Componentes `lazy=True` omiten validación completa: Dependencias requeridas sólo por componentes marcados como perezosos pueden no validarse hasta el primer acceso (trade-off deliberado de `lazy=True`). 🤔

---

## Guía de adopción y migración

- Anota los parámetros de constructores y de métodos `@provides` con tipos precisos. Los parámetros sin anotación o ambiguos pueden no resolverse adecuadamente.
- Asegura que, para cada tipo/clave/calificador requerido por componentes no perezosos en el perfil activo, exista al menos un proveedor seleccionado tras `Registrar.select_and_bind`.
- Marca dependencias opcionales usando `Optional[T]`/`T | None` o define valores por defecto en los parámetros para evitar errores cuando su ausencia sea aceptable.
- Para inyecciones de colección, provee al menos un binding o establece un valor por defecto (por ejemplo, lista vacía) si la ausencia es válida semánticamente.
- Usa `lazy=True` en componentes cuyo coste de validación/resolución deba diferirse conscientemente, asumiendo el riesgo de errores en el primer acceso.
- Si usas perfiles/condiciones, revisa que estén configurados antes de `init()` para que la selección de proveedores sea coherente con el entorno objetivo.

---

## Ejemplos de resultados de validación

- Dependencia faltante requerida:
  - Componente A requiere `ServiceX` sin valor por defecto ni `Optional` y no existe proveedor de `ServiceX` en el perfil activo → `InvalidBindingError`.
- Inyección de lista sin proveedores:
  - Componente B requiere `List[Plugin]` y no hay `Plugin` registrados → `InvalidBindingError` (salvo que el parámetro tenga valor por defecto u opcionalidad).
- Ciclo entre componentes no perezosos:
  - A requiere B y B requiere A → `CircularDependencyError` durante la validación o en el primer intento de resolución.
- Dependencia opcional no satisfecha:
  - Componente C tiene `repo: Optional[Repo] = None` y no hay `Repo` → no se considera error.
