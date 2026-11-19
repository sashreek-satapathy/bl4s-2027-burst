""""""
BEAM_ENERGY_MEV = None
CONVERTER_MATERIAL = None
CONVERTER_THICKNESS_CM = None
NUMBER_OF_ELECTRONS = None
""""""

def check_inputs():
    inputs = {
        "Beam energy (MeV)": BEAM_ENERGY_MEV,
        "Converter material": CONVERTER_MATERIAL,
        "Converter thickness (cm)": CONVERTER_THICKNESS_CM,
        "Number of electrons": NUMBER_OF_ELECTRONS,
    }

    for name, value in inputs.items():
        if value is None:
            print("Still needed:", name)


if __name__ == "__main__":
    check_inputs()
