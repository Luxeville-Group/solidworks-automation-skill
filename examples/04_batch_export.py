"""
Example 4: Batch export.
Demonstrates exporting SOLIDWORKS files to STEP in a batch.
"""
import sys
sys.path.insert(0, r"../scripts")

from sw_connect import connect_solidworks
from sw_export import batch_export
import glob

def main():
    sw, _ = connect_solidworks()

    # Get all part files.
    input_dir = r"C:\parts"
    output_dir = r"C:\exports\step"

    print(f"Kaynak {input_dir} toplu dışa aktarılıyor...")

    # Get all .sldprt files.
    part_files = glob.glob(f"{input_dir}\\*.sldprt")

    if not part_files:
        print("Parça dosyası bulunamadı!")
        return

    print(f"Bulunan {len(part_files)} dosya")

    # Batch-export to STEP.
    results = batch_export(sw, part_files, output_dir, ".step")

    # Show results.
    print("\nDışa aktarma sonuçları:")
    for result in results:
        status = "✓" if result["success"] else "✗"
        print(f"{status} {result['file']}")
        if result["success"]:
            print(f"   → {result['output']}")

if __name__ == "__main__":
    main()
