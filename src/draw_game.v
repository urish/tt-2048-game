/*
 * Copyright (c) 2024 Uri Shaked
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module draw_game (
    input wire [63:0] grid,
    input wire [15:0] new_tiles,
    input wire [2:0] new_tiles_counter,
    input wire [9:0] x,
    input wire [9:0] y,
    input wire retro_colors,
    input wire debug_mode,
    input wire       anim_active,
    input wire [1:0] anim_dir,
    input wire [5:0] anim_offset,
    input wire [31:0] disp_map,
    output reg [5:0] rrggbb
);

  localparam CELL_SIZE = 64;
  localparam BOARD_X_POS = 192;
  localparam BOARD_Y_POS = 128;
  localparam BOARD_WIDTH = CELL_SIZE * 4;
  localparam BOARD_HEIGHT = CELL_SIZE * 4;
  localparam BOARD_X_RIGHT = BOARD_X_POS + BOARD_WIDTH;
  localparam BOARD_Y_BOTTOM = BOARD_Y_POS + BOARD_HEIGHT;

  wire [5:0] color_font = retro_colors ? 6'b101110 : 6'b001111;
  wire [5:0] color_bg = retro_colors ? {3'b000, x[0], 2'b00} : 6'd0;
  wire [5:0] color_outline = retro_colors ? 6'b001000 : 6'b111111;

  wire [9:0] board_x = x - BOARD_X_POS;
  wire [9:0] board_y = y - BOARD_Y_POS;

  // Animation axis parameters
  wire horizontal = (anim_dir == 2'd0 || anim_dir == 2'd1);
  wire shift_neg  = (anim_dir == 2'd0 || anim_dir == 2'd2);

  wire [7:0] par_coord = horizontal ? board_x[7:0] : board_y[7:0];
  wire [1:0] perp_idx  = horizontal ? board_y[7:6] : board_x[7:6];
  wire [5:0] perp_sub  = horizontal ? board_y[5:0] : board_x[5:0];

  // Precompute offset multiples (anim_offset * 1/2/3)
  wire [7:0] ofs_1x = {2'b0, anim_offset};
  wire [7:0] ofs_2x = {1'b0, anim_offset, 1'b0};
  wire [7:0] ofs_3x = ofs_1x + ofs_2x;

  // Extract 4 displacements and 4 grid values along animation axis
  reg [1:0] d0, d1, d2, d3;
  reg [3:0] v0, v1, v2, v3;

  always @(*) begin
    case ({horizontal, perp_idx})
      3'b100: begin
        {d3, d2, d1, d0} = disp_map[7:0];
        v0 = grid[3:0]; v1 = grid[7:4]; v2 = grid[11:8]; v3 = grid[15:12];
      end
      3'b101: begin
        {d3, d2, d1, d0} = disp_map[15:8];
        v0 = grid[19:16]; v1 = grid[23:20]; v2 = grid[27:24]; v3 = grid[31:28];
      end
      3'b110: begin
        {d3, d2, d1, d0} = disp_map[23:16];
        v0 = grid[35:32]; v1 = grid[39:36]; v2 = grid[43:40]; v3 = grid[47:44];
      end
      3'b111: begin
        {d3, d2, d1, d0} = disp_map[31:24];
        v0 = grid[51:48]; v1 = grid[55:52]; v2 = grid[59:56]; v3 = grid[63:60];
      end
      3'b000: begin
        d0 = disp_map[1:0]; d1 = disp_map[9:8]; d2 = disp_map[17:16]; d3 = disp_map[25:24];
        v0 = grid[3:0]; v1 = grid[19:16]; v2 = grid[35:32]; v3 = grid[51:48];
      end
      3'b001: begin
        d0 = disp_map[3:2]; d1 = disp_map[11:10]; d2 = disp_map[19:18]; d3 = disp_map[27:26];
        v0 = grid[7:4]; v1 = grid[23:20]; v2 = grid[39:36]; v3 = grid[55:52];
      end
      3'b010: begin
        d0 = disp_map[5:4]; d1 = disp_map[13:12]; d2 = disp_map[21:20]; d3 = disp_map[29:28];
        v0 = grid[11:8]; v1 = grid[27:24]; v2 = grid[43:40]; v3 = grid[59:56];
      end
      3'b011: begin
        d0 = disp_map[7:6]; d1 = disp_map[15:14]; d2 = disp_map[23:22]; d3 = disp_map[31:30];
        v0 = grid[15:12]; v1 = grid[31:28]; v2 = grid[47:44]; v3 = grid[63:60];
      end
    endcase
  end

  // Per-cell pixel offsets: displacement * anim_offset
  reg [7:0] off0, off1, off2, off3;
  always @(*) begin
    case (d0) 2'd0: off0 = 8'd0; 2'd1: off0 = ofs_1x; 2'd2: off0 = ofs_2x; default: off0 = ofs_3x; endcase
    case (d1) 2'd0: off1 = 8'd0; 2'd1: off1 = ofs_1x; 2'd2: off1 = ofs_2x; default: off1 = ofs_3x; endcase
    case (d2) 2'd0: off2 = 8'd0; 2'd1: off2 = ofs_1x; 2'd2: off2 = ofs_2x; default: off2 = ofs_3x; endcase
    case (d3) 2'd0: off3 = 8'd0; 2'd1: off3 = ofs_1x; 2'd2: off3 = ofs_2x; default: off3 = ofs_3x; endcase
  end

  // Animated cell positions (9-bit to handle under/overflow)
  wire [8:0] pos0 = shift_neg ? (9'd0   - {1'b0, off0}) : (9'd0   + {1'b0, off0});
  wire [8:0] pos1 = shift_neg ? (9'd64  - {1'b0, off1}) : (9'd64  + {1'b0, off1});
  wire [8:0] pos2 = shift_neg ? (9'd128 - {1'b0, off2}) : (9'd128 + {1'b0, off2});
  wire [8:0] pos3 = shift_neg ? (9'd192 - {1'b0, off3}) : (9'd192 + {1'b0, off3});

  // Hit test: par_coord in [pos, pos+63] and cell non-empty
  wire [8:0] delta0 = {1'b0, par_coord} - pos0;
  wire [8:0] delta1 = {1'b0, par_coord} - pos1;
  wire [8:0] delta2 = {1'b0, par_coord} - pos2;
  wire [8:0] delta3 = {1'b0, par_coord} - pos3;

  wire hit0 = (delta0[8:6] == 3'b000) && (v0 != 4'd0);
  wire hit1 = (delta1[8:6] == 3'b000) && (v1 != 4'd0);
  wire hit2 = (delta2[8:6] == 3'b000) && (v2 != 4'd0);
  wire hit3 = (delta3[8:6] == 3'b000) && (v3 != 4'd0);

  reg [3:0] sel_val;
  reg [5:0] sel_sub_par;
  reg [1:0] sel_idx;

  always @(*) begin
    if (hit0)      begin sel_val = v0; sel_sub_par = delta0[5:0]; sel_idx = 2'd0; end
    else if (hit1) begin sel_val = v1; sel_sub_par = delta1[5:0]; sel_idx = 2'd1; end
    else if (hit2) begin sel_val = v2; sel_sub_par = delta2[5:0]; sel_idx = 2'd2; end
    else if (hit3) begin sel_val = v3; sel_sub_par = delta3[5:0]; sel_idx = 2'd3; end
    else           begin sel_val = 4'd0; sel_sub_par = 6'd0; sel_idx = 2'd0; end
  end

  // Mux between animated and static cell lookup
  wire [1:0] cell_x = anim_active ? (horizontal ? sel_idx  : perp_idx) : board_x[7:6];
  wire [1:0] cell_y = anim_active ? (horizontal ? perp_idx : sel_idx)  : board_y[7:6];
  wire [3:0] current_number = anim_active ? sel_val : grid[{board_y[7:6], board_x[7:6], 2'b00} +: 4];
  wire is_new_tile = new_tiles_counter > 0 && new_tiles[{cell_y, cell_x}];

  wire is_outline_x = (x % CELL_SIZE == 0 || x % CELL_SIZE == (CELL_SIZE - 1));
  wire is_outline_y = (y % CELL_SIZE == 0 || y % CELL_SIZE == (CELL_SIZE - 1));
  wire is_outline = is_outline_x || is_outline_y;

  wire [5:0] glyph_x = anim_active ? (horizontal ? sel_sub_par : perp_sub) : board_x[5:0];
  wire [5:0] glyph_y = anim_active ? (horizontal ? perp_sub : sel_sub_par) : board_y[5:0];

  wire pixel;
  draw_numbers draw_numbers_inst (
      .index(current_number),
      .x(glyph_x),
      .y(glyph_y),
      .pixel(pixel)
  );

  wire board_area = x >= BOARD_X_POS && y >= BOARD_Y_POS && x < BOARD_X_RIGHT && y < BOARD_Y_BOTTOM;
  wire [5:0] fade_font_color = 6'b001111 ^ {3'b0, new_tiles_counter};
  wire [5:0] draw_text = is_new_tile ? fade_font_color : color_font;
  wire [5:0] draw_board = is_outline ? color_outline : color_bg;

  wire debug_rect = x >= BOARD_X_POS - 64 && x < BOARD_X_RIGHT + 64 && y >= 16 && y < 32;

  always @(*) begin
    rrggbb = board_area ? pixel ? draw_text : draw_board : debug_mode && debug_rect ? x[8:3] : 6'b0;
  end

endmodule
