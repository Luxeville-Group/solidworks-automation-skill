"""
Example 3: Create an assembly.
Demonstrates adding components and Mate relationships.
"""
import sys
sys.path.insert(0, r"../scripts")

from sw_connect import connect_solidworks, new_document, mm
from sw_assembly import (
    add_component,
    add_mate_coincident,
    add_mate_concentric,
    get_components
)

def main():
    sw, _ = connect_solidworks()

    # Create a new assembly.
    print("Montaj oluşturuluyor...")
    asm = new_document(sw, "assembly")

    # Add the first component (fixed).
    print("Parça ekleniyor...")
    part1_path = r"C:\parts\base.sldprt"
    part2_path = r"C:\parts\shaft.sldprt"

    comp1 = add_component(asm, part1_path, 0, 0, 0)
    comp2 = add_component(asm, part2_path, mm(50), 0, 0)

    # Add Mate relationships.
    print("Mate ekleniyor...")
    # Coincident Mate: align two planes.
    add_mate_coincident(
        asm,
        "Front Plane@base-1", "PLANE",
        "Front Plane@shaft-1", "PLANE"
    )

    # Concentric Mate: align two cylinders.
    add_mate_concentric(
        asm,
        "Face1@base-1",
        "Face1@shaft-1"
    )

    # List all components.
    print("\nMontaj bileşenleri:")
    components = get_components(asm)
    for comp in components:
        print(f"  - {comp['name']}: {comp['path']}")

    print("\nMontaj oluşturuldu!")

if __name__ == "__main__":
    main()
