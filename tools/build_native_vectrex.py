#!/usr/bin/env python3
"""Build a native Vectrex ROM from generated logo segment data."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

HARDWARE_TARGET_ABS = 72
HARDWARE_LINE_SCALE = 96
HARDWARE_BRIGHTNESS = 72
SCREEN_ASPECT_RATIO = 11.0 / 9.0


ROM_TEMPLATE = """\
        ORG     $0000

WAIT_RECAL      EQU     $F192
INTENSITY_A     EQU     $F2AB
RESET0REF       EQU     $F354
MOVETO_D        EQU     $F312
DRAW_VL_MODE    EQU     $F46E
VIA_T1_CNT_LO   EQU     $D004
VEC_PATTERN     EQU     $C829
POS_Y           EQU     $C880
POS_X           EQU     $C881
VEL_Y           EQU     $C882
VEL_X           EQU     $C883
MOVE_MODE       EQU     $C884
MOVE_PHASE      EQU     $C885
STEP_Y          EQU     $C886
STEP_X          EQU     $C887
HIT_Y           EQU     $C888
HIT_X           EQU     $C889

        FCB     $67,$20
        FCC     "GCE 2026"
        FCB     $80
        FDB     $F600
        FCB     $F8,$50,20,-40
        FCC     "ACTIONCORP"
        FCB     $80,0

start:
        CLR     POS_Y
        CLR     POS_X
        CLR     MOVE_PHASE
        LDA     #1
        STA     VEL_Y
        STA     VEL_X
        STA     MOVE_MODE

frame:
        JSR     WAIT_RECAL
        LDA     #{brightness}
        JSR     INTENSITY_A
        LDA     #$FF
        STA     VEC_PATTERN
        LDA     #{line_scale}
        STA     VIA_T1_CNT_LO
        JSR     draw_logo
        JSR     update_position
        BRA     frame

draw_logo:
{draw_calls}
        RTS

update_position:
        CLR     HIT_Y
        CLR     HIT_X

        LDA     VEL_Y
        STA     STEP_Y
        LDA     VEL_X
        STA     STEP_X

        LDA     MOVE_PHASE
        EORA    #1
        STA     MOVE_PHASE

        LDA     MOVE_MODE
        CMPA    #1
        BNE     check_mode_two
        LDA     MOVE_PHASE
        BEQ     steps_ready
        LDA     STEP_Y
        ADDA    VEL_Y
        STA     STEP_Y
        BRA     steps_ready

check_mode_two:
        CMPA    #2
        BNE     steps_ready
        LDA     MOVE_PHASE
        BEQ     steps_ready
        LDA     STEP_X
        ADDA    VEL_X
        STA     STEP_X

steps_ready:
        LDA     POS_Y
        ADDA    STEP_Y
        CMPA    #{min_y}
        BLT     bounce_y_min
        CMPA    #{max_y}
        BGT     bounce_y_max
store_y:
        STA     POS_Y

        LDA     POS_X
        ADDA    STEP_X
        CMPA    #{min_x}
        BLT     bounce_x_min
        CMPA    #{max_x}
        BGT     bounce_x_max
store_x:
        STA     POS_X
        BRA     update_mode

bounce_y_min:
        LDA     VEL_Y
        NEGA
        STA     VEL_Y
        LDA     #1
        STA     HIT_Y
        LDA     #{min_y}
        BRA     store_y

bounce_y_max:
        LDA     VEL_Y
        NEGA
        STA     VEL_Y
        LDA     #1
        STA     HIT_Y
        LDA     #{max_y}
        BRA     store_y

bounce_x_min:
        LDA     VEL_X
        NEGA
        STA     VEL_X
        LDA     #1
        STA     HIT_X
        LDA     #{min_x}
        BRA     store_x

bounce_x_max:
        LDA     VEL_X
        NEGA
        STA     VEL_X
        LDA     #1
        STA     HIT_X
        LDA     #{max_x}
        BRA     store_x

update_mode:
        LDA     HIT_Y
        BEQ     done_update
        LDA     HIT_X
        BEQ     done_update
        LDA     POS_Y
        CMPA    #{max_y}
        BEQ     top_corner
        LDA     POS_X
        CMPA    #{max_x}
        BEQ     set_mode_two
        LDA     #1
        STA     MOVE_MODE
        RTS

top_corner:
        LDA     POS_X
        CMPA    #{max_x}
        BEQ     set_mode_one

set_mode_two:
        LDA     #2
        STA     MOVE_MODE
        RTS

set_mode_one:
        LDA     #1
        STA     MOVE_MODE

done_update:
        RTS

{packet_rows}

        END     start
