// ============================================================
// Small representative SV test based on real Isp_rand_item
// ============================================================

class Isp_rand_item_small extends uvm_sequence_item;

    // --------------------------------------------------------
    // Core control fields
    // --------------------------------------------------------
    rand bit [31:0] IsIspBypassMode;
    rand bit [31:0] IsIspYuvFormat;
    rand bit [31:0] IsIspSrcCompType;
    rand bit [31:0] IsIspDstCompType;
    rand bit [31:0] IsIspInBittageType;
    rand bit [31:0] IsIspOutBittageType;

    rand bit [31:0] IsRdmaDataFormatYuv;
    rand bit [31:0] IsWdmaDataFormatYuv;

    // --------------------------------------------------------
    // Signed variable test cases
    // --------------------------------------------------------
    rand bit signed [31:0] isp_grid_2d_0_0;
    rand bit signed [31:0] isp_grid_2d_0_1;
    rand bit signed [31:0] isp_grid_2d_0_2;
    rand bit signed [31:0] isp_grid_2d_0_3;
    rand bit signed [31:0] isp_grid_2d_0_4;
    rand bit signed [31:0] isp_grid_2d_0_6;

    // --------------------------------------------------------
    // UVM registration (kept minimal)
    // --------------------------------------------------------
    `uvm_object_utils_begin(Isp_rand_item_small)
        `uvm_field_int(IsIspBypassMode,        UVM_DEFAULT)
        `uvm_field_int(IsIspYuvFormat,         UVM_DEFAULT)
        `uvm_field_int(IsIspSrcCompType,       UVM_DEFAULT)
        `uvm_field_int(IsIspDstCompType,       UVM_DEFAULT)
        `uvm_field_int(IsIspInBittageType,     UVM_DEFAULT)
        `uvm_field_int(IsIspOutBittageType,    UVM_DEFAULT)
        `uvm_field_int(IsRdmaDataFormatYuv,    UVM_DEFAULT)
        `uvm_field_int(IsWdmaDataFormatYuv,    UVM_DEFAULT)
    `uvm_object_utils_end

    // --------------------------------------------------------
    // Basic range constraints (from real code)
    // --------------------------------------------------------

    constraint CR_VAR_RANGE_IsIspBypassMode {
        IsIspBypassMode >= 0 && IsIspBypassMode <= 1;
    }

    constraint CR_VAR_RANGE_IsIspYuvFormat {
        IsIspYuvFormat >= 0 && IsIspYuvFormat <= 1;
    }

    constraint CR_VAR_RANGE_IsIspSrcCompType {
        IsIspSrcCompType >= 0 && IsIspSrcCompType <= 2;
    }

    constraint CR_VAR_RANGE_IsIspDstCompType {
        IsIspDstCompType >= 0 && IsIspDstCompType <= 2;
    }

    constraint CR_VAR_RANGE_IsIspInBittageType {
        IsIspInBittageType >= 0 && IsIspInBittageType <= 3;
    }

    constraint CR_VAR_RANGE_IsIspOutBittageType {
        IsIspOutBittageType >= 0 && IsIspOutBittageType <= 3;
    }

    // --------------------------------------------------------
    // Conditional + inside + solve-order (cr1 equivalent)
    // --------------------------------------------------------

    constraint cr1 {
        if (IsRdmaDataFormatYuv inside {4, 5, 16, 17, 20, 21})
            IsIspYuvFormat == 0;
        else
            IsIspYuvFormat == 1;

        solve IsRdmaDataFormatYuv before IsIspYuvFormat;
    }

    // --------------------------------------------------------
    // Conditional + inside + solve-order (cr4 equivalent)
    // --------------------------------------------------------

    constraint cr4 {
        if (IsIspBypassMode)
            IsIspSrcCompType inside {0, 1};

        solve IsIspBypassMode before IsIspSrcCompType;
    }

    // --------------------------------------------------------
    // Equality dependency + solve-order (cr5 equivalent)
    // --------------------------------------------------------

    constraint cr5 {
        if (IsIspBypassMode)
            IsIspDstCompType == IsIspSrcCompType;

        solve IsIspBypassMode before IsIspDstCompType;
        solve IsIspSrcCompType before IsIspDstCompType;
		solve IsIspYuvFormat before IsIspSrcCompType;
        solve IsIspDstCompType before IsIspInBittageType;
        solve IsIspInBittageType before IsIspOutBittageType;
    }

    // --------------------------------------------------------
    // Multi-branch conditional + solve-order (cr6 equivalent)
    // --------------------------------------------------------

    constraint cr6 {
        if (IsRdmaDataFormatYuv inside {4, 5, 7, 8})
            IsIspInBittageType == 0;
        else if (IsRdmaDataFormatYuv inside {16, 17, 32, 33})
            IsIspInBittageType == 1;
        else
            IsIspInBittageType == 3;

        solve IsRdmaDataFormatYuv before IsIspInBittageType;
		solve IsIspYuvFormat before IsIspSrcCompType;
        solve IsIspSrcCompType before IsIspDstCompType;
        solve IsIspDstCompType before IsIspInBittageType;
        solve IsIspInBittageType before IsIspOutBittageType;
    }

    // --------------------------------------------------------
    // Cascaded dependency (cr7 equivalent)
    // --------------------------------------------------------

    constraint cr7 {
        if (IsIspInBittageType == 0)
            IsIspOutBittageType == 0;
        else if (IsIspDstCompType > 0)
            IsIspOutBittageType == 1;
        else
            IsIspOutBittageType inside {1, 3};

        solve IsIspInBittageType before IsIspOutBittageType;
        solve IsIspDstCompType before IsIspOutBittageType;
		solve IsIspYuvFormat before IsIspSrcCompType;
        solve IsIspSrcCompType before IsIspDstCompType;
        solve IsIspDstCompType before IsIspInBittageType;
        solve IsIspInBittageType before IsIspOutBittageType;
    }

    // --------------------------------------------------------
    // Test constraint with many solve orders in specific sequence
    // --------------------------------------------------------

    constraint cr8_solve_order_test {
        if (IsIspBypassMode)
            IsIspYuvFormat == 0;
        else
            IsIspYuvFormat == 1;

        solve IsRdmaDataFormatYuv before IsWdmaDataFormatYuv;
		solve IsIspBypassMode before IsIspYuvFormat;
        solve IsIspYuvFormat before IsIspSrcCompType;
        solve IsIspSrcCompType before IsIspDstCompType;
        solve IsIspDstCompType before IsIspInBittageType;
        solve IsIspInBittageType before IsIspOutBittageType;
    }

    // --------------------------------------------------------
    // Signed variable constraints (testing negative ranges)
    // --------------------------------------------------------

    constraint CR_SIGNED_RANGE_isp_grid_2d {
        isp_grid_2d_0_0 >= -1024 && isp_grid_2d_0_0 <= 1023;
        isp_grid_2d_0_1 >= -1024 && isp_grid_2d_0_1 <= 1023;
        isp_grid_2d_0_2 >= -512 && isp_grid_2d_0_2 <= 511;
        isp_grid_2d_0_3 >= -512 && isp_grid_2d_0_3 <= 511;
        isp_grid_2d_0_4 inside {-100, -50, 0, 50, 100};
        isp_grid_2d_0_6 >= -2048 && isp_grid_2d_0_6 <= 2047;
    }

    // --------------------------------------------------------
    // Test single & and | operators
    // --------------------------------------------------------

    constraint cr9_single_logical_ops {
        (IsIspBypassMode == 1) & (IsIspYuvFormat == 0);
        (IsIspSrcCompType == 0) | (IsIspDstCompType == 1);
        (IsIspInBittageType >= 0) & (IsIspInBittageType <= 2) | (IsIspOutBittageType == 3);
    }
endclass
