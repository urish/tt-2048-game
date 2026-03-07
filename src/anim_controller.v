/*
 * Copyright (c) 2024 Uri Shaked
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module anim_controller (
    input wire       clk,
    input wire       rst_n,
    input wire       vsync_rising_edge,
    input wire       btn_up,
    input wire       btn_down,
    input wire       btn_left,
    input wire       btn_right,
    input wire       enable,
    input wire [63:0] grid,
    input wire [63:0] next_grid,
    output reg       animating,
    output reg [1:0] anim_dir,
    output wire [5:0] anim_offset,
    output wire      anim_done
);

  reg [3:0] anim_counter;

  assign anim_offset = {anim_counter, 2'b00};
  assign anim_done = animating && vsync_rising_edge && (anim_counter == 4'd15);

  wire any_btn = btn_up || btn_down || btn_left || btn_right;

  always @(posedge clk) begin
    if (~rst_n) begin
      animating <= 1'b0;
      anim_dir <= 2'd0;
      anim_counter <= 4'd0;
    end else begin
      if (!animating && enable && any_btn) begin
        animating <= 1'b1;
        anim_counter <= 4'd1;
        if (btn_left)       anim_dir <= 2'd0;
        else if (btn_right) anim_dir <= 2'd1;
        else if (btn_up)    anim_dir <= 2'd2;
        else                anim_dir <= 2'd3;
      end else if (animating && vsync_rising_edge) begin
        if (anim_counter == 4'd15 || grid == next_grid) begin
          animating <= 1'b0;
          anim_counter <= 4'd0;
        end else begin
          anim_counter <= anim_counter + 4'd1;
        end
      end
    end
  end

endmodule
