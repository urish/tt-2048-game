# VGA Simulator for Tiny Tapeout Projects

Simulates Verilog VGA projects using Verilator and captures frames as PNG images
or MP4 video. Reads project configuration from `info.yaml` and handles
compilation, simulation, and frame capture automatically.

## Requirements

- Python 3.10+
- [Verilator](https://www.veripool.org/verilator/) (runtime)
- [ffmpeg](https://ffmpeg.org/) (for `--video`)
- ImageMagick `convert` (optional, for faster PPM-to-PNG conversion)

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Single frame (welcome screen)
python vga_sim.py .

# 120 frames + MP4 video with input events from file
python vga_sim.py . -n 120 -d out --video output.mp4 -i events.yaml

# Inline input events
python vga_sim.py . -n 60 -e 2:1 4:0 25:4 27:0

# Custom video settings (30fps, 3x upscale)
python vga_sim.py -n 60 --video --fps 30 --scale 3 .

# Direct file mode (no info.yaml)
python vga_sim.py -f project.v -t tt_um_example
```

### Input events

Events set the `ui_in` value at specific frames. Two ways to specify them:

**File (`-i`)** - YAML mapping of `frame: ui_in_value`:

```yaml
# events.yaml
2: 1     # btn_up press
4: 0     # release
25: 4    # btn_left press
27: 0    # release
```

**Inline (`-e`)** - `FRAME:VALUE` pairs on the command line:

```bash
python vga_sim.py . -e 2:1 4:0 25:4 27:0
```

Both can be combined; inline events are appended to file events.
