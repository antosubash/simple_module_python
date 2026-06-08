# Events

`EventBus` is an **in-process** pub/sub mechanism. It's not a message broker — no persistence, no retries, no cross-process delivery. For durable async work, use the `background_tasks` module (Celery) or publish a domain event and have a handler enqueue a Celery task.

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
        await self.session.flush()   # need the id
        await self.bus.publish(OrderPlaced(
            order_id=order.id,
            customer_email=order.customer_email,
            total=order.total,
        ))
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

bus.subscribe(OrderEvent, audit_handler)     # receives only OrderEvent, NOT subclasses
bus.subscribe(OrderPlaced, specific_handler) # receives only OrderPlaced
```

If you want a handler to see several event types, subscribe it to each one explicitly.

## Delivery semantics

- **Awaited** from the publisher's perspective: `await bus.publish(...)` runs all handlers **concurrently** via `asyncio.gather` and resolves once they've all completed. (Use `publish_nowait(...)` for fire-and-forget scheduling on the loop.)
- **In-process only.** Not delivered to other uvicorn workers, other processes, or other hosts.
- **No persistence.** A crash mid-publish loses undelivered events.
- **Handler failures are isolated.** `publish` gathers with `return_exceptions=True`: each handler exception is logged and the publish itself never raises.

If you need durable delivery across processes, handlers should enqueue a Celery task:

```python
def register_event_handlers(self, bus: EventBus) -> None:
    bus.subscribe(OrderPlaced, self._enqueue_invoice)

async def _enqueue_invoice(self, event: OrderPlaced) -> None:
    from invoices.tasks import create_invoice_task
    create_invoice_task.delay(event.order_id)
```

## Testing

Subscribe a spy in a test fixture:

```python
@pytest.mark.asyncio
async def test_place_order_publishes_event(db_session, app):
    received: list[OrderPlaced] = []
    app.state.sm.event_bus.subscribe(
        OrderPlaced, lambda e: received.append(e)
    )

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
