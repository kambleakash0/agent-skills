# Interface Design for TDD

Good interfaces make TDD easy. Bad interfaces make every test feel like a fight.

1. **Accept dependencies, don't create them**

   ```typescript
   // Testable
   function processOrder(order, paymentGateway) {}

   // Hard to test
   function processOrder(order) {
     const gateway = new StripeGateway();
   }
   ```

2. **Return results, don't produce side effects**

   ```typescript
   // Testable
   function calculateDiscount(cart): Discount {}

   // Hard to test
   function applyDiscount(cart): void {
     cart.total -= discount;
   }
   ```

3. **Small surface area**
   - Fewer methods = fewer tests needed
   - Fewer params = simpler test setup

When designing an interface, aim for:

- **Clarity:** Names that describe what the caller wants, not how you implement it.
- **Small surface area:** A few well‑chosen entrypoints instead of many tiny configuration knobs.
- **Good defaults:** Reasonable behavior without requiring every option to be set.
- **Stability:** An interface that can stay the same while internals evolve.

Ask yourself:

- “If I were a caller, could I use this API **without reading the implementation**?”
- “Can I write one or two high‑value tests that hit this interface and cover most of the behavior I care about?”
- “Does this interface match the words my team uses when talking about the domain?”

If it takes several steps of low‑level calls to do anything useful, consider introducing a higher‑level function or method that encapsulates the common path.
