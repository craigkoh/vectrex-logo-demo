#!/usr/bin/env python3
"""Convert a simple SVG into Vectrex/PiTrex-friendly line segments."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


COMMAND_RE = re.compile(r"[AaCcHhLlMmQqSsTtVvZz]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")


@dataclass
class Point:
    x: float
    y: float


@dataclass
class Segment:
    start: Point
    end: Point


def strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def distance(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def cubic_point(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    mt = 1.0 - t
    return Point(
        mt ** 3 * p0.x + 3 * mt ** 2 * t * p1.x + 3 * mt * t ** 2 * p2.x + t ** 3 * p3.x,
        mt ** 3 * p0.y + 3 * mt ** 2 * t * p1.y + 3 * mt * t ** 2 * p2.y + t ** 3 * p3.y,
    )


def quadratic_point(p0: Point, p1: Point, p2: Point, t: float) -> Point:
    mt = 1.0 - t
    return Point(
        mt ** 2 * p0.x + 2 * mt * t * p1.x + t ** 2 * p2.x,
        mt ** 2 * p0.y + 2 * mt * t * p1.y + t ** 2 * p2.y,
    )


def arc_to_center(
    start: Point,
    rx: float,
    ry: float,
    x_axis_rotation: float,
    large_arc: float,
    sweep: float,
    end: Point,
) -> tuple[Point, float, float, float, float]:
    if rx == 0 or ry == 0:
        return Point(0.0, 0.0), 0.0, 0.0, 0.0, 0.0

    phi = math.radians(x_axis_rotation % 360.0)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    dx2 = (start.x - end.x) / 2.0
    dy2 = (start.y - end.y) / 2.0

    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2

    rx = abs(rx)
    ry = abs(ry)

    lam = (x1p ** 2) / (rx ** 2) + (y1p ** 2) / (ry ** 2)
    if lam > 1:
        scale = math.sqrt(lam)
        rx *= scale
        ry *= scale

    sign = -1.0 if large_arc == sweep else 1.0
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    factor = 0.0 if den == 0 else sign * math.sqrt(max(0.0, num / den))

    cxp = factor * ((rx * y1p) / ry)
    cyp = factor * (-(ry * x1p) / rx)

    cx = cos_phi * cxp - sin_phi * cyp + (start.x + end.x) / 2.0
    cy = sin_phi * cxp + cos_phi * cyp + (start.y + end.y) / 2.0

    def angle(u: tuple[float, float], v: tuple[float, float]) -> float:
        dot = u[0] * v[0] + u[1] * v[1]
        length = math.hypot(u[0], u[1]) * math.hypot(v[0], v[1])
        if length == 0:
            return 0.0
        value = max(-1.0, min(1.0, dot / length))
        sign_local = 1.0 if u[0] * v[1] - u[1] * v[0] >= 0 else -1.0
        return sign_local * math.acos(value)

    u = ((x1p - cxp) / rx, (y1p - cyp) / ry)
    v = ((-x1p - cxp) / rx, (-y1p - cyp) / ry)

    theta1 = angle((1.0, 0.0), u)
    delta_theta = angle(u, v)

    if not sweep and delta_theta > 0:
        delta_theta -= 2.0 * math.pi
    elif sweep and delta_theta < 0:
        delta_theta += 2.0 * math.pi

    return Point(cx, cy), rx, ry, phi, theta1 + delta_theta


def arc_points(
    start: Point,
    rx: float,
    ry: float,
    rotation: float,
    large_arc: float,
    sweep: float,
    end: Point,
    steps: int,
) -> list[Point]:
    if rx == 0 or ry == 0:
        return [start, end]

    phi = math.radians(rotation % 360.0)
    cos_phi = math.cos(phi)
    sin_phi = math.sin(phi)

    center, rx, ry, _, theta2 = arc_to_center(start, rx, ry, rotation, large_arc, sweep, end)
    cx = center.x
    cy = center.y

    dx2 = (start.x - end.x) / 2.0
    dy2 = (start.y - end.y) / 2.0
    x1p = cos_phi * dx2 + sin_phi * dy2
    y1p = -sin_phi * dx2 + cos_phi * dy2

    sign = -1.0 if large_arc == sweep else 1.0
    num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2
    den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
    factor = 0.0 if den == 0 else sign * math.sqrt(max(0.0, num / den))
    cxp = factor * ((rx * y1p) / ry)
    cyp = factor * (-(ry * x1p) / rx)

    u = ((x1p - cxp) / rx, (y1p - cyp) / ry)
    v = ((-x1p - cxp) / rx, (-y1p - cyp) / ry)

    def angle(u_vec: tuple[float, float], v_vec: tuple[float, float]) -> float:
        dot = u_vec[0] * v_vec[0] + u_vec[1] * v_vec[1]
        length = math.hypot(u_vec[0], u_vec[1]) * math.hypot(v_vec[0], v_vec[1])
        if length == 0:
            return 0.0
        value = max(-1.0, min(1.0, dot / length))
        sign_local = 1.0 if u_vec[0] * v_vec[1] - u_vec[1] * v_vec[0] >= 0 else -1.0
        return sign_local * math.acos(value)

    theta1 = angle((1.0, 0.0), u)
    delta_theta = angle(u, v)
    if not sweep and delta_theta > 0:
        delta_theta -= 2.0 * math.pi
    elif sweep and delta_theta < 0:
        delta_theta += 2.0 * math.pi

    points = []
    for i in range(steps + 1):
        t = i / steps
        theta = theta1 + delta_theta * t
        x = cx + rx * math.cos(theta) * cos_phi - ry * math.sin(theta) * sin_phi
        y = cy + rx * math.cos(theta) * sin_phi + ry * math.sin(theta) * cos_phi
        points.append(Point(x, y))

    points[0] = start
    points[-1] = end
    return points


def flatten_path(d: str, curve_steps: int) -> list[Segment]:
    tokens = COMMAND_RE.findall(d)
    index = 0
    command = ""
    current = Point(0.0, 0.0)
    start = Point(0.0, 0.0)
    last_control: Point | None = None
    segments: list[Segment] = []

    def has_more() -> bool:
        return index < len(tokens)

    def next_number() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    while has_more():
        token = tokens[index]
        if re.fullmatch(r"[AaCcHhLlMmQqSsTtVvZz]", token):
            command = token
            index += 1
        elif not command:
            raise ValueError("Path data starts with numbers before a command")

        lower = command.lower()
        relative = command.islower()

        if lower == "m":
            x = next_number()
            y = next_number()
            if relative:
                current = Point(current.x + x, current.y + y)
            else:
                current = Point(x, y)
            start = current
            last_control = None
            command = "l" if relative else "L"
            while has_more() and not re.fullmatch(r"[AaCcHhLlMmQqSsTtVvZz]", tokens[index]):
                x = next_number()
                y = next_number()
                end = Point(current.x + x, current.y + y) if relative else Point(x, y)
                segments.append(Segment(current, end))
                current = end
        elif lower == "l":
            while has_more() and not re.fullmatch(r"[AaCcHhLlMmQqSsTtVvZz]", tokens[index]):
                x = next_number()
                y = next_number()
                end = Point(current.x + x, current.y + y) if relative else Point(x, y)
                segments.append(Segment(current, end))
                current = end
            last_control = None
        elif lower == "h":
            while has_more() and not re.fullmatch(r"[AaCcHhLlMmQqSsTtVvZz]", tokens[index]):
                x = next_number()
                end = Point(current.x + x, current.y) if relative else Point(x, current.y)
                segments.append(Segment(current, end))
                current = end
            last_control = None
        elif lower == "v":
            while has_more() and not re.fullmatch(r"[AaCcHhLlMmQqSsTtVvZz]", tokens[index]):
                y = next_number()
                end = Point(current.x, current.y + y) if relative else Point(current.x, y)
                segments.append(Segment(current, end))
                current = end
            last_control = None
        elif lower == "c":
            while has_more() and not re.fullmatch(r"[AaCcHhLlMmQqSsTtVvZz]", tokens[index]):
                x1 = next_number()
                y1 = next_number()
                x2 = next_number()
                y2 = next_number()
                x = next_number()
                y = next_number()
                c1 = Point(current.x + x1, current.y + y1) if relative else Point(x1, y1)
                c2 = Point(current.x + x2, current.y + y2) if relative else Point(x2, y2)
                end = Point(current.x + x, current.y + y) if relative else Point(x, y)
                prev = current
                for step in range(1, curve_steps + 1):
                    t = step / curve_steps
                    point = cubic_point(current, c1, c2, end, t)
                    segments.append(Segment(prev, point))
                    prev = point
                current = end
                last_control = c2
        elif lower == "s":
            while has_more() and not re.fullmatch(r"[AaCcHhLlMmQqSsTtVvZz]", tokens[index]):
                x2 = next_number()
                y2 = next_number()
                x = next_number()
                y = next_number()
                c1 = current if last_control is None else Point(2 * current.x - last_control.x, 2 * current.y - last_control.y)
                c2 = Point(current.x + x2, current.y + y2) if relative else Point(x2, y2)
                end = Point(current.x + x, current.y + y) if relative else Point(x, y)
                prev = current
                for step in range(1, curve_steps + 1):
                    t = step / curve_steps
                    point = cubic_point(current, c1, c2, end, t)
                    segments.append(Segment(prev, point))
                    prev = point
                current = end
                last_control = c2
        elif lower == "q":
            while has_more() and not re.fullmatch(r"[AaCcHhLlMmQqSsTtVvZz]", tokens[index]):
                x1 = next_number()
                y1 = next_number()
                x = next_number()
                y = next_number()
                c1 = Point(current.x + x1, current.y + y1) if relative else Point(x1, y1)
                end = Point(current.x + x, current.y + y) if relative else Point(x, y)
                prev = current
                for step in range(1, curve_steps + 1):
                    t = step / curve_steps
                    point = quadratic_point(current, c1, end, t)
                    segments.append(Segment(prev, point))
                    prev = point
                current = end
                last_control = c1
        elif lower == "t":
            while has_more() and not re.fullmatch(r"[AaCcHhLlMmQqSsTtVvZz]", tokens[index]):
                x = next_number()
                y = next_number()
                c1 = current if last_control is None else Point(2 * current.x - last_control.x, 2 * current.y - last_control.y)
                end = Point(current.x + x, current.y + y) if relative else Point(x, y)
                prev = current
                for step in range(1, curve_steps + 1):
                    t = step / curve_steps
                    point = quadratic_point(current, c1, end, t)
                    segments.append(Segment(prev, point))
                    prev = point
                current = end
                last_control = c1
        elif lower == "a":
            while has_more() and not re.fullmatch(r"[AaCcHhLlMmQqSsTtVvZz]", tokens[index]):
                rx = next_number()
                ry = next_number()
                rotation = next_number()
                large_arc = next_number()
                sweep = next_number()
                x = next_number()
                y = next_number()
                end = Point(current.x + x, current.y + y) if relative else Point(x, y)
                points = arc_points(current, rx, ry, rotation, large_arc, sweep, end, curve_steps)
                for i in range(1, len(points)):
                    segments.append(Segment(points[i - 1], points[i]))
                current = end
                last_control = None
        elif lower == "z":
            if distance(current, start) > 0:
                segments.append(Segment(current, start))
            current = start
            last_control = None
        else:
            raise ValueError(f"Unsupported path command: {command}")

    return segments


def parse_points(value: str) -> list[Point]:
    numbers = [float(part) for part in re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", value)]
    if len(numbers) % 2 != 0:
        raise ValueError("Point list must contain x/y pairs")
    return [Point(numbers[i], numbers[i + 1]) for i in range(0, len(numbers), 2)]


def flatten_element(element: ET.Element, curve_steps: int) -> list[Segment]:
    tag = strip_ns(element.tag)

    if tag == "path":
        return flatten_path(element.attrib.get("d", ""), curve_steps)
    if tag == "line":
        return [
            Segment(
                Point(float(element.attrib.get("x1", "0")), float(element.attrib.get("y1", "0"))),
                Point(float(element.attrib.get("x2", "0")), float(element.attrib.get("y2", "0"))),
            )
        ]
    if tag in {"polyline", "polygon"}:
        points = parse_points(element.attrib.get("points", ""))
        segments = [Segment(points[i], points[i + 1]) for i in range(len(points) - 1)]
        if tag == "polygon" and len(points) > 1:
            segments.append(Segment(points[-1], points[0]))
        return segments
    if tag == "rect":
        x = float(element.attrib.get("x", "0"))
        y = float(element.attrib.get("y", "0"))
        width = float(element.attrib.get("width", "0"))
        height = float(element.attrib.get("height", "0"))
        p0 = Point(x, y)
        p1 = Point(x + width, y)
        p2 = Point(x + width, y + height)
        p3 = Point(x, y + height)
        return [Segment(p0, p1), Segment(p1, p2), Segment(p2, p3), Segment(p3, p0)]
    if tag == "circle":
        cx = float(element.attrib.get("cx", "0"))
        cy = float(element.attrib.get("cy", "0"))
        r = float(element.attrib.get("r", "0"))
        return flatten_ellipse(cx, cy, r, r, curve_steps)
    if tag == "ellipse":
        cx = float(element.attrib.get("cx", "0"))
        cy = float(element.attrib.get("cy", "0"))
        rx = float(element.attrib.get("rx", "0"))
        ry = float(element.attrib.get("ry", "0"))
        return flatten_ellipse(cx, cy, rx, ry, curve_steps)
    return []


def flatten_ellipse(cx: float, cy: float, rx: float, ry: float, steps: int) -> list[Segment]:
    points = []
    for i in range(steps):
        angle = 2.0 * math.pi * i / steps
        points.append(Point(cx + rx * math.cos(angle), cy + ry * math.sin(angle)))
    return [Segment(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]


def collect_segments(root: ET.Element, curve_steps: int) -> list[Segment]:
    segments: list[Segment] = []
    for element in root.iter():
        segments.extend(flatten_element(element, curve_steps))
    return [segment for segment in segments if distance(segment.start, segment.end) > 1e-9]


def normalize_segments(
    segments: list[Segment],
    brightness: int,
    target_width: int,
    target_height: int,
    margin: float,
    min_length: float,
) -> tuple[list[list[int]], dict[str, int]]:
    points = [segment.start for segment in segments] + [segment.end for segment in segments]
    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)
    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)

    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    scale = min((target_width * (1.0 - margin)) / width, (target_height * (1.0 - margin)) / height)

    cx = (min_x + max_x) / 2.0
    cy = (min_y + max_y) / 2.0

    normalized = []
    for segment in segments:
        x0 = int(round((segment.start.x - cx) * scale))
        y0 = int(round((cy - segment.start.y) * scale))
        x1 = int(round((segment.end.x - cx) * scale))
        y1 = int(round((cy - segment.end.y) * scale))
        if math.hypot(x1 - x0, y1 - y0) < min_length:
            continue
        normalized.append([x0, y0, x1, y1, brightness])

    if not normalized:
        raise ValueError("No drawable segments were produced from the SVG")

    bounds = {
        "min_x": min(min(line[0], line[2]) for line in normalized),
        "max_x": max(max(line[0], line[2]) for line in normalized),
        "min_y": min(min(line[1], line[3]) for line in normalized),
        "max_y": max(max(line[1], line[3]) for line in normalized),
    }

    return normalized, bounds


def header_text(lines: list[list[int]]) -> str:
    line_rows = ",\n".join(f"  {{{x0}, {y0}, {x1}, {y1}, {brightness}}}" for x0, y0, x1, y1, brightness in lines)
    return "\n".join([
        "#ifndef LOGO_SEGMENTS_H",
        "#define LOGO_SEGMENTS_H",
        "",
        "#include <stdint.h>",
        "",
        "typedef struct LogoLine {",
        "  int16_t x0;",
        "  int16_t y0;",
        "  int16_t x1;",
        "  int16_t y1;",
        "  uint8_t brightness;",
        "} LogoLine;",
        "",
        "static const LogoLine kLogoLines[] = {",
        line_rows,
        "};",
        "",
        "static const uint16_t kLogoLineCount = sizeof(kLogoLines) / sizeof(kLogoLines[0]);",
        "",
        "#endif",
        "",
    ])


def preview_svg_text(lines: list[list[int]], width: int = 240, height: int = 320) -> str:
    margin = 24.0
    usable_width = width - 2.0 * margin
    usable_height = height - 2.0 * margin
    all_x = [value for line in lines for value in (line[0], line[2])]
    all_y = [value for line in lines for value in (line[1], line[3])]
    min_x = min(all_x)
    max_x = max(all_x)
    min_y = min(all_y)
    max_y = max(all_y)
    dx = max(max_x - min_x, 1)
    dy = max(max_y - min_y, 1)
    scale = min(usable_width / dx, usable_height / dy)

    def map_x(x: int) -> float:
        return margin + (x - min_x) * scale

    def map_y(y: int) -> float:
        return height - (margin + (y - min_y) * scale)

    svg_lines = []
    for x0, y0, x1, y1, _ in lines:
        svg_lines.append(
            f'    <line x1="{map_x(x0):.2f}" y1="{map_y(y0):.2f}" x2="{map_x(x1):.2f}" y2="{map_y(y1):.2f}" />'
        )

    return "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        '  <rect width="100%" height="100%" fill="#08110a"/>',
        '  <g stroke="#9cff9c" stroke-width="2" fill="none" stroke-linecap="round">',
        *svg_lines,
        '  </g>',
        '</svg>',
        '',
    ])


def convert_svg(
    input_svg: Path,
    brightness: int,
    curve_steps: int,
    target_width: int,
    target_height: int,
    margin: float,
    min_length: float,
) -> tuple[list[list[int]], dict[str, int]]:
    tree = ET.parse(input_svg)
    segments = collect_segments(tree.getroot(), curve_steps)
    return normalize_segments(segments, brightness, target_width, target_height, margin, min_length)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_svg", type=Path)
    parser.add_argument("--header", type=Path, default=Path("generated/logo_segments.h"))
    parser.add_argument("--json", type=Path, default=Path("generated/logo_segments.json"))
    parser.add_argument("--preview", type=Path, default=Path("generated/logo_preview.svg"))
    parser.add_argument("--brightness", type=int, default=96)
    parser.add_argument("--curve-steps", type=int, default=16)
    parser.add_argument("--target-width", type=int, default=30000)
    parser.add_argument("--target-height", type=int, default=42000)
    parser.add_argument("--margin", type=float, default=0.1, help="Fractional margin inside target bounds")
    parser.add_argument("--min-length", type=float, default=6.0, help="Drop tiny segments after scaling")
    args = parser.parse_args(argv)

    lines, bounds = convert_svg(
        args.input_svg,
        args.brightness,
        args.curve_steps,
        args.target_width,
        args.target_height,
        args.margin,
        args.min_length,
    )

    payload = {
        "source": str(args.input_svg),
        "line_count": len(lines),
        "bounds": bounds,
        "lines": lines,
    }

    for path in (args.header, args.json, args.preview):
        path.parent.mkdir(parents=True, exist_ok=True)

    args.header.write_text(header_text(lines), encoding="utf-8")
    args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    args.preview.write_text(preview_svg_text(lines), encoding="utf-8")

    print(f"Converted {args.input_svg} into {len(lines)} line segments.")
    print(f"Header:  {args.header}")
    print(f"JSON:    {args.json}")
    print(f"Preview: {args.preview}")
    print(f"Bounds:  {bounds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
