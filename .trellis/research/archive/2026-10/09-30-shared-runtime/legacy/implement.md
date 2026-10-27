# Implementation

Follow `.trellis/tasks/09-30-offline-desktop-tui/implement.md`.

Owner: Pi.

Deliverable: Implement all existing open operations through the frozen shared service; extract interactions, paths and progress without changing algorithms.

Validation: Existing regressions and new service/path/state tests pass; operation coverage matches menus.

Dependency: shared contract is frozen; frontend/backend may proceed concurrently with separate write ownership.