"""


def clamp_byte(value: int) -> int:
    if value < -127 or value > 127:
        raise ValueError(f"Coordinate {value} does not fit in signed 8-bit range")
    return value


def render_fcb(value: int) -> str:
    if value < 0:
        return f"-{abs(value)}"
    return str(value)


def make_native_lines(lines: list[list[int]], target_abs: int = HARDWARE_TARGET_ABS) -> list[tuple[int, int, int, int]]:
    max_endpoint = max(abs(coord) for line in lines for coord in line[:4])
    max_delta = max(
        max(abs(line[2] - line[0]), abs(line[3] - line[1]))
        for line in lines
    )
    scale = max(max_endpoint, max_delta) / float(target_abs)
    if scale < 1.0:
        scale = 1.0

    native: list[tuple[int, int, int, int]] = []
    for x0, y0, x1, y1, _brightness in lines:
        sx = clamp_byte(int(round(x0 / scale)))
        sy = clamp_byte(int(round(y0 / scale)))
        dx = clamp_byte(int(round((x1 - x0) / scale)))
        dy = clamp_byte(int(round((y1 - y0) / scale)))
        native.append((sy, sx, dy, dx))
    return native


def native_logo_bounds(lines: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    xs = []
    ys = []
    for sy, sx, dy, dx in lines:
        xs.extend([sx, sx + dx])
        ys.extend([sy, sy + dy])
    return min(ys), max(ys), min(xs), max(xs)


def split_polylines(lines: list[tuple[int, int, int, int]]) -> list[list[tuple[int, int, int, int]]]:
    polylines: list[list[tuple[int, int, int, int]]] = []
    current: list[tuple[int, int, int, int]] = []
    cursor: tuple[int, int] | None = None

    for line in lines:
        sy, sx, dy, dx = line
        start = (sy, sx)
        end = (clamp_byte(sy + dy), clamp_byte(sx + dx))
        if current and start != cursor:
            polylines.append(current)
            current = []
        current.append(line)
        cursor = end

    if current:
        polylines.append(current)

    return polylines


def build_asm(
    lines: list[tuple[int, int, int, int]],
    *,
    brightness: int = HARDWARE_BRIGHTNESS,
    line_scale: int = HARDWARE_LINE_SCALE,
) -> str:
    draw_calls = []
    packet_sections = []

    for index, polyline in enumerate(split_polylines(lines)):
        start_y, start_x, _, _ = polyline[0]
        packet_name = f"logo_packet_{index}"
        draw_calls.extend(
            [
                "        JSR     RESET0REF",
                "        LDA     POS_Y",
                "        LDB     POS_X",
                "        JSR     MOVETO_D",
                f"        LDA     #{render_fcb(start_y)}",
                f"        LDB     #{render_fcb(start_x)}",
                "        JSR     MOVETO_D",
                f"        LDX     #{packet_name}",
                "        JSR     DRAW_VL_MODE",
            ]
        )

        rows = [f"{packet_name}:"]
        for _sy, _sx, dy, dx in polyline:
            rows.append(
                "        FCB     $FF,{0},{1}".format(
                    render_fcb(dy),
                    render_fcb(dx),
                )
            )
        rows.append("        FCB     $01")
        packet_sections.append("\n".join(rows))

    logo_min_y, logo_max_y, logo_min_x, logo_max_x = native_logo_bounds(lines)
    margin = 6
    max_safe_x = min(abs(-127 - logo_min_x + margin), abs(127 - logo_max_x - margin))
    max_safe_y = min(abs(-127 - logo_min_y + margin), abs(127 - logo_max_y - margin))
    x_travel = clamp_byte(max_safe_x)
    y_travel = clamp_byte(min(120, int(round(x_travel * SCREEN_ASPECT_RATIO))))
    min_y = render_fcb(-y_travel)
    max_y = render_fcb(y_travel)

    return ROM_TEMPLATE.format(
        draw_calls="\n".join(draw_calls),
        packet_rows="\n\n".join(packet_sections),
        min_y=min_y,
        max_y=max_y,
        min_x=render_fcb(-x_travel),
        max_x=render_fcb(x_travel),
        brightness=render_fcb(brightness),
        line_scale=render_fcb(line_scale),
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-json",
        type=Path,
        default=Path("generated/logo_segments.json"),
        help="Generated line JSON from svg_to_vectrex.py",
    )
    parser.add_argument(
        "--asm-output",
        type=Path,
        default=Path("build/actioncorp_logo.asm"),
        help="Where to write the generated assembly source",
    )
    parser.add_argument(
        "--bin-output",
        type=Path,
        default=Path("build/actioncorp_logo.bin"),
        help="Where to write the assembled Vectrex ROM",
    )
    parser.add_argument(
        "--target-abs",
        type=int,
        default=HARDWARE_TARGET_ABS,
        help="Maximum native logo coordinate magnitude before Vectrex scale is applied",
    )
    parser.add_argument(
        "--line-scale",
        type=int,
        default=HARDWARE_LINE_SCALE,
        help="Vectrex timer scale for drawn lines",
    )
    parser.add_argument(
        "--brightness",
        type=int,
        default=HARDWARE_BRIGHTNESS,
        help="Vectrex beam brightness",
    )
    args = parser.parse_args(argv)

    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    native_lines = make_native_lines(payload["lines"], target_abs=args.target_abs)
    asm_text = build_asm(native_lines, brightness=args.brightness, line_scale=args.line_scale)

    args.asm_output.parent.mkdir(parents=True, exist_ok=True)
    args.bin_output.parent.mkdir(parents=True, exist_ok=True)
    args.asm_output.write_text(asm_text, encoding="utf-8")

    result = subprocess.run(
        ["asm6809", "-o", str(args.bin_output), str(args.asm_output)],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode

    print(f"Wrote assembly: {args.asm_output}")
    print(f"Wrote ROM:      {args.bin_output}")
    print(f"Native lines:   {len(native_lines)}")
    print(f"Objects:        {len(split_polylines(native_lines))}")
    print(f"ROM bytes:      {args.bin_output.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
