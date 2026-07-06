# Grasshopper integration

## Initial integration

1. Install Hops in Rhino/Grasshopper.
2. Run:

```powershell
python -m wheelchair_layout_solver.hops_server
```

3. Add a Hops component.
4. Set its path to:

```text
http://127.0.0.1:5000/check_pose
```

Inputs:
- `Scene`: complete scene JSON;
- `X`;
- `Y`;
- `Angle`.

Output:
- JSON result containing validity, collisions, clearance and footprint.

A `.gh` definition will be added after the JSON contract and layer convention
are validated with a real sample file.
