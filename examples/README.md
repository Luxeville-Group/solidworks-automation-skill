# SOLIDWORKS automation examples

These examples progress from part creation to assemblies, drawings, and Motion Study. They exercise CAD APIs; read and adjust their input/output paths before running them.

| Example | What it demonstrates | Prerequisites |
|---|---|---|
| `01_basic_part.py` | Connect, create a part, sketch a circle, extrude a cylinder with driving dimensions, save, and review | SOLIDWORKS available; `C:\temp` writable |
| `02_complex_part.py` | Create a rectangular plate with four dimension-driven holes, multiple sketches, and extruded cuts; review actual sketch state | SOLIDWORKS available |
| `03_assembly.py` | Add components, create coincident/concentric Mates, and list components | Provide `C:\parts\base.sldprt` and `C:\parts\shaft.sldprt`, or edit the paths |
| `04_batch_export.py` | Batch file processing, STEP export, and error handling | `.sldprt` files in `C:\parts`, or edit the source directory |
| `05_drawing.py` | Create a drawing, three standard views, automatic dimensions, notes, and PDF | Provide `C:\parts\mypart.sldprt`, or edit the path |
| `06_friendly_api.py` | Use `SolidWorksSession` to create/save/export, with `with sketch(...)` managing sketch entry/exit and reusable references | Running SOLIDWORKS or permission for the script to launch it; writable `C:\temp` |
| `07_motion_study_rotary_motor.py` | Load the Motion type library, create/activate a study, add a 60 RPM motor using shaft/impeller cylinders, calculate, and play | Existing fan assembly; edit `assembly_path` and component keywords; impeller must float and its concentric Mate must permit rotation |
| `08_mini_fan_motion_assembly.py` | Generate base, center shaft, cross-blade impeller, and guard; assemble with actual Mates; fix stationary parts, keep impeller free, add a 60 RPM motor, and export review evidence | SOLIDWORKS available; `C:\temp\solidworks_mini_fan_demo` writable |

The miniature fan is an execution-stability benchmark, not a finished industrial design. Fillets/chamfers are not success criteria: automated edge selection varies across versions, locales, and modeling order. Refine appearance through a separate, verified entity-selection strategy. The complex-plate example also prioritizes driven sketches and holes; it does not demonstrate every cosmetic feature.

## Run an example

Install the required Python COM dependencies, start SOLIDWORKS, then run the selected example from the repository root:

```powershell
python -m pip install pywin32 comtypes
python examples/01_basic_part.py
```

Change example paths for your workstation:

```python
# Input document
part_path = r"C:\your\path\part.sldprt"

# Output deliverable
output_path = r"C:\your\output\file.step"
```

## Troubleshooting

If connection fails, verify SOLIDWORKS is installed/running and the Python architecture matches it (normally 64-bit).

Reference-plane names depend on the installed CAD locale. Prefer the helper aliases `Front Plane`, `Top Plane`, and `Right Plane`; Turkish aliases include `Ön Düzlem`, `Üst Düzlem`, and `Sağ Düzlem`. Helpers preserve legacy CAD lookup names internally. For customized templates, use actual feature names and verify selection.

If feature creation fails, check the closed sketch profile, length units (use `mm()` to convert millimeters to API meters), and selected entities. Consult [troubleshooting](../references/troubleshooting.md).

## Türkçe başlangıç

Önce örnekteki dosya yollarını kendi bilgisayarınıza uyarlayın. SOLIDWORKS açıkken yukarıdaki komutla örneği çalıştırın. `Sketch` eskiz, `Extrude` doğrusal katı oluşturma, `Mate` montaj ilişkisi, `Motion Study` hareket çalışması anlamında kullanılır. API uzunlukları metredir; milimetre değerlerini `mm()` ile dönüştürün.

Oluşan parçayı, ölçüleri, montaj ilişkilerini ve raporu SOLIDWORKS içinde inceleyin. Örnek kodun tamamlanması, üretim uygunluğu veya dayanım onayı anlamına gelmez. Hareket örnekleri için ilgili lisans ve Add-in kullanılabilirliği de gereklidir.
