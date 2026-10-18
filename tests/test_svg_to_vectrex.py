import tempfile
import textwrap
import unittest
from pathlib import Path

from tools.build_native_vectrex import make_native_lines, split_polylines
from tools.svg_to_vectrex import convert_svg, flatten_path


class SvgToVectrexTests(unittest.TestCase):
    def test_path_close_generates_segments(self) -> None:
        segments = flatten_path("M 0 0 L 10 0 L 10 10 Z", curve_steps=8)
        self.assertEqual(len(segments), 3)

    def test_convert_simple_svg(self) -> None:
        svg = textwrap.dedent(
            """\
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">
              <g fill="none" stroke="#000">
                <path d="M30 160 L100 30 L170 160 Z"/>
                <line x1="62" y1="112" x2="138" y2="112"/>
              </g>
            </svg>
            """
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "logo.svg"
            path.write_text(svg, encoding="utf-8")
            lines, bounds = convert_svg(
                path,
                brightness=96,
                curve_steps=12,
                target_width=30000,
                target_height=42000,
                margin=0.1,
                min_length=1.0,
            )

        self.assertEqual(len(lines), 4)
        self.assertLess(bounds["min_x"], 0)
        self.assertGreater(bounds["max_x"], 0)
        self.assertLess(bounds["min_y"], 0)
        self.assertGreater(bounds["max_y"], 0)

    def test_circle_becomes_many_segments(self) -> None:
        svg = '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="30" /></svg>'
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "circle.svg"
            path.write_text(svg, encoding="utf-8")
            lines, _ = convert_svg(
                path,
                brightness=80,
                curve_steps=10,
                target_width=20000,
                target_height=20000,
                margin=0.0,
                min_length=1.0,
            )

        self.assertEqual(len(lines), 10)

    def test_native_lines_fit_signed_byte_range(self) -> None:
        svg = Path("assets/logo.svg")
        lines, _ = convert_svg(
            svg,
            brightness=96,
            curve_steps=16,
            target_width=30000,
            target_height=42000,
            margin=0.1,
            min_length=1.0,
        )
        native_lines = make_native_lines(lines)

        for row in native_lines:
            for value in row:
                self.assertGreaterEqual(value, -127)
                self.assertLessEqual(value, 127)

    def test_real_hardware_renderer_splits_disconnected_objects(self) -> None:
        svg = Path("assets/logo.svg")
        lines, _ = convert_svg(
            svg,
            brightness=96,
            curve_steps=16,
            target_width=30000,
            target_height=42000,
            margin=0.1,
            min_length=1.0,
        )
        native_lines = make_native_lines(lines)
        polylines = split_polylines(native_lines)

        self.assertGreater(len(polylines), 1)
        self.assertEqual(sum(len(polyline) for polyline in polylines), len(native_lines))


if __name__ == "__main__":
    unittest.main()
