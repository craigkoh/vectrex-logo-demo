# Vectrex Logo Demo

This project converts a simple SVG logo into line segments that are friendly to a Vectrex/PiTrex display, previews the result locally, and emits a C header you can compile into a PiTrex program.

## What is here

- `tools/svg_to_vectrex.py`: converts SVG shapes/paths into centered line segments
- `tools/preview_logo.py`: renders the generated line data into an SVG preview on your desktop
- `tools/build_native_vectrex.py`: builds a native Vectrex `.bin` ROM for emulators
- `src/logo_demo.c`: PiTrex demo program using the official `vectrexInterface` flow
- `generated/logo_segments.h`: generated line data included by the demo
- `tests/test_svg_to_vectrex.py`: converter tests

## Quick start

1. Put your logo SVG at `assets/logo.svg`
2. Convert it:

   ```bash
   python3 tools/svg_to_vectrex.py assets/logo.svg \
     --header generated/logo_segments.h \
     --json generated/logo_segments.json \
     --preview generated/logo_preview.svg
   ```

3. Create a larger desktop preview if you want:

   ```bash
   python3 tools/preview_logo.py generated/logo_segments.json --output generated/logo_preview_large.svg
   ```

4. Run the tests:

   ```bash
   python3 -m unittest discover -s tests -p 'test_*.py'
   ```

5. Build a native Vectrex ROM for OpenEmu/vecx:

   ```bash
   python3 tools/build_native_vectrex.py
   ```

   This writes:

   - `build/actioncorp_logo.asm`
   - `build/actioncorp_logo.bin`

## PiTrex build notes

The PiTrex wiki shows a normal Linux workflow where you clone the PiTrex repo and build example programs with `make -f Makefile.raspbian`, and the Vectrex Interface page shows a minimal program pattern using:

- `vectrexinit(1);`
- `v_setName("...");`
- `v_init();`
- `v_setRefresh(60);`
- `v_WaitRecal();`
- `v_directDraw32(...);`

This demo source follows that pattern. To build it on your PiTrex setup, the simplest path is:

1. Clone the PiTrex repo on the Pi.
2. Copy `src/logo_demo.c` and `generated/logo_segments.h` into a new or existing sample directory in that repo.
3. Use the same Makefile style as the PiTrex `hello_world` examples and build with `make -f Makefile.raspbian`.

Because this local machine does not currently have the PiTrex SDK installed, the code in this repo is verified here by:

- testing the SVG converter
- generating the C header
- generating an SVG preview of the exact segments that the Vectrex program will draw

## Emulator note

`vecx` and OpenEmu emulate native Vectrex ROMs. The sample program in `src/logo_demo.c` is a PiTrex program, which runs on the Raspberry Pi attached to the PiTrex cartridge, so it is not something OpenEmu or vecx can load directly as a `.bin`.

This repo now also includes a native Vectrex ROM builder. It rescales the generated logo line data into 8-bit Vectrex coordinates and assembles a cartridge ROM at `build/actioncorp_logo.bin`.

## Current testing status

I can test the converter and preview pipeline here right now.

I cannot yet run the PiTrex C program in a Vectrex emulator on this machine because there is no local PiTrex toolchain or emulator installed. If you want, the next step can be either:

- you drop your real logo SVG into `assets/logo.svg` and I wire it in here
- or I help you install a PiTrex build environment and emulator so we can try to compile and run it too

## Sources

- [PiTrex Linux example](https://www.ombertech.com/cnk/pitrex/wiki/index.php?wiki=Linux_Example)
- [PiTrex Vectrex Interface reference](https://www.ombertech.com/cnk/pitrex/wiki/index.php?wiki=Vectrex_Interface)
