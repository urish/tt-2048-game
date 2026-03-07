/*
 * Copyright (c) 2024 Uri Shaked
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module game_row_push_merge (
    input  wire [15:0] row,         // 4x4 grid row input
    input  wire        push_right,  // 0 to push left, 1 to push right
    output reg  [15:0] result_row,  // Processed output row
    output reg  [7:0]  source_disp  // Per-cell displacement (4 cells x 2 bits)
);

  reg [3:0] result_0, result_1, result_2, result_3;
  reg merged_0;
  reg merged_1;
  reg [3:0] value;
  integer i, j;
  reg [1:0] disp_0, disp_1, disp_2, disp_3;
  reg [1:0] disp_val, phys_col;

  always @(*) begin
    // Initialize result cells to 0
    result_0 = 4'b0000;
    result_1 = 4'b0000;
    result_2 = 4'b0000;
    result_3 = 4'b0000;
    merged_0 = 1'b0;
    merged_1 = 1'b0;
    disp_0 = 2'd0;
    disp_1 = 2'd0;
    disp_2 = 2'd0;
    disp_3 = 2'd0;

    j = 0;  // Index to track the current position in the result

    // Process each cell in the row
    for (i = 0; i < 4; i = i + 1) begin
      value = push_right ? row[15-i*4-:4] : row[i*4+:4];  // Extract each 4-bit cell

      if (value != 4'b0000) begin
        case (j)
          0: result_0 = value;
          1: begin
            if (value == result_0 && !merged_0) begin
              result_0 = result_0 + 1;  // Merge with the previous value
              j = j - 1;  // Reduce j as the merge took place
              merged_0 = 1'b1;
            end else begin
              result_1 = value;
            end
          end
          2: begin
            if (value == result_1 && !merged_1) begin
              result_1 = result_1 + 1;  // Merge with the previous value
              j = j - 1;  // Reduce j as the merge took place
              merged_1 = 1'b1;
            end else begin
              result_2 = value;
            end
          end
          3: begin
            if (value == result_2) begin
              result_2 = result_2 + 1;  // Merge with the previous value
              j = j - 1;  // Reduce j as the merge took place
            end else begin
              result_3 = value;
            end
          end
        endcase
        // Track per-cell displacement: how far this cell moved
        disp_val = i[1:0] - j[1:0];
        phys_col = push_right ? (2'd3 - i[1:0]) : i[1:0];
        case (phys_col)
          2'd0: disp_0 = disp_val;
          2'd1: disp_1 = disp_val;
          2'd2: disp_2 = disp_val;
          2'd3: disp_3 = disp_val;
        endcase

        j = j + 1;
      end
    end

    // Combine result cells into a single 16-bit value
    result_row = push_right ? {result_0, result_1, result_2, result_3} : {result_3, result_2, result_1, result_0};
    source_disp = {disp_3, disp_2, disp_1, disp_0};
  end

endmodule
