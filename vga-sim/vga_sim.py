#!/usr/bin/env python3

# Copyright (C) 2026, Uri Shaked.
# SPDX-License-Identifier: Apache-2.0

"""
VGA Simulation Script for Tiny Tapeout Projects

Simulates Verilog VGA projects using Verilator and captures frames as PNG images.
Reads project configuration from info.yaml and handles compilation, simulation,
and frame capture automatically.

Usage:
    python vga_sim.py [options] <project_dir>
    python vga_sim.py [options] -f <verilog_files...>

Examples:
    # Simulate project from info.yaml
    python vga_sim.py /path/to/tt-project

    # Capture 10 frames
    python vga_sim.py -n 10 /path/to/tt-project

    # Direct file mode (no info.yaml)
    python vga_sim.py -f project.v hvsync_generator.v -t tt_um_example
"""

import argparse
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path
from string import Template

import yaml


# VGA timing constants (640x480 @ 60Hz)
H_DISPLAY = 640
H_FRONT = 16
H_SYNC = 96
H_BACK = 48
H_TOTAL = H_DISPLAY + H_FRONT + H_SYNC + H_BACK  # 800

V_DISPLAY = 480
V_BOTTOM = 10
V_SYNC = 2
V_TOP = 33
V_TOTAL = V_DISPLAY + V_BOTTOM + V_SYNC + V_TOP  # 525

# Verilator warning flags to suppress (common in Tiny Tapeout projects)
_VERILATOR_SUPPRESS = [
    "-Wno-UNUSEDSIGNAL",
    "-Wno-DECLFILENAME",
    "-Wno-WIDTH",
    "-Wno-CASEINCOMPLETE",
    "-Wno-TIMESCALEMOD",
    "-Wno-PINMISSING",
    "-Wno-fatal",
]

_TESTBENCH_TEMPLATE = Template("""\
// Auto-generated Verilator VGA testbench
#include <verilated.h>
#include "V${top_module}.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>

#define H_DISPLAY   ${h_display}
#define H_FRONT     ${h_front}
#define H_SYNC      ${h_sync}
#define H_BACK      ${h_back}
#define H_TOTAL     ${h_total}

#define V_DISPLAY   ${v_display}
#define V_BOTTOM    ${v_bottom}
#define V_SYNC      ${v_sync}
#define V_TOP       ${v_top}
#define V_TOTAL     ${v_total}

static uint8_t framebuffer[H_DISPLAY * V_DISPLAY * 3];

inline uint8_t extend2to8(uint8_t val) { return val * 85; }

void decode_vga(uint8_t uo_out, bool &hsync, bool &vsync, uint8_t &r, uint8_t &g, uint8_t &b) {
    hsync = (uo_out >> 7) & 1;
    vsync = (uo_out >> 3) & 1;
    r = ((uo_out & 0x01) << 1) | ((uo_out >> 4) & 0x01);
    g = ((uo_out & 0x02) >> 0) | ((uo_out >> 5) & 0x01);
    b = ((uo_out & 0x04) >> 1) | ((uo_out >> 6) & 0x01);
}

void save_ppm(const char *filename) {
    FILE *f = fopen(filename, "wb");
    if (!f) { fprintf(stderr, "Error: Cannot open %s\\n", filename); return; }
    fprintf(f, "P6\\n%d %d\\n255\\n", H_DISPLAY, V_DISPLAY);
    fwrite(framebuffer, 1, H_DISPLAY * V_DISPLAY * 3, f);
    fclose(f);
}

void clock_tick(V${top_module} *top) {
    top->clk = 0; top->eval();
    top->clk = 1; top->eval();
}

int main(int argc, char **argv) {
    int num_frames = 1;
    const char *output_prefix = "frame";
    if (argc > 1) num_frames = atoi(argv[1]);
    if (argc > 2) output_prefix = argv[2];

    Verilated::commandArgs(argc, argv);
    V${top_module} *top = new V${top_module};

    // Reset sequence
    top->clk = 0;
    top->rst_n = 0;
    top->ena = 1;
    top->ui_in = 0;
    top->uio_in = 0;

    for (int i = 0; i < 10; i++) clock_tick(top);
    top->rst_n = 1;

    bool hsync, vsync;
    uint8_t r, g, b;

    // Synchronize to frame start
    do { clock_tick(top); decode_vga(top->uo_out, hsync, vsync, r, g, b); } while (!vsync);
    do { clock_tick(top); decode_vga(top->uo_out, hsync, vsync, r, g, b); } while (vsync);
${event_init}
    // Capture frames
    for (int frame = 0; frame < num_frames; frame++) {
${event_apply}        memset(framebuffer, 0, sizeof(framebuffer));

        // Skip V_TOP lines (vertical back porch)
        for (int line = 0; line < V_TOP; line++)
            for (int px = 0; px < H_TOTAL; px++) clock_tick(top);

        // Capture V_DISPLAY lines
        for (int y = 0; y < V_DISPLAY; y++) {
            // Skip H_BACK pixels (horizontal back porch)
            for (int px = 0; px < H_BACK; px++) clock_tick(top);

            // Capture H_DISPLAY pixels
            for (int x = 0; x < H_DISPLAY; x++) {
                clock_tick(top);
                decode_vga(top->uo_out, hsync, vsync, r, g, b);
                int idx = (y * H_DISPLAY + x) * 3;
                framebuffer[idx] = extend2to8(r);
                framebuffer[idx + 1] = extend2to8(g);
                framebuffer[idx + 2] = extend2to8(b);
            }

            // Skip H_FRONT + H_SYNC pixels
            for (int px = 0; px < H_FRONT + H_SYNC; px++) clock_tick(top);
        }

        // Skip V_BOTTOM + V_SYNC lines
        for (int line = 0; line < V_BOTTOM + V_SYNC; line++)
            for (int px = 0; px < H_TOTAL; px++) clock_tick(top);

        // Save frame
        char filename[256];
        snprintf(filename, sizeof(filename), "%s_%04d.ppm", output_prefix, frame);
        save_ppm(filename);
        fprintf(stderr, "Saved %s\\n", filename);
    }

    top->final();
    delete top;
    return 0;
}
""")


