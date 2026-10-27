# Contributing

Report bugs and propose features through the [fork's issues](https://github.com/Luxeville-Group/solidworks-automation-skill/issues). Include the CAD version/service pack, Python version, OS version, sanitized error/stack trace and reproduction steps. Search existing issues before opening a feature request; explain the use case and expected behavior.

## Changes and verification

1. Fork this repository and create a focused branch.
2. Follow existing Python style: four spaces, snake_case functions/variables, PascalCase classes and UPPER_CASE constants.
3. Use English comments/docstrings and technical documentation. User-facing text is Turkish with English terminology; keep Turkish onboarding and the [glossary](localization/TERMS.tr-en.md) current.
4. Preserve API identifiers, enum values, JSON keys, units, numeric limits and evidence gates.
5. Run relevant offline tests. For native CAD changes, test the actual CAD version and retain save, reopen, feature/B-Rep and review evidence. Do not infer compatibility with untested versions.
6. Commit with a clear English summary, push your branch and open a pull request.

Document public functions with arguments, return values and units:

```python
def extrude_boss(model, sketch_name, depth, direction=True, merge=True):
    """Extrude a sketch into a boss.

    Args:
        model: Active SolidWorks model.
        sketch_name: Sketch name, for example "Sketch1".
        depth: Extrusion depth in meters.
        direction: True for the forward direction.
        merge: Whether to merge the result.

    Returns:
        The created IFeature object.
    """
    # Implementation follows the verified API wrapper.
```

## Repository map

- `scripts/`: core Python modules for connection, modeling, assemblies, drawings, export and review.
- `references/`: technical API and workflow documentation.
- `subskills/`: specialist workflows and their evidence requirements.
- `examples/`: sample inputs and runnable examples.
- `apps/`: desktop workbench.
- `tests/`: offline regression suite.
- `localization/`: Turkish/English policy and terminology.

For a new wrapper, first check `capabilities.yaml`, reuse the existing backend, update the relevant `scripts/sw_*.py` module and references, add an example and meaningful tests, and update the entry-point documentation. Keep unverified capabilities at their actual level; never promote them from a successful API return alone.

See [references](references/), [examples](examples/) and [official SolidWorks API help](https://help.solidworks.com/2026/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks_namespace.html).

Treat contributors respectfully, give constructive feedback and focus reviews on reproducible behavior and evidence.
