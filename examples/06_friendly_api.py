"""
Example 6: Create/export a part with the session API.

Prerequisites:
    1. SOLIDWORKS is installed; launch manually or through the script.
    2. pywin32 is installed: pip install pywin32.
"""
import sys

sys.path.insert(0, r"../scripts")

from sw_connect import mm
from sw_part import extrude_boss, sketch, sketch_circle
from sw_session import SolidWorksSession


def main():
    """Create a cylinder and export STEP."""
    session = SolidWorksSession()
    model = session.new_part()

    with sketch(model, "Front Plane") as sketch_name:
        sketch_circle(model, 0, 0, mm(25))

    extrude_boss(model, sketch_name, mm(50))

    session.save(model, r"C:\temp\friendly_cylinder.sldprt")
    session.export(model, r"C:\temp\friendly_cylinder.step")
    print("Tamamlandı: C:\\temp\\friendly_cylinder.sldprt / .step")


if __name__ == "__main__":
    main()
