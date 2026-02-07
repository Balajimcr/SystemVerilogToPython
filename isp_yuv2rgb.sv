// ============================================================================
// ISP YUV → RGB Constraint Model (Solver-Stable, Range-Complete)
// ============================================================================

typedef enum int {
    YUV_444 = 0,
    YUV_422 = 1,
    YUV_420 = 2
} yuv_format_e;

typedef enum int {
    COMP_RGB = 0,
    COMP_YUV = 1,
    COMP_RAW = 2
} comp_type_e;

typedef enum int {
    BIT_8  = 0,
    BIT_10 = 1,
    BIT_12 = 3
} bit_depth_e;


// ============================================================================
// Main Randomizable Configuration Class
// ============================================================================

class isp_rand_item;

    // ------------------------------------------------------------------------
    // Primary selector fields
    // ------------------------------------------------------------------------
    rand bit            isp_bypass_mode;
    rand yuv_format_e   isp_yuv_format;
    rand comp_type_e    isp_src_comp;
    rand comp_type_e    isp_dst_comp;
    rand bit_depth_e    isp_in_bit_depth;
    rand bit_depth_e    isp_out_bit_depth;

    // ------------------------------------------------------------------------
    // DMA / format selectors (previously unbounded → BUG)
    // ------------------------------------------------------------------------
    rand int unsigned   rdma_data_format;
    rand int unsigned   wdma_data_format;

    // ------------------------------------------------------------------------
    // Signed grid parameters
    // ------------------------------------------------------------------------
    rand int signed     isp_grid_2d_0_0;
    rand int signed     isp_grid_2d_0_1;
    rand int signed     isp_grid_2d_0_2;
    rand int signed     isp_grid_2d_0_3;
    rand int signed     isp_grid_2d_0_4;
    rand int signed     isp_grid_2d_0_6;


    // ========================================================================
    // GLOBAL SOLVE ORDER (acyclic, selector-only)
    // ========================================================================
    constraint solve_order_c {
        solve isp_bypass_mode  before isp_yuv_format;
        solve isp_yuv_format   before isp_src_comp;
        solve isp_src_comp     before isp_dst_comp;
        solve isp_dst_comp     before isp_in_bit_depth;
        solve isp_in_bit_depth before isp_out_bit_depth;
    }


    // ========================================================================
    // ENUM / BIT RANGE CONSTRAINTS (explicit, redundant-safe)
    // ========================================================================
    constraint enum_ranges_c {
        isp_bypass_mode inside {0,1};

        isp_yuv_format inside {YUV_444, YUV_422, YUV_420};

        isp_src_comp inside {COMP_RGB, COMP_YUV, COMP_RAW};
        isp_dst_comp inside {COMP_RGB, COMP_YUV, COMP_RAW};

        isp_in_bit_depth  inside {BIT_8, BIT_10, BIT_12};
        isp_out_bit_depth inside {BIT_8, BIT_10, BIT_12};
    }


    // ========================================================================
    // DMA FORMAT RANGE CONSTRAINTS
    // ========================================================================
    constraint dma_format_range_c {

        // RDMA formats supported by HW
        rdma_data_format inside {
            4, 5,
            7, 8,
            16, 17,
            20, 21,
            32, 33
        };

        // WDMA formats (kept generic but bounded)
        wdma_data_format inside {[0:63]};
    }


    // ========================================================================
    // RDMA → YUV FORMAT RELATION
    // ========================================================================
    constraint rdma_format_c {

        if (rdma_data_format inside {4,5,16,17,20,21})
            isp_yuv_format == YUV_444;
        else
            isp_yuv_format inside {YUV_422, YUV_420};
    }


    // ========================================================================
    // BYPASS MODE CONSTRAINTS
    // ========================================================================
    constraint bypass_mode_c {

        if (isp_bypass_mode) {
            isp_src_comp inside {COMP_RGB, COMP_YUV};
            isp_dst_comp == isp_src_comp;
        }
    }


    // ========================================================================
    // INPUT BIT-DEPTH DERIVATION FROM RDMA FORMAT
    // ========================================================================
    constraint input_bit_depth_c {

        if (rdma_data_format inside {4,5,7,8})
            isp_in_bit_depth == BIT_8;
        else if (rdma_data_format inside {16,17,32,33})
            isp_in_bit_depth == BIT_10;
        else
            isp_in_bit_depth == BIT_12;
    }


    // ========================================================================
    // OUTPUT BIT-DEPTH RULES
    // ========================================================================
    constraint output_bit_depth_c {

        if (isp_in_bit_depth == BIT_8)
            isp_out_bit_depth == BIT_8;
        else if (isp_dst_comp != COMP_RGB)
            isp_out_bit_depth == BIT_10;
        else
            isp_out_bit_depth inside {BIT_10, BIT_12};
    }


    // ========================================================================
    // SIGNED GRID RANGE CONSTRAINTS
    // ========================================================================
    constraint grid_range_c {

        isp_grid_2d_0_0 inside {[-1024:1023]};
        isp_grid_2d_0_1 inside {[-1024:1023]};
        isp_grid_2d_0_2 inside {[-512:511]};
        isp_grid_2d_0_3 inside {[-512:511]};
        isp_grid_2d_0_4 inside {-100, -50, 0, 50, 100};
        isp_grid_2d_0_6 inside {[-2048:2047]};
    }

endclass
