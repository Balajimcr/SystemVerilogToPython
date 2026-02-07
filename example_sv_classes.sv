// ============================================================================
// ISP YUV → RGB Golden Constraint Model
// ============================================================================

typedef enum int { YUV_444=0, YUV_422=1, YUV_420=2 } yuv_format_e;
typedef enum int { YUV_PLANAR=0, YUV_SEMI_PLANAR, YUV_PACKED } yuv_packing_e;
typedef enum int { CS_BT601=0, CS_BT709, CS_BT2020 } color_space_e;
typedef enum int { BIT_8=8, BIT_10=10, BIT_12=12 } bit_depth_e;
typedef enum int { RGB_888=0, RGB_101010, RGB_121212 } rgb_format_e;
typedef enum int { FULL_RANGE=0, LIMITED_RANGE } range_mode_e;

class isp_yuv2rgb_cfg;

    // ------------------------------------------------------------------------
    // Core Controls
    // ------------------------------------------------------------------------
    rand bit enable;
    rand int yuv_format;
    rand int yuv_packing;
    rand int yuv_bit_depth;
    rand int color_space;
    rand int range_mode;
    rand int rgb_format;

    // ------------------------------------------------------------------------
    // Frame Geometry
    // ------------------------------------------------------------------------
    rand int unsigned width;
    rand int unsigned height;

    // ------------------------------------------------------------------------
    // Feature Enables
    // ------------------------------------------------------------------------
    rand bit chroma_enabled;
    rand bit dither_enable;
    rand bit clip_enable;

    // ------------------------------------------------------------------------
    // Matrix Coefficients (signed)
    // ------------------------------------------------------------------------
    rand int signed c00;
    rand int signed c01;
    rand int signed c02;
    rand int signed c10;
    rand int signed c11;
    rand int signed c12;
    rand int signed c20;
    rand int signed c21;
    rand int signed c22;

    // ------------------------------------------------------------------------
    // Offsets
    // ------------------------------------------------------------------------
    rand int signed y_offset;
    rand int signed uv_offset;

    // ========================================================================
    // ARITHMETIC / LOGIC TRANSLATION TEST FIELDS
    // ========================================================================
    rand int a;
    rand int b;
    rand int c;
    rand int d;

    rand int x;
    rand int y;
    rand int z;
    rand int w;

    rand int arith_width;
    rand int stride;

    rand int fmt;
    rand int bit_depth;
    rand int arith_y_offset;

    rand int signed signed_val;
    rand int unsigned unsigned_val;

    rand int mode;
    rand int range;

    // ========================================================================
    // DEFAULT RANGELISTS
    // ========================================================================
    constraint cr_default_rangelists {

        // ---- enum-backed ints ----
        yuv_format     inside {YUV_444, YUV_422, YUV_420};
        yuv_packing    inside {YUV_PLANAR, YUV_SEMI_PLANAR, YUV_PACKED};
        color_space    inside {CS_BT601, CS_BT709, CS_BT2020};
        range_mode     inside {FULL_RANGE, LIMITED_RANGE};
        rgb_format     inside {RGB_888, RGB_101010, RGB_121212};
        yuv_bit_depth  inside {BIT_8, BIT_10, BIT_12};

        // ---- booleans ----
        enable          inside {0,1};
        chroma_enabled  inside {0,1};
        dither_enable   inside {0,1};
        clip_enable     inside {0,1};

        // ---- frame geometry ----
        width           inside {[64:16384]};
        height          inside {[64:16384]};

        // ---- matrix coefficients (signed fixed-point) ----
        c00 inside {[-1024:1023]};
        c01 inside {[-1024:1023]};
        c02 inside {[-1024:1023]};
        c10 inside {[-1024:1023]};
        c11 inside {[-1024:1023]};
        c12 inside {[-1024:1023]};
        c20 inside {[-1024:1023]};
        c21 inside {[-1024:1023]};
        c22 inside {[-1024:1023]};

        // ---- offsets ----
        y_offset  inside {[-65536:65535]};
        uv_offset inside {[-65536:65535]};
        arith_y_offset inside {[-65536:65535]};

        // ---- arithmetic scratch variables ----
        a inside {[-1024:1023]};
        b inside {[-1024:1023]};
        c inside {[-1024:1023]};
        d inside {[1:1024]};      // avoid divide-by-zero

        x inside {[-4096:4095]};
        y inside {[-4096:4095]};
        z inside {[-4096:4095]};
        w inside {[-4096:4095]};

        arith_width inside {[1:16384]};
        stride      inside {[1:131072]};

        bit_depth inside {[1:16]};
        fmt       inside {[0:3]};
        mode      inside {[0:3]};
        range     inside {[0:1]};

        signed_val   inside {[-128:127]};
        unsigned_val inside {[0:255]};
    }

    // ========================================================================
    // BASIC RANGES
    // ========================================================================
    constraint cr_basic_ranges {
        enable inside {0,1};
        width  inside {[64:8192]};
        height inside {[64:8192]};
    }

    // ========================================================================
    // FORMAT vs PACKING
    // ========================================================================
    constraint cr_format_packing {
        if (yuv_packing == YUV_PACKED) {
            yuv_format != YUV_420;
        }
        if (yuv_format == YUV_420) {
            yuv_packing != YUV_PACKED;
        }
    }

    // ========================================================================
    // BIT DEPTH RULES
    // ========================================================================
    constraint cr_bit_depth {
        if (yuv_packing == YUV_PACKED) {
            yuv_bit_depth inside {BIT_8, BIT_10};
        }

        if (rgb_format == RGB_888) {
            yuv_bit_depth == BIT_8;
        }
        else if (rgb_format == RGB_101010) {
            yuv_bit_depth inside {BIT_10, BIT_12};
        }
        else {
            yuv_bit_depth == BIT_12;
        }
    }

    // ========================================================================
    // CHROMA ENABLE
    // ========================================================================
    constraint cr_chroma {
        if (yuv_format == YUV_444) {
            chroma_enabled == 1;
        }
        else {
            chroma_enabled inside {0,1};
        }
    }

    // ========================================================================
    // COLOR MATRIX
    // ========================================================================
    constraint cr_color_matrix {

        if (color_space == CS_BT601) {
            c00==298; c01==0;   c02==409;
            c10==298; c11==-100;c12==-208;
            c20==298; c21==516; c22==0;
        }
        else if (color_space == CS_BT709) {
            c00==298; c01==0;   c02==459;
            c10==298; c11==-55; c12==-136;
            c20==298; c21==541; c22==0;
        }
        else {
            c00==298; c01==0;   c02==483;
            c10==298; c11==-57; c12==-157;
            c20==298; c21==565; c22==0;
        }

        solve color_space before c00;
        solve color_space before c01;
        solve color_space before c02;
        solve color_space before c10;
        solve color_space before c11;
        solve color_space before c12;
        solve color_space before c20;
        solve color_space before c21;
        solve color_space before c22;
    }

    // ========================================================================
    // OFFSETS
    // ========================================================================
    constraint cr_offsets {

        if (range_mode == FULL_RANGE) {
            y_offset  == 0;
            uv_offset == (1 << (yuv_bit_depth-1));
        }
        else {
            y_offset  == (16  << (yuv_bit_depth-8));
            uv_offset == (128 << (yuv_bit_depth-8));
        }

        solve range_mode before y_offset;
        solve range_mode before uv_offset;
        solve yuv_bit_depth before y_offset;
        solve yuv_bit_depth before uv_offset;
    }

    // ========================================================================
    // DITHER & CLIP
    // ========================================================================
    constraint cr_dither_clip {

        if ((yuv_bit_depth > BIT_8) && (rgb_format == RGB_888)) {
            dither_enable == 1;
        }
        else {
            dither_enable inside {0,1};
        }

        if (range_mode == LIMITED_RANGE) {
            clip_enable == 1;
        }

        solve yuv_bit_depth before dither_enable;
        solve rgb_format    before dither_enable;
        solve range_mode    before clip_enable;
    }

    // ========================================================================
    // DIMENSION ALIGNMENT
    // ========================================================================
    constraint cr_dimension_alignment {

        if (yuv_format == YUV_420) {
            (width  % 2) == 0;
            (height % 2) == 0;
        }
        else if (yuv_format == YUV_422) {
            (width % 2) == 0;
        }

        solve yuv_format before width;
        solve yuv_format before height;
    }

    // ========================================================================
    // DISTRIBUTIONS
    // ========================================================================
    constraint cr_distributions {

        yuv_format dist {
            YUV_444 := 20,
            YUV_422 := 50,
            YUV_420 := 30
        };

        yuv_bit_depth dist {
            BIT_8  := 60,
            BIT_10 := 30,
            BIT_12 := 10
        };

        color_space dist {
            CS_BT601  := 40,
            CS_BT709  := 40,
            CS_BT2020 := 20
        };
    }

    // ========================================================================
    // TRANSLATION BUG-CATCHING TESTS (ADDITIVE)
    // ========================================================================

    constraint tc_logical_ops {
        if ((a > 8) && (b < 4))
            c == 1;
        else
            c == 0;
    }

    constraint tc_int_div {
        stride == (arith_width * 10 + 7) / 8;
    }

    constraint tc_signed_unsigned {
        signed_val inside {[-128:127]};
        unsigned_val == signed_val + 128;
    }

    constraint tc_parallel_if {
        if (a == 0) b == 1;
        if (c == 0) d == 2;
    }

    constraint tc_not {
        if (!(mode == 0))
            bit_depth == BIT_10;
    }

    constraint tc_shift {
        arith_y_offset == (1 << (bit_depth - 1));
        x == y << 2;
        z == w >> 1;
    }

    constraint tc_modulo {
        (x % 2) == 0;
        (arith_width % 4) == 0;
    }

    constraint tc_conditional_stride {
        if (fmt == 0) {
            stride >= (arith_width * 8 + 7) / 8;
        }
    }

    constraint tc_golden {
        if (fmt == 0) {
            stride >= (arith_width * bit_depth + 7) / 8;
            stride <= ((arith_width * bit_depth + 7) / 8) * 125 / 100;
        }
    }

    // ========================================================================
    // INSIDE IN CONDITIONS (PyVSC requires .inside() method in conditions)
    // ========================================================================

    rand int IsRdmaDataFormatYuv;
    rand int IsYuvFormat;
    rand int IsInBittageType;

    constraint cr_inside_if {
        if (IsRdmaDataFormatYuv inside {4, 5, 16, 17, 20, 21}) IsYuvFormat == 0;
        else IsYuvFormat == 1;
        solve IsRdmaDataFormatYuv before IsYuvFormat;
    }

    constraint cr_inside_else_if {
        if (IsRdmaDataFormatYuv inside {4, 5, 7, 8}) IsInBittageType == 0;
        else if (IsRdmaDataFormatYuv inside {16, 17, 32, 33}) IsInBittageType == 1;
        else IsInBittageType == 3;
        solve IsRdmaDataFormatYuv before IsInBittageType;
    }

    constraint cr_inside_standalone {
        IsRdmaDataFormatYuv inside {4, 5, 7, 8, 16, 17, 20, 21, 32, 33};
    }

    constraint cr_inside_implies {
        (mode == 1) -> IsRdmaDataFormatYuv inside {4, 5, 16, 17};
    }

    // ========================================================================
    // COMPLEX LOGICAL OPERATORS
    // ========================================================================

    constraint cr_complex_logic {
        if ((a > 0) && (b < 10) || (c == 5))
            d == 1;
        else
            d == 2;
    }

    constraint cr_negation {
        if (!(a == 0) && !(b == 0))
            c == a + b;
    }

    constraint cr_implication_inside_antecedent {
        (IsRdmaDataFormatYuv inside {4, 5}) -> (IsYuvFormat == 0);
    }

    // ========================================================================
    // LOGICAL OPERATOR PRECEDENCE (Python | & have higher precedence than ==)
    // ========================================================================

    rand int IsSrcCompType;
    rand int IsInWidth;
    rand int yuv_rdmaY_img_stride_1p;
    rand int yuv_rdmaY_sbwc_lossy_comp_mode;
    rand int yuv_rdmaY_comp_64B_align;

    constraint cr_logical_precedence {
        if (yuv_rdmaY_sbwc_lossy_comp_mode == 0 || yuv_rdmaY_sbwc_lossy_comp_mode == 1) {
            if (yuv_rdmaY_comp_64B_align) {
                yuv_rdmaY_img_stride_1p == ((IsInWidth+31)/32)*128;
            } else {
                yuv_rdmaY_img_stride_1p == ((IsInWidth+31)/32)*96;
            }
        } else if (yuv_rdmaY_sbwc_lossy_comp_mode == 2) {
            yuv_rdmaY_img_stride_1p == ((IsInWidth+31)/32)*64;
        }
    }

    constraint cr_multi_or {
        if (mode == 0 || mode == 1 || mode == 2)
            a == 1;
        else
            a == 0;
    }

    constraint cr_mixed_and_or {
        if (a == 1 && b == 2 || c == 3)
            d == 100;
    }

    // ========================================================================
    // DISTRIBUTION WITH RANGES (vsc.weight takes only 2 args, not 3)
    // ========================================================================

    rand int ip_post_frame_gap;
    rand int packet_size;
    rand int delay_cycles;

    constraint cr_dist_range {
        ip_post_frame_gap dist { [10:2000]:/95, [2001:50000]:/5 };
    }

    constraint cr_dist_mixed {
        packet_size dist { 64:=10, 128:=20, [256:1024]:/50, [1025:4096]:/20 };
    }

    constraint cr_dist_simple {
        delay_cycles dist { 0:=50, 1:=30, [2:10]:/20 };
    }

    // ========================================================================
    // LITERAL ON LEFT SIDE OF ARITHMETIC (PyVSC needs vsc.unsigned wrapper)
    // ========================================================================

    rand int IsBypassMode;
    rand int IsGridMode;
    rand int yuv_isp_image_crop_pre_x;
    rand int yuv_isp_image_active_width;
    rand int yuv_isp_out_scale_x;
    rand int yuv_isp_crop_width;

    constraint cr_literal_subtract {
        yuv_isp_image_crop_pre_x <= 16384 - yuv_isp_image_active_width;
    }

    constraint cr_literal_add {
        x <= 1000 + y;
    }

    constraint cr_literal_multiply {
        z == 10 * w;
    }

    constraint cr_nested_arithmetic {
        if (IsBypassMode) {
            yuv_isp_image_crop_pre_x == 0;
        } else {
            if (IsGridMode == 0) {
                (yuv_isp_image_crop_pre_x + yuv_isp_image_active_width)*yuv_isp_out_scale_x/8192 <= (yuv_isp_crop_width);
            } else {
                (yuv_isp_image_crop_pre_x + yuv_isp_image_active_width*yuv_isp_out_scale_x/8192) <= (yuv_isp_crop_width);
            }
            yuv_isp_image_crop_pre_x <= 16384 - yuv_isp_image_active_width;
        }
        solve IsBypassMode before yuv_isp_image_crop_pre_x;
        solve yuv_isp_crop_width before yuv_isp_image_crop_pre_x;
        solve yuv_isp_image_active_width before yuv_isp_image_crop_pre_x;
        solve yuv_isp_out_scale_x before yuv_isp_image_crop_pre_x;
    }

endclass
