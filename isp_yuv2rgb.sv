// ============================================================================
// ISP YUV → RGB Configuration
// Range-complete, solver-stable, HW-realistic
// ============================================================================

// ---------------------------------------------------------------------------
// ENUMS
// ---------------------------------------------------------------------------

typedef enum int { YUV_444=0, YUV_422=1, YUV_420=2 } yuv_format_e;
typedef enum int { PLANAR=0, SEMI_PLANAR=1, PACKED=2 } yuv_packing_e;
typedef enum int { BT601=0, BT709=1, BT2020=2 } color_space_e;
typedef enum int { FULL_RANGE=0, LIMITED_RANGE=1 } range_mode_e;
typedef enum int { RGB_888=0, RGB_101010=1, RGB_121212=2 } rgb_format_e;
typedef enum int { BIT_8=8, BIT_10=10, BIT_12=12 } bit_depth_e;


// ---------------------------------------------------------------------------
// CONFIGURATION CLASS
// ---------------------------------------------------------------------------

class isp_yuv2rgb_cfg;

    // -----------------------------------------------------------------------
    // Core controls
    // -----------------------------------------------------------------------
    rand bit enable;
    rand yuv_format_e yuv_format;
    rand yuv_packing_e yuv_packing;
    rand bit_depth_e yuv_bit_depth;
    rand color_space_e color_space;
    rand range_mode_e range_mode;
    rand rgb_format_e rgb_format;

    // -----------------------------------------------------------------------
    // Geometry
    // -----------------------------------------------------------------------
    rand int unsigned width;
    rand int unsigned height;

    // -----------------------------------------------------------------------
    // Feature enables
    // -----------------------------------------------------------------------
    rand bit chroma_enabled;
    rand bit dither_enable;
    rand bit clip_enable;

    // -----------------------------------------------------------------------
    // Matrix coefficients
    // -----------------------------------------------------------------------
    rand int signed c00;
    rand int signed c01;
    rand int signed c02;
    rand int signed c10;
    rand int signed c11;
    rand int signed c12;
    rand int signed c20;
    rand int signed c21;
    rand int signed c22;

    // -----------------------------------------------------------------------
    // Offsets
    // -----------------------------------------------------------------------
    rand int signed y_offset;
    rand int signed uv_offset;
    rand int signed arith_y_offset;

    // -----------------------------------------------------------------------
    // Arithmetic / misc
    // -----------------------------------------------------------------------
    rand int signed a;
    rand int signed b;
    rand int signed c;
    rand int signed d;
    rand int signed x;
    rand int signed y;
    rand int signed z;
    rand int signed w;

    rand int unsigned arith_width;
    rand int unsigned stride;
    rand int unsigned fmt;
    rand bit_depth_e bit_depth;
    rand int signed signed_val;
    rand int unsigned unsigned_val;
    rand int unsigned mode;
    rand int unsigned range;

    // -----------------------------------------------------------------------
    // RDMA / ISP
    // -----------------------------------------------------------------------
    rand int unsigned IsRdmaDataFormatYuv;
    rand yuv_format_e IsYuvFormat;
    rand int unsigned IsInBittageType;
    rand int unsigned IsSrcCompType;
    rand int unsigned IsInWidth;

    // -----------------------------------------------------------------------
    // Stride / SBWC
    // -----------------------------------------------------------------------
    rand int unsigned yuv_rdmaY_img_stride_1p;
    rand bit yuv_rdmaY_sbwc_lossy_comp_mode;
    rand bit yuv_rdmaY_comp_64B_align;

    // -----------------------------------------------------------------------
    // Packet / timing
    // -----------------------------------------------------------------------
    rand int unsigned ip_post_frame_gap;
    rand int unsigned packet_size;
    rand int unsigned delay_cycles;

    // -----------------------------------------------------------------------
    // Bypass / grid
    // -----------------------------------------------------------------------
    rand bit IsBypassMode;
    rand bit IsGridMode;

    // -----------------------------------------------------------------------
    // ISP geometry
    // -----------------------------------------------------------------------
    rand int unsigned yuv_isp_image_crop_pre_x;
    rand int unsigned yuv_isp_image_active_width;
    rand int unsigned yuv_isp_out_scale_x;
    rand int unsigned yuv_isp_crop_width;

    // -----------------------------------------------------------------------
    // ISP
    // -----------------------------------------------------------------------
    rand int signed yuv_isp_scale_y;
    rand int signed yuv_isp_scale_shifter_y;
    rand int unsigned yuv_isp_org_height;
    rand int unsigned yuv_isp_image_active_height;

    // =======================================================================
    // BASIC RANGE CONSTRAINTS
    // =======================================================================

    constraint range_c {
        enable inside {0,1};
        chroma_enabled inside {0,1};
        dither_enable inside {0,1};
        clip_enable inside {0,1};

        width inside {[64:16384]};
        height inside {[64:16384]};
        IsInWidth inside {[64:16384]};

        arith_width inside {[1:16]};
        stride inside {[1:65536]};
        fmt inside {[0:15]};
        mode inside {[0:7]};
        range inside {[0:3]};

        signed_val inside {[-32768:32767]};
        unsigned_val inside {[0:255]};

        ip_post_frame_gap inside {[0:1000]};
        packet_size inside {[64:4096]};
        delay_cycles inside {[0:100000]};
    }

    // =======================================================================
    // MATRIX / OFFSET CONSISTENCY
    // =======================================================================

    constraint matrix_c {
        c00 inside {[-1024:1024]};
        c01 inside {[-1024:1024]};
        c02 inside {[-1024:1024]};
        c10 inside {[-1024:1024]};
        c11 inside {[-1024:1024]};
        c12 inside {[-1024:1024]};
        c20 inside {[-1024:1024]};
        c21 inside {[-1024:1024]};
        c22 inside {[-1024:1024]};

        y_offset inside {[-1024:1024]};
        uv_offset inside {[-1024:1024]};
        arith_y_offset inside {[-1024:1024]};
    }

    // =======================================================================
    // FORMAT / BIT-DEPTH COHERENCY
    // =======================================================================

    constraint format_c {
        bit_depth inside {BIT_8, BIT_10, BIT_12};
        yuv_bit_depth == bit_depth;

        if (rgb_format == RGB_888)
            bit_depth == BIT_8;
        else
            bit_depth inside {BIT_10, BIT_12};
    }

    // =======================================================================
    // YUV FORMAT / PACKING RULES
    // =======================================================================

    constraint packing_c {
        if (yuv_format == YUV_420)
            yuv_packing != PACKED;
    }

    // =======================================================================
    // STRIDE & ALIGNMENT
    // =======================================================================

    constraint stride_c {
        stride % 16 == 0;

        if (yuv_rdmaY_comp_64B_align)
            stride % 64 == 0;
    }

    // =======================================================================
    // RDMA → ISP RELATION
    // =======================================================================

    constraint rdma_c {
        IsRdmaDataFormatYuv inside {4,5,7,8,16,17,20,21,32,33};
        IsYuvFormat == yuv_format;

        if (IsRdmaDataFormatYuv inside {4,5,7,8})
            IsInBittageType == 0;
        else if (IsRdmaDataFormatYuv inside {16,17,32,33})
            IsInBittageType == 1;
        else
            IsInBittageType == 3;
    }

    // =======================================================================
    // GEOMETRY RELATIONS
    // =======================================================================

    constraint geometry_c {
        yuv_isp_image_active_width <= width;
        yuv_isp_crop_width <= yuv_isp_image_active_width;
        yuv_isp_image_crop_pre_x + yuv_isp_crop_width <= width;
    }

    // =======================================================================
    // ISP CONSISTENCY
    // =======================================================================

    constraint isp_c {
        yuv_isp_scale_y inside {[-8192:8191]};
        yuv_isp_scale_shifter_y inside {[0:15]};
        yuv_isp_image_active_height <= yuv_isp_org_height;
    }

endclass
