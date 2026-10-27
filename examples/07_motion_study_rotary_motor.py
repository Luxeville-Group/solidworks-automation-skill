"""
Example: Add a Motion Study rotary motor to an existing fan assembly.

Prerequisites:
1. SOLIDWORKS and Python pywin32/comtypes are installed.
2. Set assembly_path to your fan assembly path.
3. The assembly contains center-post and impeller components; the impeller concentric Mate does not lock rotation.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

from sw_connect import connect_solidworks, mm, open_document
from sw_assembly import find_component_by_name
from sw_motion import (
    create_motion_study,
    add_constant_speed_rotary_motor_by_cylinders,
    calculate_and_play,
)


def main():
    """Open the assembly and add a 60 RPM rotary motor."""
    assembly_path = r"C:\temp\desktop_mini_cooling_fan.SLDASM"
    sw, _ = connect_solidworks()
    asm = open_document(sw, assembly_path, silent=True, raise_on_error=True)

    stand_comp = find_component_by_name(asm, "stand")
    impeller_comp = find_component_by_name(asm, "impeller")

    study = create_motion_study(
        asm,
        name="Impeller_60RPM_ContinuousRotation",
        duration=4.0,
    )
    add_constant_speed_rotary_motor_by_cylinders(
        study,
        shaft_component=stand_comp,
        rotor_component=impeller_comp,
        shaft_radius=(mm(4.5), mm(5.5)),
        rotor_radius=(mm(10.5), mm(11.5)),
        rpm=60.0,
        name="ImpellerRotaryMotor_60RPM",
    )
    print(f"Motion Study hesaplama sonucu: {calculate_and_play(study)}")


if __name__ == "__main__":
    main()
