"""
Example 5: Create a drawing.
Demonstrates adding views, dimensions, and a BOM table.
"""
import sys
sys.path.insert(0, r"../scripts")

from sw_connect import connect_solidworks, new_document
from sw_drawing import (
    create_standard_views,
    insert_dimensions,
    add_note,
    export_sheet_to_pdf
)

def main():
    sw, _ = connect_solidworks()

    # Create a new drawing.
    print("Teknik çizim oluşturuluyor...")
    drawing = new_document(sw, "drawing")

    # Specify the part path.
    part_path = r"C:\parts\mypart.sldprt"

    # Create three standard views.
    print("Üç standart görünüş oluşturuluyor...")
    create_standard_views(drawing, part_path)

    # Add dimensions automatically.
    print("Ölçüler ekleniyor...")
    insert_dimensions(drawing)

    # Add notes.
    print("Açıklamalar ekleniyor...")
    add_note(drawing, 0.1, 0.05, "Malzeme: 1045 çelik\nYüzey işlemi: galvaniz")

    # Export PDF.
    output_pdf = r"C:\exports\drawing.pdf"
    print(f"PDF dışa aktarma: {output_pdf}")
    export_sheet_to_pdf(drawing, output_pdf)

    print("Teknik çizim oluşturuldu!")

if __name__ == "__main__":
    main()