class VgaSimError(Exception):
    """Error raised for expected failures during VGA simulation."""


# -- Testbench generation --


def generate_testbench(
    top_module: str, input_events: list[tuple[int, int]] | None = None
) -> str:
    """Generate C++ testbench code for Verilator.

    input_events: list of (frame_number, ui_in_value) pairs.
    At the start of each frame, ui_in is set to the most recent event value.
    """
    if input_events:
        event_entries = ", ".join("{%d, %d}" % (f, v) for f, v in sorted(input_events))
        event_init = """
    // Input event schedule
    struct InputEvent { int frame; uint8_t ui_in; };
    InputEvent events[] = { %s };
    int num_events = %d;
    int event_idx = 0;
""" % (
            event_entries,
            len(input_events),
        )
        event_apply = """
        // Apply input events
        while (event_idx < num_events && events[event_idx].frame <= frame) {
            top->ui_in = events[event_idx].ui_in;
            event_idx++;
        }
"""
    else:
        event_init = ""
        event_apply = ""

    return _TESTBENCH_TEMPLATE.substitute(
        top_module=top_module,
        h_display=H_DISPLAY,
        h_front=H_FRONT,
        h_sync=H_SYNC,
        h_back=H_BACK,
        h_total=H_TOTAL,
        v_display=V_DISPLAY,
        v_bottom=V_BOTTOM,
        v_sync=V_SYNC,
        v_top=V_TOP,
        v_total=V_TOTAL,
        event_init=event_init,
        event_apply=event_apply,
    )


# -- PNG conversion --


def write_png(path: Path, width: int, height: int, rgb_data: bytes) -> None:
    """Write a minimal PNG file from RGB data."""

    def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
        chunk_len = struct.pack(">I", len(data))
        chunk_crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        return chunk_len + chunk_type + data + chunk_crc

    row_size = width * 3
    raw = bytearray((row_size + 1) * height)
    for y in range(height):
        dst = y * (row_size + 1)
        raw[dst] = 0  # filter type: None
        raw[dst + 1 : dst + 1 + row_size] = rgb_data[y * row_size : (y + 1) * row_size]

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(
            png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        )
        f.write(png_chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(png_chunk(b"IEND", b""))


def ppm_to_png(ppm_path: Path, png_path: Path) -> bool:
    """Convert PPM to PNG using ImageMagick or Python fallback."""
    if shutil.which("convert"):
        result = subprocess.run(
            ["convert", str(ppm_path), str(png_path)], capture_output=True
        )
        if result.returncode == 0:
            return True

    try:
        with open(ppm_path, "rb") as f:
            magic = f.readline().strip()
            if magic != b"P6":
                return False
            line = f.readline()
            while line.startswith(b"#"):
                line = f.readline()
            width, height = map(int, line.split())
            f.readline()  # maxval
            pixels = f.read()

        write_png(png_path, width, height, pixels)
        return True
    except Exception as e:
        print(f"Warning: PNG conversion failed: {e}", file=sys.stderr)
        return False


# -- Video creation --


def create_video(
    frame_pattern: str,
    output_path: Path,
    fps: int = 60,
    scale: int = 2,
    verbose: bool = False,
) -> None:
    """Create MP4 video from PNG frames using ffmpeg."""
    if not shutil.which("ffmpeg"):
        raise VgaSimError("ffmpeg not found in PATH")

    ffmpeg_args = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        frame_pattern,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        f"scale={H_DISPLAY * scale}:{V_DISPLAY * scale}:flags=neighbor",
        str(output_path),
    ]

    if verbose:
        print(f"Running: {' '.join(ffmpeg_args)}", file=sys.stderr)

    result = subprocess.run(ffmpeg_args, capture_output=True, text=True)
    if result.returncode != 0:
        raise VgaSimError(f"ffmpeg failed:\n{result.stderr}")

    print(f"Created {output_path}")


