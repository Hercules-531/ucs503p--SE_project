# BharatOS UML diagrams

This folder contains the editable PlantUML source and the verified SVG/PNG renders for the complete planned BharatOS system.

| Diagram | Why it is included |
| --- | --- |
| Use case | Defines the system boundary, external actors and services available to each actor. |
| Class | Defines the main domain entities, multiplicities, compositions, inheritance and adapter interface. |
| Sequence | Explains the ordered runtime interactions for a protected API request. |
| Activity | Explains control flow, decisions and failure paths in data ingestion. |
| Component | Separates deployable responsibilities and shows dependencies on storage and official sources. |

Regenerate all assets from the project root:

```powershell
.venv\Scripts\python.exe scripts\render_diagrams.py
```

The renderer fails when the PlantUML server returns a syntax-error SVG, a dimensionless SVG or an invalid PNG. The final assets should also be visually reviewed before submission.
