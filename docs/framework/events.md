# Events

`EventBus` is an **in-process** pub/sub mechanism. `publish` is not a message broker — no persistence, no retries, no cross-process delivery. For events that must be handled even across a crash, use [durable delivery](#durable-delivery) (`subscribe_durable` / `publish_durable`), through the `DurableTransport` protocol extension point. The framework ships an outbox implementation in `background_tasks`. To tell *other worker processes* that something they cached is stale, use the [invalidation bus](/framework/invalidation) instead — same shape, deliberately narrower contract.

Events are the preferred way for modules to react to **other modules'** actions without creating a direct code dependency.

## Defining events

Base class is `Event` from `simple_module_core.events`. Subclass per domain event. Use `@dataclass`:

```python
# modules/orders/orders/contracts/events.py
from dataclasses import dataclass
from decimal import Decimal
from simple_module_core.events import Event


@dataclass
class OrderPlaced(Event):
    order_id: int
    customer_email: str
    total: Decimal


@dataclass
class OrderCancelled(Event):
    order_id: int
    reason: str
```

Events live in `contracts/events.py` — the **public surface** of the module. Other modules import them with `from orders.contracts.events import OrderPlaced`.

## Subscribing

Inside `register_event_handlers`:

```python
# modules/invoices/invoices/module.py
from orders.contracts.events import OrderPlaced

class InvoicesModule(ModuleBase):
    meta = ModuleMeta(
        name="Invoices",
        depends_on=["Orders"],    # subscribe to its events
        ...
    )

    def register_event_handlers(self, bus: EventBus) -> None:
        bus.subscribe(OrderPlaced, self._on_order_placed)

    async def _on_order_placed(self, event: OrderPlaced) -> None:
        await self._invoice_service.create_for(event.order_id)
```

`depends_on=["Orders"]` is needed so `Invoices.register_event_handlers` runs *after* `Orders` has been discovered. Cross-module subscriptions should always have the corresponding `depends_on`.

Handlers can be sync or async — the bus detects coroutines and awaits them.

## Publishing

Grab the bus from the framework services and await the publish:

```python
class OrderService:
    def __init__(self, session: AsyncSession, bus: EventBus) -> None:
        self.session = session
        self.bus = bus

    async def place(self, data: OrderCreate) -> Order:
        order = Order(**data.model_dump())
        self.session.add(order)
        await self.session.flush()  # need the id
        await self.bus.publish(
            OrderPlaced(
                order_id=order.id,
                customer_email=order.customer_email,
                total=order.total,
            )
        )
        return order
```

Get the bus as a FastAPI dependency:

```python
# modules/orders/orders/deps.py
from fastapi import Depends, Request
from simple_module_core.events import EventBus


def _event_bus(request: Request) -> EventBus:
    return request.app.state.sm.event_bus


EventBusDep = Annotated[EventBus, Depends(_event_bus)]
```

## Exact-type dispatch

The bus (backed by `pyee`'s `AsyncIOEventEmitter`) keys handlers by the **exact** event type — internally `f"{event_type.__module__}.{event_type.__qualname__}"`. There is **no MRO walk**: subscribing to a base class does **not** deliver subclass events. Subscribe to each concrete type you care about:

```python
@dataclass
class OrderEvent(Event): ...


@dataclass
class OrderPlaced(OrderEvent): ...


@dataclass
class OrderCancelled(OrderEvent): ...


bus.subscribe(OrderEvent, audit_handler)  # receives only OrderEvent, NOT subclasses
bus.subscribe(OrderPlaced, specific_handler)  # receives only OrderPlaced
```

If you want a handler to see several event types, subscribe it to each one explicitly.

## Delivery semantics

- **Awaited** from the publisher's perspective: `await bus.publish(...)` runs all handlers **concurrently** via `asyncio.gather` and resolves once they've all completed. (Use `publish_nowait(...)` for fire-and-forget scheduling on the loop.)
- **In-process only.** Not delivered to other uvicorn workers, other processes, or other hosts.
- **No persistence.** A crash mid-publish loses undelivered events.
- **Handler failures are isolated.** `publish` gathers with `return_exceptions=True`: each handler exception is logged and the publish itself never raises.

If you need durable delivery across processes, use [durable delivery](#durable-delivery) below. The older pattern — a handler that enqueues a Celery task — still works, but loses the event if the process dies between the commit and the enqueue:

```python
def register_event_handlers(self, bus: EventBus) -> None:
    bus.subscribe(OrderPlaced, self._enqueue_invoice)


async def _enqueue_invoice(self, event: OrderPlaced) -> None:
    from invoices.tasks import create_invoice_task

    create_invoice_task.delay(event.order_id)
```

## Durable delivery

```python
from simple_module_core import DurableContext


def register_event_handlers(self, bus: EventBus, app=None) -> None:
    bus.subscribe_durable(OrderPlaced, create_invoice)  # name defaults to the import path


async def create_invoice(event: OrderPlaced, ctx: DurableContext) -> None:
    ctx.db.add(Invoice(order_id=event.order_id))


# publisher, inside its transaction:
await bus.publish_durable(OrderPlaced(order_id=order.id, ...), db)
```

- `publish_durable(event, db)` hands the event to `bus.durable_transport`, which
  writes it in `db`'s transaction: a rollback means it was never published. With
  no transport installed it raises `DurableDeliveryUnavailable` rather than
  quietly falling back to in-process delivery. It does **not** call `subscribe`
  handlers; publish separately if you want both.
- Handlers are called later, by a worker, as `await handler(event, ctx)`.
  Delivery is **at-least-once** with exponential backoff; database writes made
  through `ctx.db` commit with the delivery record and so land **exactly once**
  — provided the handler never commits `ctx.db` itself (the transport refuses
  that with `HandlerCommitError`; flush instead). Everything else a handler does
  (HTTP calls, emails, other sessions) may happen more than once: make it
  idempotent. Savepoints (`ctx.db.begin_nested()`) are allowed. Each attempt
  has a timeout just inside the transport's lease; handlers must not block the
  event loop (use `run_in_executor` for blocking work) or swallow
  `CancelledError`. `ctx.attempt` counts from 1. The handler runs in the scope
  it was published in: the publisher's tenant; `all_tenants()` for an event
  published inside `all_tenants()`; or, for one published with no tenant bound
  at all, no tenant (strict isolation fails closed, as it would have for the
  publisher).
- A durable handler may itself `publish_durable(..., ctx.db)`; the new event
  commits with the handler's delivery.
- The handler `name=` (default `f"{handler.__module__}.{handler.__qualname__}"`)
  keys delivery state, so keep it stable across deploys.
- Events must be `@dataclass` classes serialisable to JSON; `UUID`, `datetime`,
  `Enum`, `Decimal` and nested dataclasses round-trip. This is checked when you
  subscribe.
- The worker builds its own bus by calling every module's
  `register_event_handlers(bus, None)` — subscribe durably *before* any early
  `return` taken when `app is None`.

`DurableTransport` (`simple_module_core.durable_events`) is the extension point: a protocol (`async enqueue(event, handler_names, db)`), so
another module could provide one; `background_tasks` is the shipped
implementation — see [its docs](/modules/background_tasks#durable-events-outbox)
for the outbox, retries, the admin page and the worker side.

## Testing

Subscribe a spy in a test fixture:

```python
@pytest.mark.asyncio
async def test_place_order_publishes_event(db_session, app):
    received: list[OrderPlaced] = []
    app.state.sm.event_bus.subscribe(OrderPlaced, lambda e: received.append(e))

    service = OrderService(db_session, app.state.sm.event_bus)
    await service.place(OrderCreate(customer_email="a@b.c", total=Decimal("1")))

    assert len(received) == 1
    assert received[0].customer_email == "a@b.c"
```

The `app` fixture from the `simple_module_test` plugin provides a fresh app with a fresh `EventBus` per test.

## Design guidelines

- **Events describe facts about the past** (`OrderPlaced`), not commands (`PlaceOrder`). If you're tempted to name an event imperatively, you actually want a service call.
- **Keep events small and stable.** They're a public API. Breaking the shape of `OrderPlaced` breaks every subscriber. Add new fields with defaults; don't remove or rename.
- **Don't use events for request/response.** If the publisher needs a result, call a service directly. Events are fire-and-observe.
- **Avoid circular publishing.** Handler A publishes event X; handler B (subscribed to X) publishes event Y; handler C (subscribed to Y) publishes X. The bus doesn't detect this — it'll run forever. Guard with a flag or redesign the flow.
