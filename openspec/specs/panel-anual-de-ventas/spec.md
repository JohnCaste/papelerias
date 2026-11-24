# panel-anual-de-ventas Specification

## Purpose
TBD - created by archiving change pulir-ventas-por-dia. Update Purpose after archive.
## Requirements
### Requirement: Total del año sobre el grid de meses

En el nivel de meses de la pantalla de Ventas, el sistema SHALL mostrar sobre el
grid de las 12 cards de mes el total vendido en el año seleccionado, calculado
como la suma de los `total` de los buckets diarios de `/api/agregaciones` del año.
El total SHALL actualizarse al cambiar de año con el stepper y al guardarse un
día desde el `ModalVentaDia`.

#### Scenario: El total anual suma todos los meses

- **WHEN** el año en curso tiene meses con totales `$1.000`, `$2.500` y `$0` en el
  resto
- **THEN** la cabecera del nivel de meses muestra `Total del año: $ 3.500`

#### Scenario: Año sin ventas

- **WHEN** el año seleccionado no tiene ningún día con registro
- **THEN** el total del año se muestra como `$ 0`

#### Scenario: Guardar un día actualiza el total anual

- **WHEN** se guarda desde el modal un día por `$200` en un año cuyo total era
  `$3.500`
- **THEN** tras la recarga la cabecera muestra `Total del año: $ 3.700` (o la
  diferencia correspondiente si el día ya tenía captura)

### Requirement: Mes de mayor y menor venta del año

En el nivel de meses, junto al total del año, el sistema SHALL señalar el mes con
mayor `total` y el mes con menor `total` considerando únicamente los meses con al
menos un día con registro en el año. Si un solo mes tiene registro, ese mes SHALL
figurar como mayor y no se SHALL mostrar un mes de menor venta distinto. Si
ningún mes tiene registro, no se SHALL mostrar mayor ni menor.

#### Scenario: Se destacan extremos entre meses con registro

- **WHEN** el año tiene ventas en marzo (`$4.000`), julio (`$1.200`) y octubre
  (`$2.500`) y el resto de meses en cero sin registro
- **THEN** la cabecera indica marzo como mes de mayor venta y julio como mes de
  menor venta, y octubre no se destaca

#### Scenario: Meses futuros o sin registro no cuentan como mínimo

- **WHEN** es septiembre y de enero a agosto hay ventas pero septiembre a
  diciembre aún no tienen registro
- **THEN** el mes de menor venta se elige entre enero y agosto, nunca un mes sin
  registro

#### Scenario: Un único mes con registro

- **WHEN** solo enero tiene ventas en el año
- **THEN** enero se muestra como mes de mayor venta y no se muestra un mes de
  menor venta

### Requirement: Día de mayor y menor venta dentro de un mes

En el nivel de días de un mes, el sistema SHALL señalar el día con mayor `total`
y el día con menor `total` considerando únicamente los días con registro de ese
mes. Si un solo día tiene registro, ese día SHALL figurar como mayor y no se
SHALL mostrar un día de menor venta distinto. Si ningún día del mes tiene
registro, no se SHALL mostrar mayor ni menor.

#### Scenario: Se destacan extremos entre días con registro

- **WHEN** en el mes abierto hay registros los días 3 (`$150`), 10 (`$900`) y 21
  (`$400`) y el resto de días sin registro
- **THEN** la vista del mes indica el día 10 como día de mayor venta y el día 3
  como día de menor venta

#### Scenario: Días sin registro no cuentan como mínimo

- **WHEN** el mes tiene 20 días sin registro y 2 días con registro de `$500` y
  `$700`
- **THEN** el día de menor venta es el de `$500`, no un día en cero sin registro

#### Scenario: Mes sin registro no muestra extremos

- **WHEN** el mes abierto no tiene ningún día con registro
- **THEN** no se muestra día de mayor ni de menor venta

### Requirement: El esquema de cards Año → Mes → Día se mantiene

El sistema SHALL conservar la navegación por cards en tres niveles (grid de 12
meses → calendario de días del mes → `ModalVentaDia`) sin reintroducir el
agrupado por semana. Los datos de todos los niveles SHALL provenir de los buckets
diarios de `/api/agregaciones` con `granularidad=dia`.

#### Scenario: No hay nivel ni controles de semana

- **WHEN** se navega la pantalla de Ventas de meses a días
- **THEN** no aparece ningún selector, botón ni fila de semana; se pasa
  directamente del grid de meses al calendario de días

#### Scenario: Fuente única de datos

- **WHEN** se carga cualquier nivel de la pantalla de Ventas
- **THEN** la única petición de datos de ventas es a `/api/agregaciones` con
  `granularidad=dia`

