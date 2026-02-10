#!/usr/bin/env python3
"""
SystemVerilog / XML to PyVSC Translation GUI

A Tkinter-based GUI for:
1. Browsing and selecting SystemVerilog (.sv) or XML (.xml) files
2. Converting XML to SV (if XML input is selected)
3. Translating SV to PyVSC Python code
4. Running PyVSC randomization tests
5. Generating test vectors
6. Displaying results and logs

All PyVSC output is generated in the Output/ directory.
PyVSC tests are executed from the Output/ directory.

Usage:
    python sv_to_pyvsc_gui.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import os
import sys
import subprocess
import threading
import queue
import re
import json
from datetime import datetime
from pathlib import Path

# Config file lives next to this script
_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "gui_config.json"
)


class SVtoPyVSCGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SV / XML to PyVSC Translation Tool")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

        # Project root directory (where this script lives)
        self.project_root = os.path.dirname(os.path.abspath(__file__))

        # Load environment config from Env.csh
        self.env_config = self._load_env_config()

        # Output directory for all PyVSC generated files
        self.output_base_dir = os.path.join(self.project_root, "Output")
        os.makedirs(self.output_base_dir, exist_ok=True)

        # Variables
        self.input_file_path = tk.StringVar()       # Can be .sv or .xml
        self.sv_file_path = tk.StringVar()           # Internal: resolved .sv path
        self.output_py_path = tk.StringVar()         # Internal: Output/<name>.py
        self.hw_field_path = tk.StringVar()
        self.class_name = tk.StringVar(value="")
        self.num_vectors = tk.IntVar(value=10)
        self.random_seed = tk.IntVar(value=12345)
        self.output_dir = tk.StringVar(value="./test_vectors")
        self.use_wsl = tk.BooleanVar(value=True)
        self.input_type = tk.StringVar(value="N/A")  # "SV", "XML", or "N/A"

        # Message queue for thread-safe logging
        self.log_queue = queue.Queue()

        # Build UI
        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()

        # Start log queue processor
        self._process_log_queue()

        # Load saved config (overrides defaults), then fall back to defaults
        if not self._load_gui_config():
            self._set_default_paths()

        # Save config on window close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # =========================================================================
    # JSON Config Persistence
    # =========================================================================

    def _save_gui_config(self):
        """Save current GUI settings to gui_config.json."""
        config = {
            'input_file_path': self.input_file_path.get(),
            'hw_field_path': self.hw_field_path.get(),
            'class_name': self.class_name.get(),
            'num_vectors': self.num_vectors.get(),
            'random_seed': self.random_seed.get(),
            'output_dir': self.output_dir.get(),
            'use_wsl': self.use_wsl.get(),
        }
        try:
            with open(_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"[WARNING] Could not save GUI config: {e}")

    def _load_gui_config(self):
        """Load GUI settings from gui_config.json.

        Returns True if config was loaded successfully, False otherwise.
        """
        if not os.path.exists(_CONFIG_FILE):
            return False

        try:
            with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Restore values only if the saved file still exists
            input_path = config.get('input_file_path', '')
            if input_path and os.path.exists(input_path):
                self.input_file_path.set(input_path)
                self._resolve_input_file(input_path, log=False)
            else:
                # Saved file gone — fall back to defaults
                self._set_default_paths()

            hw_path = config.get('hw_field_path', '')
            if hw_path and os.path.exists(hw_path):
                self.hw_field_path.set(hw_path)

            self.class_name.set(config.get('class_name', ''))
            self.num_vectors.set(config.get('num_vectors', 10))
            self.random_seed.set(config.get('random_seed', 12345))
            self.output_dir.set(config.get('output_dir', './test_vectors'))
            self.use_wsl.set(config.get('use_wsl', True))

            self._log("Loaded previous session settings from gui_config.json", 'info')
            return True

        except Exception as e:
            print(f"[WARNING] Could not load GUI config: {e}")
            return False

    def _on_close(self):
        """Save config and close the application."""
        self._save_gui_config()
        self.root.destroy()

    # =========================================================================
    # Env.csh
    # =========================================================================

    def _load_env_config(self):
        """
        Load environment configuration from Env.csh.

        Returns a dict with keys:
            WIN_PROJECT_PATH, WSL_PROJECT_PATH, WSL_VENV_PATH,
            WSL_DISTRO, WSL_PYTHON_VERSION
        """
        env_file = os.path.join(self.project_root, "Env.csh")
        config = {}

        if not os.path.exists(env_file):
            print(f"[WARNING] Env.csh not found at: {env_file}")
            print("          Using fallback defaults. Create Env.csh to configure paths.")
            # Fallback defaults
            config['WIN_PROJECT_PATH'] = self.project_root
            config['WSL_PROJECT_PATH'] = self._to_wsl_path(self.project_root)
            config['WSL_VENV_PATH'] = '.wsl_venv'
            config['WSL_DISTRO'] = 'Ubuntu'
            config['WSL_PYTHON_VERSION'] = '3.10'
            return config

        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and blank lines
                    if not line or line.startswith('#'):
                        continue
                    # Parse KEY = VALUE
                    if '=' in line:
                        key, _, value = line.partition('=')
                        key = key.strip()
                        value = value.strip()
                        if key and value:
                            config[key] = value
        except Exception as e:
            print(f"[WARNING] Error reading Env.csh: {e}")

        # Verify required keys exist, fill defaults if missing
        defaults = {
            'WIN_PROJECT_PATH': self.project_root,
            'WSL_PROJECT_PATH': self._to_wsl_path(self.project_root),
            'WSL_VENV_PATH': '.wsl_venv',
            'WSL_DISTRO': 'Ubuntu',
            'WSL_PYTHON_VERSION': '3.10',
        }
        for key, default_val in defaults.items():
            if key not in config:
                print(f"[WARNING] {key} not found in Env.csh, using default: {default_val}")
                config[key] = default_val

        return config

    def _get_output_dir(self):
        """Get the Output directory path, creating it if needed."""
        os.makedirs(self.output_base_dir, exist_ok=True)
        return self.output_base_dir

    def _set_default_paths(self):
        """Set default file paths based on current directory."""
        cwd = self.project_root
        default_sv = os.path.join(cwd, "isp_yuv2rgb.sv")
        default_hw = os.path.join(cwd, "hw_field.txt")

        if os.path.exists(default_sv):
            self.input_file_path.set(default_sv)
            self._resolve_input_file(default_sv, log=False)

        if os.path.exists(default_hw):
            self.hw_field_path.set(default_hw)

    def _create_menu(self):
        """Create menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open SV/XML File...", command=self._browse_input_file)
        file_menu.add_command(label="Open HW Field File...", command=self._browse_hw_field)
        file_menu.add_separator()
        file_menu.add_command(label="Open Output Folder", command=self._open_output_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)

        # Actions menu
        actions_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Actions", menu=actions_menu)
        actions_menu.add_command(label="Convert XML to SV", command=self._run_xml_to_sv)
        actions_menu.add_command(label="Translate SV to PyVSC", command=self._run_translation)
        actions_menu.add_command(label="Test PyVSC Randomization", command=self._run_pyvsc_test)
        actions_menu.add_command(label="Generate Test Vectors", command=self._run_vector_generation)
        actions_menu.add_separator()
        actions_menu.add_command(label="Run All Steps", command=self._run_all)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

    def _create_main_layout(self):
        """Create main application layout."""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left panel - Configuration (scrollable for more content)
        left_frame = ttk.LabelFrame(main_frame, text="Configuration", padding="10")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))

        self._create_config_panel(left_frame)

        # Right panel - Log and Results
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        self._create_log_panel(right_frame)

    @staticmethod
    def _make_right_aligned_entry(parent, textvariable, width=40, **grid_kw):
        """Create an Entry widget whose cursor sits at the right end so
        the *filename* (not the leading path) is always visible."""
        entry = ttk.Entry(parent, textvariable=textvariable, width=width)
        entry.grid(**grid_kw)
        # Move cursor to the end whenever the value changes
        def _scroll_right(*_args):
            entry.xview_moveto(1.0)
        textvariable.trace_add('write', _scroll_right)
        # Also scroll right once now (for the initial value)
        entry.after_idle(lambda: entry.xview_moveto(1.0))
        return entry

    def _create_config_panel(self, parent):
        """Create configuration panel."""
        row = 0

        # === Input Files Section ===
        ttk.Label(parent, text="Input Files", font=('Helvetica', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))
        row += 1

        # Input File (SV or XML)
        input_label_frame = ttk.Frame(parent)
        input_label_frame.grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=2)
        ttk.Label(input_label_frame, text="Input File (.sv / .xml):").pack(side=tk.LEFT)
        self.input_type_label = ttk.Label(
            input_label_frame, textvariable=self.input_type,
            foreground='#569cd6', font=('Helvetica', 9, 'bold'))
        self.input_type_label.pack(side=tk.LEFT, padx=(10, 0))
        row += 1

        self._make_right_aligned_entry(
            parent, self.input_file_path,
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=2)
        ttk.Button(parent, text="Browse...", command=self._browse_input_file).grid(
            row=row, column=2, padx=(5, 0), pady=2)
        row += 1

        # HW Field File
        ttk.Label(parent, text="HW Field File:").grid(row=row, column=0, sticky=tk.W, pady=2)
        row += 1
        self._make_right_aligned_entry(
            parent, self.hw_field_path,
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=2)
        ttk.Button(parent, text="Browse...", command=self._browse_hw_field).grid(
            row=row, column=2, padx=(5, 0), pady=2)
        row += 1

        # Separator
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky=tk.EW, pady=10)
        row += 1

        # === Test Vector Generation Section ===
        ttk.Label(parent, text="Test Vector Generation", font=('Helvetica', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))
        row += 1

        # Class Name
        ttk.Label(parent, text="PyVSC Class Name:").grid(row=row, column=0, sticky=tk.W, pady=2)
        row += 1
        class_entry = ttk.Entry(parent, textvariable=self.class_name, width=40)
        class_entry.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=2)
        ttk.Button(parent, text="Detect", command=self._detect_class_name).grid(
            row=row, column=2, padx=(5, 0), pady=2)
        row += 1

        # Number of Vectors
        ttk.Label(parent, text="Number of Vectors:").grid(row=row, column=0, sticky=tk.W, pady=2)
        ttk.Spinbox(parent, from_=1, to=10000, textvariable=self.num_vectors, width=10).grid(
            row=row, column=1, sticky=tk.W, pady=2)
        row += 1

        # Random Seed
        ttk.Label(parent, text="Random Seed:").grid(row=row, column=0, sticky=tk.W, pady=2)
        ttk.Entry(parent, textvariable=self.random_seed, width=12).grid(
            row=row, column=1, sticky=tk.W, pady=2)
        row += 1

        # Output Directory
        ttk.Label(parent, text="Output Directory:").grid(row=row, column=0, sticky=tk.W, pady=2)
        row += 1
        self._make_right_aligned_entry(
            parent, self.output_dir,
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=2)
        ttk.Button(parent, text="Browse...", command=self._browse_output_dir).grid(
            row=row, column=2, padx=(5, 0), pady=2)
        row += 1

        # Separator
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky=tk.EW, pady=10)
        row += 1

        # === Options Section ===
        ttk.Label(parent, text="Options", font=('Helvetica', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))
        row += 1

        # Use WSL checkbox
        ttk.Checkbutton(parent, text="Use WSL for PyVSC execution",
                        variable=self.use_wsl).grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=2)
        row += 1

        # Separator
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=3, sticky=tk.EW, pady=10)
        row += 1

        # === Action Buttons ===
        ttk.Label(parent, text="Actions", font=('Helvetica', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))
        row += 1

        # Row 1: XML Convert + Translate
        btn_frame1 = ttk.Frame(parent)
        btn_frame1.grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=2)

        self.xml_convert_btn = ttk.Button(
            btn_frame1, text="0. XML\u2192SV", command=self._run_xml_to_sv, width=15)
        self.xml_convert_btn.pack(side=tk.LEFT, padx=2)

        self.translate_btn = ttk.Button(
            btn_frame1, text="1. Translate", command=self._run_translation, width=15)
        self.translate_btn.pack(side=tk.LEFT, padx=2)
        self.test_btn = ttk.Button(
            btn_frame1, text="2. Test PyVSC", command=self._run_pyvsc_test, width=15)
        self.test_btn.pack(side=tk.LEFT, padx=2)
        row += 1

        # Row 2: Generate
        btn_frame2 = ttk.Frame(parent)
        btn_frame2.grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=2)

        self.generate_btn = ttk.Button(
            btn_frame2, text="3. Generate", command=self._run_vector_generation, width=15)
        self.generate_btn.pack(side=tk.LEFT, padx=2)
        row += 1

        # Run All button
        self.run_all_btn = ttk.Button(parent, text="Run All Steps", command=self._run_all, width=47)
        self.run_all_btn.grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=10)

        # Collect all action buttons for state management
        self._action_buttons = [
            self.xml_convert_btn, self.translate_btn,
            self.test_btn, self.generate_btn, self.run_all_btn,
        ]
        row += 1

        # Clear Log button
        ttk.Button(parent, text="Clear Log", command=self._clear_log, width=47).grid(
            row=row, column=0, columnspan=3, sticky=tk.EW, pady=2)

    def _create_log_panel(self, parent):
        """Create log and results panel."""
        # Log section
        log_frame = ttk.LabelFrame(parent, text="Log Output", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)

        # Log text widget with scrollbar
        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=('Consolas', 9),
            bg='#1e1e1e', fg='#d4d4d4', insertbackground='white'
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Configure text tags for colored output
        self.log_text.tag_configure('info', foreground='#d4d4d4')
        self.log_text.tag_configure('success', foreground='#4ec9b0')
        self.log_text.tag_configure('warning', foreground='#dcdcaa')
        self.log_text.tag_configure('error', foreground='#f14c4c')
        self.log_text.tag_configure('header', foreground='#569cd6', font=('Consolas', 9, 'bold'))
        self.log_text.tag_configure('command', foreground='#ce9178')

        # Results summary section
        results_frame = ttk.LabelFrame(parent, text="Results Summary", padding="5")
        results_frame.pack(fill=tk.X, pady=(5, 0))

        self.results_text = tk.Text(results_frame, height=4, font=('Consolas', 9),
                                     bg='#252526', fg='#d4d4d4')
        self.results_text.pack(fill=tk.X)
        self.results_text.insert(tk.END, "No results yet. Run the translation and tests to see results here.")
        self.results_text.config(state=tk.DISABLED)

    def _create_status_bar(self):
        """Create status bar at bottom."""
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var,
                               relief=tk.SUNKEN, anchor=tk.W, padding=(5, 2))
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # =========================================================================
    # File Browsing
    # =========================================================================

    def _browse_input_file(self):
        """Browse for SystemVerilog or XML file."""
        filename = filedialog.askopenfilename(
            title="Select SystemVerilog or XML File",
            filetypes=[
                ("SV / XML files", "*.sv *.xml"),
                ("SystemVerilog files", "*.sv"),
                ("XML files", "*.xml"),
                ("All files", "*.*"),
            ]
        )
        if filename:
            self.input_file_path.set(filename)
            self._resolve_input_file(filename)

    def _resolve_input_file(self, filepath, log=True):
        """
        Determine input type and set internal resolved paths accordingly.

        If .xml: SV path = Output/<name>.sv, PyVSC path = Output/<name>.py
        If .sv:  SV path = filepath,         PyVSC path = Output/<name>.py
        """
        ext = os.path.splitext(filepath)[1].lower()
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        output_dir = self._get_output_dir()

        if ext == '.xml':
            self.input_type.set("XML")
            sv_path = os.path.join(output_dir, base_name + ".sv")
            self.sv_file_path.set(sv_path)
            self.output_py_path.set(os.path.join(output_dir, base_name + ".py"))
            if log:
                self._log(f"XML file selected: {os.path.basename(filepath)}", 'info')
                self._log(f"  SV output -> Output/{base_name}.sv", 'info')
                self._log(f"  PyVSC output -> Output/{base_name}.py", 'info')
        elif ext == '.sv':
            self.input_type.set("SV")
            self.sv_file_path.set(filepath)
            self.output_py_path.set(os.path.join(output_dir, base_name + ".py"))
            if log:
                self._log(f"SV file selected: {os.path.basename(filepath)}", 'info')
                self._log(f"  PyVSC output -> Output/{base_name}.py", 'info')
        else:
            self.input_type.set("N/A")
            self.sv_file_path.set(filepath)
            self.output_py_path.set(os.path.join(output_dir, base_name + ".py"))
            if log:
                self._log(f"Unknown file type: {ext}. Treating as SV.", 'warning')

        self._detect_class_name()

    def _browse_hw_field(self):
        """Browse for HW field file and validate against SV fields."""
        filename = filedialog.askopenfilename(
            title="Select HW Field File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            self.hw_field_path.set(filename)
            self._validate_hw_fields(filename)

    def _browse_output_dir(self):
        """Browse for output directory."""
        dirname = filedialog.askdirectory(title="Select Output Directory")
        if dirname:
            self.output_dir.set(dirname)

    def _open_output_folder(self):
        """Open the Output folder in file explorer."""
        output_dir = self._get_output_dir()
        try:
            if sys.platform == 'win32':
                os.startfile(output_dir)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', output_dir])
            else:
                subprocess.Popen(['xdg-open', output_dir])
        except Exception as e:
            self._log(f"Could not open output folder: {e}", 'warning')

    # =========================================================================
    # HW Field Validation
    # =========================================================================

    def _validate_hw_fields(self, hw_path):
        """Validate hw_field.txt entries against fields in the selected SV file.

        Parses field names from hw_field.txt, extracts 'rand ... <name>;'
        declarations from the SV source, and warns about any hw_field
        entries that have no matching SV field.
        """
        sv_path = self.sv_file_path.get()
        if not sv_path or not os.path.exists(sv_path):
            self._log("SV file not available yet; skipping HW field validation.", 'info')
            return

        # Parse field names from hw_field.txt (first token on non-comment lines)
        hw_fields = set()
        try:
            with open(hw_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    # Remove inline comments, take first whitespace-separated token
                    token = line.split('#')[0].split()[0]
                    hw_fields.add(token)
        except Exception as e:
            self._log(f"Could not read HW field file: {e}", 'error')
            return

        if not hw_fields:
            messagebox.showwarning(
                "HW Field Validation",
                "The HW field file is empty or contains no field entries.\n\n"
                "Please check the file format:\n"
                "  field_name default_value"
            )
            return

        # Parse field names from SV file (rand/randc declarations)
        sv_fields = set()
        try:
            with open(sv_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Match:  rand <type> [qualifiers] <name> ;
            #  e.g.   rand bit [7:0] my_field;
            #         rand int unsigned width;
            #         rand int signed c00;
            for m in re.finditer(
                r'\b(?:rand|randc)\s+(?:bit|logic|int|byte|shortint|longint|integer)\b'
                r'[^;]*?(\w+)\s*;', content
            ):
                sv_fields.add(m.group(1))
            # Also match rand enum fields: rand <enum_type> <name>;
            for m in re.finditer(r'\brand\s+\w+\s+(\w+)\s*;', content):
                sv_fields.add(m.group(1))
        except Exception as e:
            self._log(f"Could not parse SV file for field names: {e}", 'error')
            return

        # Compare
        missing = hw_fields - sv_fields
        if missing:
            missing_list = ', '.join(sorted(missing))
            self._log(
                f"HW field validation: {len(missing)} field(s) not found in SV: {missing_list}",
                'warning'
            )
            messagebox.showwarning(
                "HW Field Validation",
                f"{len(missing)} field(s) in hw_field.txt are NOT present "
                f"in the selected SV file:\n\n"
                f"{missing_list}\n\n"
                f"Please check hw_field.txt for typos or stale entries."
            )
        else:
            self._log(
                f"HW field validation: all {len(hw_fields)} field(s) found in SV.",
                'success'
            )

    # =========================================================================
    # Class Name Detection
    # =========================================================================

    def _detect_class_name(self):
        """Detect class name from SV file."""
        sv_path = self.sv_file_path.get()
        if not sv_path or not os.path.exists(sv_path):
            # For XML files, the SV file may not exist yet
            input_path = self.input_file_path.get()
            if input_path and os.path.exists(input_path) and input_path.lower().endswith('.xml'):
                self._log("SV file not generated yet. Class name will be detected after XML\u2192SV conversion.", 'info')
            return

        try:
            with open(sv_path, 'r') as f:
                content = f.read()

            # Look for class definitions
            matches = re.findall(r'class\s+(\w+)', content)
            if matches:
                # Convert to PascalCase (as the translator does)
                class_name = matches[0]
                pascal_name = ''.join(word.capitalize() for word in class_name.split('_'))
                self.class_name.set(pascal_name)
                self._log(f"Detected class: {class_name} -> {pascal_name}", 'info')
        except Exception as e:
            self._log(f"Could not detect class name: {e}", 'warning')

    # =========================================================================
    # Logging
    # =========================================================================

    def _log(self, message, tag='info'):
        """Add message to log queue (thread-safe)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put((f"[{timestamp}] {message}\n", tag))

    def _process_log_queue(self):
        """Process messages from log queue."""
        try:
            while True:
                message, tag = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, message, tag)
                self.log_text.see(tk.END)
        except queue.Empty:
            pass
        self.root.after(100, self._process_log_queue)

    def _clear_log(self):
        """Clear log output."""
        self.log_text.delete(1.0, tk.END)

    def _set_buttons_state(self, state):
        """Enable or disable all action buttons (thread-safe via root.after).

        Args:
            state: 'normal' to enable, 'disabled' to disable.
        """
        def _apply():
            for btn in self._action_buttons:
                btn.config(state=state)
        # Schedule on main thread — Tk widgets must only be touched there
        self.root.after_idle(_apply)

    def _update_results(self, results):
        """Update results summary."""
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, results)
        self.results_text.config(state=tk.DISABLED)

    # =========================================================================
    # Command Execution
    # =========================================================================

    def _run_command(self, cmd, description, use_wsl=False, cwd=None):
        """Run a command and capture output.

        Uses PYTHONUNBUFFERED=1 and bufsize=1 to prevent the massive
        slowdown caused by Python's default full-buffering when stdout
        is redirected to a pipe.  A dedicated reader thread streams
        output to the log without blocking the caller.
        """
        self._log(f"{'='*50}", 'header')
        self._log(f"{description}", 'header')
        self._log(f"{'='*50}", 'header')

        if use_wsl:
            # Read paths from Env.csh config
            wsl_project_path = self.env_config['WSL_PROJECT_PATH']
            wsl_venv_path = self.env_config['WSL_VENV_PATH']
            wsl_distro = self.env_config['WSL_DISTRO']
            wsl_cmd = (
                f'wsl -d {wsl_distro} -- bash -lc '
                f'"cd {wsl_project_path} '
                f'&& source {wsl_venv_path}/bin/activate && {cmd}"'
            )
            self._log(f"Command (WSL): {cmd}", 'command')
        else:
            wsl_cmd = cmd
            self._log(f"Command: {cmd}", 'command')

        self._log("")

        # Determine working directory
        if cwd is None:
            cwd = self.project_root

        try:
            # Force unbuffered stdout in child Python processes.
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'

            process = subprocess.Popen(
                wsl_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd,
                env=env,
                bufsize=1        # line-buffered on the reading side
            )

            # Read output on a dedicated thread so the caller is not
            # blocked by slow I/O and the GUI stays responsive.
            def _reader():
                for line in process.stdout:
                    line = line.rstrip()
                    lower = line.lower()
                    if 'error' in lower or 'exception' in lower:
                        self._log(line, 'error')
                    elif 'warning' in lower:
                        self._log(line, 'warning')
                    elif 'success' in lower or 'complete' in lower:
                        self._log(line, 'success')
                    else:
                        self._log(line, 'info')

            reader_thread = threading.Thread(target=_reader, daemon=True)
            reader_thread.start()
            reader_thread.join()        # wait for all output to be read
            process.wait()

            if process.returncode == 0:
                self._log(f"\n{description} - COMPLETED SUCCESSFULLY", 'success')
                return True
            else:
                self._log(f"\n{description} - FAILED (exit code: {process.returncode})", 'error')
                return False

        except Exception as e:
            self._log(f"Error running command: {e}", 'error')
            return False

    def _to_wsl_path(self, win_path):
        """Convert a Windows path to a WSL path."""
        # e.g. C:\Users\foo\bar -> /mnt/c/Users/foo/bar
        path = win_path.replace('\\', '/')
        if len(path) >= 2 and path[1] == ':':
            drive = path[0].lower()
            path = f'/mnt/{drive}{path[2:]}'
        return path

    # =========================================================================
    # Step 0: XML to SV Conversion
    # =========================================================================

    def _run_xml_to_sv(self):
        """Run XML to SV conversion."""
        input_path = self.input_file_path.get()

        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("Error", "Please select a valid input file.")
            return

        if not input_path.lower().endswith('.xml'):
            messagebox.showinfo("Info", "Input is already an SV file. Skipping XML\u2192SV conversion.")
            return

        self.status_var.set("Converting XML to SV...")
        self._set_buttons_state('disabled')

        def run():
            try:
                sv_output_path = self.sv_file_path.get()
                xml_converter_script = os.path.join(self.project_root, "XML_to_sv_Converter.py")

                if not os.path.exists(xml_converter_script):
                    self._log("ERROR: XML_to_sv_Converter.py not found in project directory!", 'error')
                    self._log(f"Expected at: {xml_converter_script}", 'error')
                    return

                cmd = (
                    f'python "{xml_converter_script}" '
                    f'"{input_path}" '
                    f'"{sv_output_path}"'
                )
                success = self._run_command(
                    cmd, "Step 0: XML to SV Conversion", use_wsl=False,
                    cwd=self.project_root
                )

                if success:
                    self._log(f"SV file generated: {sv_output_path}", 'success')
                    self._update_results(f"XML\u2192SV conversion completed!\nOutput: {sv_output_path}")
                    # Re-detect class name from the newly generated SV file
                    self._detect_class_name()
                else:
                    self._log("XML to SV conversion failed.", 'error')
            finally:
                self.status_var.set("Ready")
                self._set_buttons_state('normal')

        threading.Thread(target=run, daemon=True).start()

    def _run_xml_to_sv_sync(self):
        """Run XML to SV conversion synchronously (for _run_all pipeline)."""
        input_path = self.input_file_path.get()

        if not input_path.lower().endswith('.xml'):
            self._log("Input is SV file. Skipping XML\u2192SV conversion.", 'info')
            return True

        if not input_path or not os.path.exists(input_path):
            self._log("Error: XML file not found.", 'error')
            return False

        sv_output_path = self.sv_file_path.get()
        xml_converter_script = os.path.join(self.project_root, "XML_to_sv_Converter.py")

        if not os.path.exists(xml_converter_script):
            self._log("ERROR: XML_to_sv_Converter.py not found in project directory!", 'error')
            self._log(f"Expected at: {xml_converter_script}", 'error')
            return False

        cmd = (
            f'python "{xml_converter_script}" '
            f'"{input_path}" '
            f'"{sv_output_path}"'
        )
        success = self._run_command(
            cmd, "Step 0: XML to SV Conversion", use_wsl=False,
            cwd=self.project_root
        )

        if success:
            self._log(f"SV file generated: {sv_output_path}", 'success')
            self._detect_class_name()

        return success

    # =========================================================================
    # Step 1: SV to PyVSC Translation
    # =========================================================================

    def _run_translation(self):
        """Run SV to PyVSC translation."""
        sv_path = self.sv_file_path.get()

        if not sv_path or not os.path.exists(sv_path):
            messagebox.showerror("Error",
                                 "SV file not found. If using XML input, run 'XML\u2192SV' first.")
            return

        self.status_var.set("Running translation...")
        self._set_buttons_state('disabled')

        def run():
            try:
                success = self._run_translation_sync()
            finally:
                self.status_var.set("Ready")
                self._set_buttons_state('normal')

        threading.Thread(target=run, daemon=True).start()

    def _run_translation_sync(self):
        """Run SV to PyVSC translation synchronously."""
        sv_path = self.sv_file_path.get()
        py_path = self.output_py_path.get()

        translator_script = os.path.join(self.project_root, "sv_to_pyvsc.py")
        cmd = f'python "{translator_script}" "{sv_path}" -o "{py_path}"'
        success = self._run_command(
            cmd, "Step 1: SV to PyVSC Translation", use_wsl=False,
            cwd=self.project_root
        )

        if success:
            self._update_results(f"Translation completed!\nOutput: {py_path}")
            self._detect_class_name()

        return success

    # =========================================================================
    # Step 2: PyVSC Randomization Test
    # =========================================================================

    def _run_pyvsc_test(self):
        """Run PyVSC randomization test."""
        py_path = self.output_py_path.get()

        if not py_path or not os.path.exists(py_path):
            messagebox.showerror("Error", "Please run translation first or select a valid Python file.")
            return

        if not self.use_wsl.get():
            messagebox.showwarning("Warning", "PyVSC tests require WSL. Enabling WSL mode.")
            self.use_wsl.set(True)

        self.status_var.set("Running PyVSC test...")
        self._set_buttons_state('disabled')

        def run():
            try:
                success = self._run_pyvsc_test_sync()
            finally:
                self.status_var.set("Ready")
                self._set_buttons_state('normal')

        threading.Thread(target=run, daemon=True).start()

    def _run_pyvsc_test_sync(self):
        """Run PyVSC randomization test synchronously."""
        py_path = self.output_py_path.get()

        # Convert the Output/ path to WSL-friendly path for execution
        wsl_output_dir = self._to_wsl_path(self._get_output_dir())
        py_filename = os.path.basename(py_path)

        # Run the PyVSC file from the Output directory
        cmd = f"cd {wsl_output_dir} && python {py_filename}"
        success = self._run_command(
            cmd, "Step 2: PyVSC Randomization Test (from Output/)", use_wsl=True
        )

        if success:
            self._update_results("PyVSC randomization test passed!")
        else:
            self._update_results("PyVSC randomization test had issues. Check log for details.")

        return success

    # =========================================================================
    # Step 3: Test Vector Generation
    # =========================================================================

    def _run_vector_generation(self):
        """Run test vector generation."""
        py_path = self.output_py_path.get()
        hw_path = self.hw_field_path.get()
        class_name = self.class_name.get()

        if not py_path or not os.path.exists(py_path):
            messagebox.showerror("Error", "Please run translation first.")
            return

        if not hw_path or not os.path.exists(hw_path):
            messagebox.showerror("Error", "Please select a valid HW field file.")
            return

        if not class_name:
            messagebox.showerror("Error", "Please specify the PyVSC class name.")
            return

        self.status_var.set("Generating test vectors...")
        self._set_buttons_state('disabled')

        def run():
            try:
                success = self._run_vector_generation_sync()
            finally:
                self.status_var.set("Ready")
                self._set_buttons_state('normal')

        threading.Thread(target=run, daemon=True).start()

    def _run_vector_generation_sync(self):
        """Run test vector generation synchronously."""
        py_path = self.output_py_path.get()
        hw_path = self.hw_field_path.get()
        class_name = self.class_name.get()
        num_vectors = self.num_vectors.get()
        seed = self.random_seed.get()
        output_dir = self.output_dir.get()

        module_name = os.path.splitext(os.path.basename(py_path))[0]
        # Use full HW field path so WSL can find it regardless of cwd
        wsl_hw_path = self._to_wsl_path(hw_path)

        # Run from the Output directory so the module can be imported
        wsl_output_dir = self._to_wsl_path(self._get_output_dir())
        wsl_project_root = self._to_wsl_path(self.project_root)

        # Convert output directory to WSL path if it's a Windows absolute path
        wsl_output_arg = output_dir
        if output_dir and len(output_dir) >= 2 and output_dir[1] == ':':
            wsl_output_arg = self._to_wsl_path(output_dir)

        cmd = (
            f"cd {wsl_output_dir} && "
            f"python {wsl_project_root}/generate_test_vectors.py "
            f"{module_name} {class_name} {wsl_hw_path} {num_vectors} {wsl_output_arg} --seed {seed}"
        )
        success = self._run_command(cmd, "Step 3: Test Vector Generation", use_wsl=True)

        if success:
            self._update_results(
                f"Test vector generation completed!\n"
                f"Generated: {num_vectors} vectors\n"
                f"Output directory: {output_dir}"
            )

        return success

    # =========================================================================
    # Run All Steps
    # =========================================================================

    def _run_all(self):
        """Run all steps in sequence."""
        self.status_var.set("Running all steps...")
        self._set_buttons_state('disabled')
        self._clear_log()

        def run():
            try:
                input_path = self.input_file_path.get()
                is_xml = input_path.lower().endswith('.xml') if input_path else False

                if not input_path or not os.path.exists(input_path):
                    self._log("Error: Please select a valid input file (.sv or .xml).", 'error')
                    return

                # Step 0: XML to SV (only if XML input)
                success0 = True
                if is_xml:
                    success0 = self._run_xml_to_sv_sync()
                    if not success0:
                        self._log("XML\u2192SV conversion failed. Stopping.", 'error')
                        return

                # Step 1: SV to PyVSC Translation
                sv_path = self.sv_file_path.get()
                if not sv_path or not os.path.exists(sv_path):
                    self._log(f"Error: SV file not found at {sv_path}", 'error')
                    return

                success1 = self._run_translation_sync()

                if not success1:
                    self._log("Translation failed. Stopping.", 'error')
                    return

                # Step 2: PyVSC Test (from Output/ directory)
                success2 = self._run_pyvsc_test_sync()

                # Step 3: Vector Generation (if HW file exists)
                hw_path = self.hw_field_path.get()
                class_name = self.class_name.get()
                success3 = False

                if hw_path and os.path.exists(hw_path) and class_name:
                    success3 = self._run_vector_generation_sync()
                else:
                    self._log("Skipping vector generation (missing HW field file or class name)", 'warning')

                # Summary
                self._log("\n" + "="*50, 'header')
                self._log("SUMMARY", 'header')
                self._log("="*50, 'header')

                if is_xml:
                    self._log(
                        f"Step 0 (XML\u2192SV):         {'PASS' if success0 else 'FAIL'}",
                        'success' if success0 else 'error')

                self._log(f"Step 1 (Translation):     {'PASS' if success1 else 'FAIL'}",
                          'success' if success1 else 'error')
                self._log(f"Step 2 (PyVSC Test):      {'PASS' if success2 else 'FAIL/WARNINGS'}",
                          'success' if success2 else 'warning')
                self._log(f"Step 3 (Vector Gen):      {'PASS' if success3 else 'SKIPPED/FAIL'}",
                          'success' if success3 else 'warning')
                self._log(f"\nOutput directory: {self._get_output_dir()}", 'info')

                results = ""
                if is_xml:
                    results += f"XML\u2192SV: {'PASS' if success0 else 'FAIL'}\n"
                results += f"Translation: {'PASS' if success1 else 'FAIL'}\n"
                results += f"PyVSC Test: {'PASS' if success2 else 'FAIL/WARNINGS'}\n"
                results += f"Vector Generation: {'PASS' if success3 else 'SKIPPED'}\n"
                results += f"Output: {self._get_output_dir()}"
                if success3:
                    results += f"\nVectors: {self.output_dir.get()}"

                self._update_results(results)
            finally:
                self.status_var.set("Ready")
                self._set_buttons_state('normal')

        threading.Thread(target=run, daemon=True).start()

    # =========================================================================
    # About
    # =========================================================================

    def _show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About",
            "SV / XML to PyVSC Translation Tool\n\n"
            "Version: 2.1\n\n"
            "This tool converts SystemVerilog or XML constraint models to PyVSC "
            "Python code and generates randomized test vectors.\n\n"
            "Pipeline:\n"
            "  XML \u2192 SV \u2192 PyVSC (.py) \u2192 Test \u2192 Vectors\n\n"
            "Features:\n"
            "- XML to SV conversion (via XML_to_sv_Converter.py)\n"
            "- SV to PyVSC translation\n"
            "- PyVSC randomization testing\n"
            "- Bulk test vector generation\n"
            f"- All output in: Output/\n"
            "- Session settings saved automatically\n\n"
            "Developed for Samsung Hardware Verification"
        )


def main():
    root = tk.Tk()

    # Set style
    style = ttk.Style()
    style.theme_use('clam')

    app = SVtoPyVSCGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
