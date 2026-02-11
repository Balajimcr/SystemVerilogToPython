class isp_yuv2rgb_rand_item extends uvm_sequence_item;

 rand bit [31:0] IsBypassMode;
 rand bit [31:0] IsYuvFormat;
 rand bit [31:0] IsImageWidth;
 rand bit [31:0] IsImageHeight;
 rand bit [31:0] IsGridMode;
 rand bit [31:0] enable;
 rand bit [31:0] chroma_enabled;
 rand bit [31:0] dither_enable;
 rand bit [31:0] clip_enable;
 rand bit [31:0] width;
 rand bit [31:0] height;
 rand bit [31:0] IsInWidth;
 rand bit [31:0] arith_width;
 rand bit [31:0] stride;
 rand bit [31:0] fmt;
 rand bit [31:0] mode;
 rand bit [31:0] range;
 rand bit signed [31:0] signed_val;
 rand bit [31:0] unsigned_val;
 rand bit signed [31:0] c00;
 rand bit signed [31:0] c01;
 rand bit signed [31:0] c02;
 rand bit signed [31:0] c10;
 rand bit signed [31:0] c11;
 rand bit signed [31:0] c12;
 rand bit signed [31:0] c20;
 rand bit signed [31:0] c21;
 rand bit signed [31:0] c22;
 rand bit signed [31:0] y_offset;
 rand bit signed [31:0] uv_offset;
 rand bit signed [31:0] arith_y_offset;
 rand bit [31:0] IsRdmaDataFormatYuv;
 rand bit [31:0] IsInBittageType;
 rand bit [31:0] yuv_isp_image_active_width;
 rand bit [31:0] yuv_isp_crop_width;
 rand bit [31:0] yuv_isp_image_crop_pre_x;
 rand bit signed [31:0] yuv_isp_scale_y;
 rand bit [31:0] yuv_isp_scale_shifter_y;
 rand bit [31:0] yuv_isp_org_height;
 rand bit [31:0] yuv_isp_image_active_height;

