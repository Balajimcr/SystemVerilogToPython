// ============================================================================
// ISP YUV → RGB Golden Constraint Model (NO IMPLICATIONS)
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
    // Matrix Coefficients
    // ------------------------------------------------------------------------
    rand int signed c00,c01,c02;
    rand int signed c10,c11,c12;
    rand int signed c20,c21,c22;

    // ------------------------------------------------------------------------
    // Offsets
    // ------------------------------------------------------------------------
    rand int signed y_offset;
    rand int signed uv_offset;

    // ========================================================================
    // BASIC RANGES
    // ========================================================================
    constraint cr_basic_ranges {
        enable inside {0,1};
        width  inside {[64:8192]};
        height inside {[64:8192]};
    }

    // ========================================================================
    // FORMAT vs PACKING (NO IMPLIES)
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
    // BIT DEPTH RULES (NO IMPLIES)
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
    // OFFSETS (NO IMPLIES)
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
    // DITHER & CLIP (NO IMPLIES)
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

endclass
