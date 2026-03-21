# Mocking and Fakes

Mocks are powerful but easy to abuse. Over‑mocking leads to tests that pass even when the real system is broken.

## Designing for Mockability

At system boundaries, design interfaces that are easy to mock:

### 1. Use dependency injection**

Pass external dependencies in rather than creating them internally:

```typescript
// Easy to mock
function processPayment(order, paymentClient) {
  return paymentClient.charge(order.total);
}

// Hard to mock
function processPayment(order) {
  const client = new StripeClient(process.env.STRIPE_KEY);
  return client.charge(order.total);
}
```

### 2. Prefer SDK-style interfaces over generic fetchers

Create specific functions for each external operation instead of one generic function with conditional logic:

```typescript
// GOOD: Each function is independently mockable
const api = {
  getUser: (id) => fetch(`/users/${id}`),
  getOrders: (userId) => fetch(`/users/${userId}/orders`),
  createOrder: (data) => fetch('/orders', { method: 'POST', body: data }),
};

// BAD: Mocking requires conditional logic inside the mock
const api = {
  fetch: (endpoint, options) => fetch(endpoint, options),
};
```

Prefer:

- **Real collaborators** where possible (e.g., in‑memory implementations).
- **Simple fakes** over complex mocking frameworks.
- **Module boundaries** that make it easy to plug in a fake implementation.

Use mocks when:

- Hitting the real dependency is **too slow, flaky, or expensive** (external APIs, long‑running jobs).
- You need to assert that a specific side effect happened (e.g., “an email was queued”).

When you do mock:

- Mock at **clear boundaries**, not deep inside a module.
- Avoid asserting on every tiny call; focus on behavior that matters.
- Ask: “Would this test still pass if the real implementation were wrong?” If yes, change the test.