`uvm_object_utils_begin(isp_yuv2rgb_rand_item)
 `uvm_field_int(IsBypassMode, UVM_DEFAULT)
 `uvm_field_int(IsYuvFormat, UVM_DEFAULT)
 `uvm_field_int(IsImageWidth, UVM_DEFAULT)
 `uvm_field_int(IsImageHeight, UVM_DEFAULT)
 `uvm_field_int(IsGridMode, UVM_DEFAULT)
 `uvm_field_int(enable, UVM_DEFAULT)
 `uvm_field_int(chroma_enabled, UVM_DEFAULT)
 `uvm_field_int(dither_enable, UVM_DEFAULT)
 `uvm_field_int(clip_enable, UVM_DEFAULT)
 `uvm_field_int(width, UVM_DEFAULT)
 `uvm_field_int(height, UVM_DEFAULT)
 `uvm_field_int(IsInWidth, UVM_DEFAULT)
 `uvm_field_int(arith_width, UVM_DEFAULT)
 `uvm_field_int(stride, UVM_DEFAULT)
 `uvm_field_int(fmt, UVM_DEFAULT)
 `uvm_field_int(mode, UVM_DEFAULT)
 `uvm_field_int(range, UVM_DEFAULT)
 `uvm_field_int(signed_val, UVM_DEFAULT)
 `uvm_field_int(unsigned_val, UVM_DEFAULT)
 `uvm_field_int(c00, UVM_DEFAULT)
 `uvm_field_int(c01, UVM_DEFAULT)
 `uvm_field_int(c02, UVM_DEFAULT)
 `uvm_field_int(c10, UVM_DEFAULT)
 `uvm_field_int(c11, UVM_DEFAULT)
 `uvm_field_int(c12, UVM_DEFAULT)
 `uvm_field_int(c20, UVM_DEFAULT)
 `uvm_field_int(c21, UVM_DEFAULT)
 `uvm_field_int(c22, UVM_DEFAULT)
 `uvm_field_int(y_offset, UVM_DEFAULT)
 `uvm_field_int(uv_offset, UVM_DEFAULT)
 `uvm_field_int(arith_y_offset, UVM_DEFAULT)
 `uvm_field_int(IsRdmaDataFormatYuv, UVM_DEFAULT)
 `uvm_field_int(IsInBittageType, UVM_DEFAULT)
 `uvm_field_int(yuv_isp_image_active_width, UVM_DEFAULT)
 `uvm_field_int(yuv_isp_crop_width, UVM_DEFAULT)
 `uvm_field_int(yuv_isp_image_crop_pre_x, UVM_DEFAULT)
 `uvm_field_int(yuv_isp_scale_y, UVM_DEFAULT)
 `uvm_field_int(yuv_isp_scale_shifter_y, UVM_DEFAULT)
 `uvm_field_int(yuv_isp_org_height, UVM_DEFAULT)
 `uvm_field_int(yuv_isp_image_active_height, UVM_DEFAULT)
`uvm_object_utils_end
   constraint CR_VAR_RANGE_IsBypassMode
     {
       (IsBypassMode >= 0 && IsBypassMode <= 1);
     }

   constraint CR_VAR_RANGE_IsYuvFormat
     {
       (IsYuvFormat >= 0 && IsYuvFormat <= 5);
     }

   constraint CR_VAR_RANGE_IsImageWidth
     {
       (IsImageWidth >= 64 && IsImageWidth <= 16384);
     }

   constraint CR_VAR_RANGE_IsImageHeight
     {
       (IsImageHeight >= 64 && IsImageHeight <= 16384);
     }

   constraint CR_VAR_RANGE_IsGridMode
     {
       (IsGridMode >= 0 && IsGridMode <= 1);
     }

   constraint CR_VAR_RANGE_enable
     {
       (enable >= 0 && enable <= 1);
     }

   constraint CR_VAR_RANGE_chroma_enabled
     {
       (chroma_enabled >= 0 && chroma_enabled <= 1);
     }

   constraint CR_VAR_RANGE_dither_enable
     {
       (dither_enable >= 0 && dither_enable <= 1);
     }

   constraint CR_VAR_RANGE_clip_enable
     {
       (clip_enable >= 0 && clip_enable <= 1);
     }

   constraint CR_VAR_RANGE_width
     {
       (width >= 64 && width <= 16384);
     }

   constraint CR_VAR_RANGE_height
     {
       (height >= 64 && height <= 16384);
     }

   constraint CR_VAR_RANGE_IsInWidth
     {
       (IsInWidth >= 64 && IsInWidth <= 16384);
     }

   constraint CR_VAR_RANGE_arith_width
     {
       (arith_width >= 1 && arith_width <= 16);
     }

   constraint CR_VAR_RANGE_stride
     {
       (stride >= 1 && stride <= 65536);
     }

   constraint CR_VAR_RANGE_fmt
     {
       (fmt >= 0 && fmt <= 15);
     }

   constraint CR_VAR_RANGE_mode
     {
       (mode >= 0 && mode <= 7);
     }

   constraint CR_VAR_RANGE_range
     {
       (range >= 0 && range <= 3);
     }

   constraint CR_VAR_RANGE_signed_val
     {
       (signed_val >= -32768 && signed_val <= 32767);
     }

   constraint CR_VAR_RANGE_unsigned_val
     {
       (unsigned_val >= 0 && unsigned_val <= 255);
     }

   constraint CR_VAR_RANGE_c00
     {
       (c00 >= -1024 && c00 <= 1024);
     }

   constraint CR_VAR_RANGE_c01
     {
       (c01 >= -1024 && c01 <= 1024);
     }

   constraint CR_VAR_RANGE_c02
     {
       (c02 >= -1024 && c02 <= 1024);
     }

   constraint CR_VAR_RANGE_c10
     {
       (c10 >= -1024 && c10 <= 1024);
     }

   constraint CR_VAR_RANGE_c11
     {
       (c11 >= -1024 && c11 <= 1024);
     }

   constraint CR_VAR_RANGE_c12
     {
       (c12 >= -1024 && c12 <= 1024);
     }

   constraint CR_VAR_RANGE_c20
     {
       (c20 >= -1024 && c20 <= 1024);
     }

   constraint CR_VAR_RANGE_c21
     {
       (c21 >= -1024 && c21 <= 1024);
     }

   constraint CR_VAR_RANGE_c22
     {
       (c22 >= -1024 && c22 <= 1024);
     }

   constraint CR_VAR_RANGE_y_offset
     {
       (y_offset >= -1024 && y_offset <= 1024);
     }

   constraint CR_VAR_RANGE_uv_offset
     {
       (uv_offset >= -1024 && uv_offset <= 1024);
     }

   constraint CR_VAR_RANGE_arith_y_offset
     {
       (arith_y_offset >= -1024 && arith_y_offset <= 1024);
     }

   constraint CR_VAR_RANGE_IsRdmaDataFormatYuv
     {
       (IsRdmaDataFormatYuv >= 4 && IsRdmaDataFormatYuv <= 33);
     }

   constraint CR_VAR_RANGE_IsInBittageType
     {
       (IsInBittageType >= 0 && IsInBittageType <= 3);
     }

   constraint CR_VAR_RANGE_yuv_isp_image_active_width
     {
       (yuv_isp_image_active_width >= 0 && yuv_isp_image_active_width <= 16384);
     }

   constraint CR_VAR_RANGE_yuv_isp_crop_width
     {
       (yuv_isp_crop_width >= 0 && yuv_isp_crop_width <= 16384);
     }

   constraint CR_VAR_RANGE_yuv_isp_image_crop_pre_x
     {
       (yuv_isp_image_crop_pre_x >= 0 && yuv_isp_image_crop_pre_x <= 16384);
     }

   constraint CR_VAR_RANGE_yuv_isp_scale_y
     {
       (yuv_isp_scale_y >= -8192 && yuv_isp_scale_y <= 8191);
     }

   constraint CR_VAR_RANGE_yuv_isp_scale_shifter_y
     {
       (yuv_isp_scale_shifter_y >= 0 && yuv_isp_scale_shifter_y <= 15);
     }

   constraint CR_VAR_RANGE_yuv_isp_org_height
     {
       (yuv_isp_org_height >= 1 && yuv_isp_org_height <= 16384);
     }

   constraint CR_VAR_RANGE_yuv_isp_image_active_height
     {
       (yuv_isp_image_active_height >= 0 && yuv_isp_image_active_height <= 16384);
     }

   constraint cr0
     {
       
       IsBypassMode inside {0, 1};
                   
     }

   constraint cr1
     {
       
       IsYuvFormat inside {0,1,2,3,4,5};
                   
     }

   constraint cr13
     {
       
       stride % 16 == 0;
               
       
       if (yuv_rdmaY_comp_64B_align)
       stride % 64 == 0;
               
     }

   constraint cr31
     {
       
       IsRdmaDataFormatYuv inside {4,5,7,8,16,17,20,21,32,33};
               
       
       if (IsRdmaDataFormatYuv inside {4,5,7,8})
       IsInBittageType == 0;
       else if (IsRdmaDataFormatYuv inside {16,17,32,33})
       IsInBittageType == 1;
       else
       IsInBittageType == 3;
               
     }

   constraint cr33
     {
       
       yuv_isp_image_active_width <= width;
               
     }

   constraint cr34
     {
       
       yuv_isp_crop_width <= yuv_isp_image_active_width;
               
     }

   constraint cr35
     {
       
       yuv_isp_image_crop_pre_x + yuv_isp_crop_width <= width;
               
     }

   constraint cr39
     {
       
       yuv_isp_image_active_height <= yuv_isp_org_height;
               
     }

endclass
