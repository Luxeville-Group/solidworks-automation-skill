# Drawing Generation Reference

## Standards

The GB/T route defaults to first-angle projection: top view below front, right view to the left. SOLIDWORKS
SetupSheet6 / NewSheet4 projection arguments must match the layout and be read back after generation.

## Evidence

- Read back view objects, orientation, position and scale.
- InsertModelAnnotations3/4 return values alone do not prove dimensions exist; read actual DisplayDimension objects.
- A template filename is only candidate evidence, not proof of GB/T-compliant content.
- PDF/BMP outputs must exist and be nonempty; PDF text bounds provide risk screening only.

## API rules

For new/unwrapped APIs, consult references/api-lookup.md and official API Help to verify signatures,
enums, returns and version differences. Return explicit failure states for None/False COM results.
