// =============================================================================
// Example 1: Basic Transaction Class
// =============================================================================

class basic_transaction;
    rand bit [7:0]  addr;
    rand bit [31:0] data;
    rand bit [3:0]  burst_len;
         bit [1:0]  fixed_mode;
    
    randc bit [3:0] cyclic_val;
    
    constraint addr_range_c {
        addr inside {[8'h10:8'hF0]};
    }
    
    constraint data_c {
        addr < 8'h20 -> data == 32'h0;
    }
    
    constraint burst_c {
        burst_len inside {[1:8]};
    }
endclass


// =============================================================================
// Example 2: AXI-like Transaction with Enums
// =============================================================================

typedef enum bit [1:0] {
    FIXED  = 2'b00,
    INCR   = 2'b01,
    WRAP   = 2'b10
} burst_type_e;

typedef enum bit [3:0] {
    READ   = 4'h0,
    WRITE  = 4'h1,
    IDLE   = 4'h2
} cmd_type_e;

class axi_transaction;
    rand bit [31:0]     addr;
    rand bit [7:0]      data[];
    rand bit [2:0]      size;
    rand bit [7:0]      len;
    rand burst_type_e   burst;
    rand cmd_type_e     cmd;
    rand bit            write;
    
    constraint valid_size_c {
        size inside {[0:3]};
    }
    
    constraint data_size_c {
        data.size() == (len + 1);
    }
    
    constraint addr_align_c {
        (addr % (1 << size)) == 0;
    }
    
    constraint wrap_c {
        (burst == WRAP) -> (len inside {1, 3, 7, 15});
    }
    
    constraint len_dist_c {
        len inside {[0:15]};
        len dist {
            [0:3]   := 60,
            [4:7]   := 25,
            [8:15]  := 15
        };
    }
    
    constraint burst_dist_c {
        burst dist {
            INCR  := 70,
            FIXED := 20,
            WRAP  := 10
        };
    }
    
    constraint solve_order_c {
        solve burst before len;
        solve len before data;
    }
endclass


// =============================================================================
// Example 3: Protocol Packet with Complex Constraints
// =============================================================================

typedef enum bit [3:0] {
    PKT_DATA    = 4'h0,
    PKT_ACK     = 4'h1,
    PKT_NACK    = 4'h2,
    PKT_CTRL    = 4'h3,
    PKT_STATUS  = 4'h4
} pkt_type_e;

class protocol_packet;
    rand pkt_type_e   pkt_type;
    rand bit [15:0]   seq_num;
    rand bit [7:0]    payload[];
    rand bit [7:0]    src_id;
    rand bit [7:0]    dst_id;
    rand bit          priority;
    rand bit [15:0]   flags;
    
    constraint solve_order_c {
        solve pkt_type before payload;
        solve pkt_type before flags;
    }
    
    constraint payload_size_c {
        if (pkt_type == PKT_DATA) {
            payload.size() inside {[64:256]};
        } else if (pkt_type == PKT_CTRL) {
            payload.size() inside {[8:64]};
        } else {
            payload.size() == 0;
        }
    }
    
    constraint flags_c {
        if (pkt_type == PKT_ACK || pkt_type == PKT_NACK) {
            flags[0] == 1;
        } else {
            flags[0] == 0;
        }
        
        priority -> flags[1];
    }
    
    constraint id_c {
        src_id != dst_id;
        src_id inside {[1:254]};
        dst_id inside {[1:254]};
    }
    
    constraint type_dist_c {
        pkt_type dist {
            PKT_DATA   := 50,
            PKT_ACK    := 20,
            PKT_NACK   := 5,
            PKT_CTRL   := 15,
            PKT_STATUS := 10
        };
    }
endclass


// =============================================================================
// Example 4: Array and Foreach Constraints
// =============================================================================

class array_example;
    rand bit [7:0] data_arr[16];
    rand bit [3:0] index_arr[8];
    rand int       values[];
    
    constraint arr_size_c {
        values.size() inside {[4:16]};
    }
    
    constraint foreach_c {
        foreach (data_arr[i]) {
            data_arr[i] > i;
            data_arr[i] < 200;
        }
    }
    
    constraint ascending_c {
        foreach (data_arr[i]) {
            if (i > 0) {
                data_arr[i] > data_arr[i-1];
            }
        }
    }
    
    constraint unique_c {
        unique {index_arr};
    }
    
    constraint index_range_c {
        foreach (index_arr[i]) {
            index_arr[i] inside {[0:15]};
        }
    }
endclass


// =============================================================================
// Example 5: Inheritance Example
// =============================================================================

class base_transaction;
    rand bit [7:0]  addr;
    rand bit [31:0] data;
    
    constraint base_addr_c {
        addr inside {[0:127]};
    }
endclass

class extended_transaction extends base_transaction;
    rand bit [3:0] burst_len;
    rand bit       enable;
    
    constraint ext_addr_c {
        addr inside {[64:127]};
    }
    
    constraint burst_c {
        burst_len inside {[1:8]};
        (burst_len > 4) -> (addr[6:0] == 0);
    }
    
    constraint enable_c {
        enable -> (data != 0);
    }
endclass


// =============================================================================
// Example 6: Soft Constraints
// =============================================================================

class soft_example;
    rand bit [7:0] addr;
    rand bit [7:0] data;
    rand bit [1:0] mode;
    
    constraint hard_c {
        addr inside {[0:255]};
        data inside {[0:255]};
    }
    
    constraint soft_defaults_c {
        soft addr == 8'h00;
        soft data == 8'hFF;
        soft mode == 2'b00;
    }
endclass
