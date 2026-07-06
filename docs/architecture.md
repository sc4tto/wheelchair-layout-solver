# Architecture

```text
Rhino / Grasshopper
        |
        | JSON / HTTP through Hops
        v
Python service
  - schema validation
  - collision checker
  - path planner
  - functional checks
  - optimizer
        |
        v
Results returned to Grasshopper
```

The Python engine must not depend on Rhino. Rhino-specific code belongs in
adapters. This makes the engine reusable by a desktop app, Unreal or a web API.