# -- Project config --


def parse_info_yaml(yaml_path: Path) -> tuple[str, list[str], Path]:
    """Parse info.yaml and return (top_module, source_files, src_dir)."""
    with open(yaml_path) as f:
        info = yaml.safe_load(f)

    project = info.get("project", {})
    top_module = project.get("top_module", "tt_um_example")
    source_files = project.get("source_files", [])
    src_dir = yaml_path.parent / "src"

    return top_module, source_files, src_dir


# -- Verilator --


def compile_verilator(
    source_files: list[Path],
    top_module: str,
    build_dir: Path,
    input_events: list[tuple[int, int]] | None = None,
    verbose: bool = False,
) -> Path:
    """Compile Verilator simulation. Returns path to executable."""
    build_dir.mkdir(parents=True, exist_ok=True)

    tb_path = build_dir / "vga_tb.cpp"
    tb_path.write_text(generate_testbench(top_module, input_events=input_events))

    include_dirs = {src.parent for src in source_files}
    verilator_args = [
        "verilator",
        "--cc",
        "--exe",
        "--build",
        "-O3",
        "--x-assign",
        "fast",
        *_VERILATOR_SUPPRESS,
        "--top-module",
        top_module,
        "-Mdir",
        str(build_dir),
        "-o",
        "vga_sim",
        *[str(src) for src in source_files],
        str(tb_path),
        *[f"-I{d}" for d in include_dirs],
    ]

    if verbose:
        print(f"Running: {' '.join(verilator_args)}", file=sys.stderr)

    env = {**os.environ, "LC_ALL": "C"}
    result = subprocess.run(verilator_args, capture_output=True, text=True, env=env)

    if verbose and result.stderr.strip():
        print(result.stderr, file=sys.stderr)

    sim_executable = build_dir / "vga_sim"
    if not sim_executable.exists():
        detail = result.stderr.strip() or result.stdout.strip() or "(no output)"
        raise VgaSimError(f"Verilator compilation failed:\n{detail}")

    return sim_executable


def run_simulation(
    sim_executable: Path,
    num_frames: int,
    output_prefix: str,
    output_dir: Path,
    verbose: bool = False,
) -> list[Path]:
    """Run Verilator simulation. Returns list of PPM output files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_prefix
    output_path.parent.mkdir(parents=True, exist_ok=True)

    sim_args = [str(sim_executable), str(num_frames), str(output_path)]

    if verbose:
        print(f"Running: {' '.join(sim_args)}", file=sys.stderr)

    result = subprocess.run(sim_args, capture_output=True, text=True, cwd=output_dir)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        for line in result.stderr.splitlines():
            if line.strip():
                print(line, file=sys.stderr)

    ppm_files = [
        ppm
        for i in range(num_frames)
        if (ppm := output_dir / f"{output_prefix}_{i:04d}.ppm").exists()
    ]

    if not ppm_files:
        raise VgaSimError("Simulation produced no output frames")

    return ppm_files


# -- CLI helpers --


def parse_input_events(
    events_file: Path | None, inline_events: list[str] | None
) -> list[tuple[int, int]] | None:
    """Parse input events from file and/or inline arguments."""
    events: list[tuple[int, int]] | None = None

    if events_file:
        with open(events_file) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise VgaSimError("Events file must be a YAML mapping of frame: value")
        events = [(int(frame), int(value)) for frame, value in data.items()]

    if inline_events:
        if events is None:
            events = []
        for ev in inline_events:
            parts = ev.split(":")
            if len(parts) != 2:
                raise VgaSimError(f"Invalid event format '{ev}', expected FRAME:VALUE")
            events.append((int(parts[0]), int(parts[1])))

    return events


def resolve_source_files(
    project_dir: Path | None,
    files: list[Path] | None,
    top_module: str,
) -> tuple[list[Path], str]:
    """Resolve source files and top module from CLI args."""
    if files:
        return [f.resolve() for f in files], top_module

    if not project_dir:
        raise VgaSimError("Either project_dir or -f/--files is required")

    project_dir = project_dir.resolve()
    info_yaml = project_dir / "info.yaml"

    if not info_yaml.exists():
        raise VgaSimError(f"info.yaml not found in {project_dir}")

    top_module, src_names, src_dir = parse_info_yaml(info_yaml)

    if not src_dir.exists():
        raise VgaSimError(f"src directory not found: {src_dir}")

    source_files = []
    for name in src_names:
        src_path = src_dir / name
        if not src_path.exists():
            raise VgaSimError(f"Source file not found: {src_path}")
        source_files.append(src_path)

    return source_files, top_module


def convert_frames(ppm_files: list[Path], keep_ppm: bool) -> None:
    """Convert PPM frames to PNG (unless keep_ppm is set)."""
    if keep_ppm:
        for ppm_file in ppm_files:
            print(f"Created {ppm_file}")
        return

    for ppm_file in ppm_files:
        png_file = ppm_file.with_suffix(".png")
        if ppm_to_png(ppm_file, png_file):
            ppm_file.unlink()
            print(f"Created {png_file}")
        else:
            print(f"Warning: Could not convert {ppm_file} to PNG")


# -- Main --


def main() -> None:
    parser = argparse.ArgumentParser(
        description="VGA Simulation for Tiny Tapeout Projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/tt-project                        # Single frame
  %(prog)s -n 120 --video /path/to/tt-project         # 120 frames + MP4 video
  %(prog)s -n 60 --video out.mp4 --fps 30 .           # Custom filename and fps
  %(prog)s -f project.v hvsync_generator.v             # Direct file mode
""",
    )

    parser.add_argument(
        "project_dir",
        nargs="?",
        type=Path,
        help="Project directory containing info.yaml",
    )
    parser.add_argument(
        "-f",
        "--files",
        nargs="+",
        type=Path,
        metavar="FILE",
        help="Verilog source files (direct mode, no info.yaml)",
    )
    parser.add_argument(
        "-t",
        "--top-module",
        default="tt_um_vga_example",
        help="Top module name (default: tt_um_vga_example)",
    )
    parser.add_argument(
        "-n",
        "--num-frames",
        type=int,
        default=1,
        help="Number of frames to capture (default: 1)",
    )
    parser.add_argument(
        "-o", "--output", default="frame", help="Output file prefix (default: frame)"
    )
    parser.add_argument(
        "-d",
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "--keep-ppm",
        action="store_true",
        help="Keep PPM files instead of converting to PNG",
    )
    parser.add_argument(
        "--build-dir", type=Path, help="Build directory (default: temp directory)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument(
        "-c",
        "--clean",
        action="store_true",
        help="Clean build directory before building",
    )
    parser.add_argument(
        "-e",
        "--input-events",
        nargs="+",
        metavar="FRAME:VALUE",
        help="Input events as frame:ui_in_value pairs (e.g., 2:1 4:0)",
    )
    parser.add_argument(
        "-i",
        "--events-file",
        type=Path,
        metavar="FILE",
        help="YAML file with input events (frame: ui_in_value mapping)",
    )
    parser.add_argument(
        "--video",
        nargs="?",
        const="output.mp4",
        metavar="FILE",
        help="Create MP4 video from captured frames (default: output.mp4)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=60,
        help="Video frame rate (default: 60)",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=2,
        help="Video upscale factor using nearest-neighbor (default: 2)",
    )

    args = parser.parse_args()

    if not args.files and not args.project_dir:
        parser.print_help()
        sys.exit(1)

    try:
        input_events = parse_input_events(args.events_file, args.input_events)
        source_files, top_module = resolve_source_files(
            args.project_dir, args.files, args.top_module
        )

        if args.verbose:
            print(f"Top module: {top_module}", file=sys.stderr)
            print("Source files:", file=sys.stderr)
            for src in source_files:
                print(f"  {src}", file=sys.stderr)

        if args.build_dir:
            build_dir = args.build_dir.resolve()
        else:
            build_dir = Path(tempfile.gettempdir()) / f"vga_sim_{top_module}"

        if args.clean and build_dir.exists():
            shutil.rmtree(build_dir)
            if args.verbose:
                print(f"Cleaned build directory: {build_dir}", file=sys.stderr)

        sim_executable = compile_verilator(
            source_files, top_module, build_dir, input_events, args.verbose
        )
        ppm_files = run_simulation(
            sim_executable,
            args.num_frames,
            args.output,
            args.output_dir.resolve(),
            args.verbose,
        )

        convert_frames(ppm_files, args.keep_ppm)
        print(f"Done! Generated {len(ppm_files)} frame(s)")

        if args.video:
            output_dir = args.output_dir.resolve()
            frame_pattern = str(output_dir / f"{args.output}_%04d.png")
            video_path = output_dir / args.video
            create_video(
                frame_pattern,
                video_path,
                fps=args.fps,
                scale=args.scale,
                verbose=args.verbose,
            )

    except VgaSimError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
