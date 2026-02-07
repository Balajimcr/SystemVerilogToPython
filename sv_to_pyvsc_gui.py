#!/usr/bin/env python3
"""
SystemVerilog to PyVSC Translation GUI

A Tkinter-based GUI for:
1. Browsing and selecting SystemVerilog (.sv) files
2. Translating SV to PyVSC Python code
3. Running PyVSC randomization tests
4. Generating test vectors
5. Displaying results and logs

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
from datetime import datetime
from pathlib import Path


class SVtoPyVSCGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SystemVerilog to PyVSC Translation Tool")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)

        # Variables
        self.sv_file_path = tk.StringVar()
        self.output_py_path = tk.StringVar()
        self.hw_field_path = tk.StringVar()
        self.class_name = tk.StringVar(value="")
        self.num_vectors = tk.IntVar(value=10)
        self.random_seed = tk.IntVar(value=12345)
        self.output_dir = tk.StringVar(value="./test_vectors")
        self.use_wsl = tk.BooleanVar(value=True)

        # Message queue for thread-safe logging
        self.log_queue = queue.Queue()

        # Build UI
        self._create_menu()
        self._create_main_layout()
        self._create_status_bar()

        # Start log queue processor
        self._process_log_queue()

        # Set default paths
        self._set_default_paths()

    def _set_default_paths(self):
        """Set default file paths based on current directory."""
        cwd = os.getcwd()
        default_sv = os.path.join(cwd, "isp_yuv2rgb.sv")
        default_hw = os.path.join(cwd, "hw_field.txt")

        if os.path.exists(default_sv):
            self.sv_file_path.set(default_sv)
            self.output_py_path.set(default_sv.replace(".sv", ".py"))

        if os.path.exists(default_hw):
            self.hw_field_path.set(default_hw)

    def _create_menu(self):
        """Create menu bar."""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Open SV File...", command=self._browse_sv_file)
        file_menu.add_command(label="Open HW Field File...", command=self._browse_hw_field)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

        # Actions menu
        actions_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Actions", menu=actions_menu)
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

        # Left panel - Configuration
        left_frame = ttk.LabelFrame(main_frame, text="Configuration", padding="10")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))

        self._create_config_panel(left_frame)

        # Right panel - Log and Results
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        self._create_log_panel(right_frame)

    def _create_config_panel(self, parent):
        """Create configuration panel."""
        row = 0

        # === Input Files Section ===
        ttk.Label(parent, text="Input Files", font=('Helvetica', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, sticky=tk.W, pady=(0, 5))
        row += 1

        # SV File
        ttk.Label(parent, text="SystemVerilog File:").grid(row=row, column=0, sticky=tk.W, pady=2)
        row += 1
        sv_entry = ttk.Entry(parent, textvariable=self.sv_file_path, width=40)
        sv_entry.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=2)
        ttk.Button(parent, text="Browse...", command=self._browse_sv_file).grid(
            row=row, column=2, padx=(5, 0), pady=2)
        row += 1

        # Output Python File
        ttk.Label(parent, text="Output Python File:").grid(row=row, column=0, sticky=tk.W, pady=2)
        row += 1
        ttk.Entry(parent, textvariable=self.output_py_path, width=40).grid(
            row=row, column=0, columnspan=2, sticky=tk.EW, pady=2)
        ttk.Button(parent, text="Browse...", command=self._browse_output_py).grid(
            row=row, column=2, padx=(5, 0), pady=2)
        row += 1

        # HW Field File
        ttk.Label(parent, text="HW Field File:").grid(row=row, column=0, sticky=tk.W, pady=2)
        row += 1
        ttk.Entry(parent, textvariable=self.hw_field_path, width=40).grid(
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
        ttk.Entry(parent, textvariable=self.output_dir, width=40).grid(
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

        btn_frame = ttk.Frame(parent)
        btn_frame.grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=5)

        ttk.Button(btn_frame, text="1. Translate", command=self._run_translation, width=15).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="2. Test PyVSC", command=self._run_pyvsc_test, width=15).pack(
            side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="3. Generate", command=self._run_vector_generation, width=15).pack(
            side=tk.LEFT, padx=2)
        row += 1

        # Run All button
        run_all_btn = ttk.Button(parent, text="Run All Steps", command=self._run_all, width=47)
        run_all_btn.grid(row=row, column=0, columnspan=3, sticky=tk.EW, pady=10)
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

    def _browse_sv_file(self):
        """Browse for SystemVerilog file."""
        filename = filedialog.askopenfilename(
            title="Select SystemVerilog File",
            filetypes=[("SystemVerilog files", "*.sv"), ("All files", "*.*")]
        )
        if filename:
            self.sv_file_path.set(filename)
            # Auto-set output path
            self.output_py_path.set(filename.replace(".sv", ".py"))
            self._detect_class_name()

    def _browse_output_py(self):
        """Browse for output Python file."""
        filename = filedialog.asksaveasfilename(
            title="Save Python File As",
            defaultextension=".py",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        if filename:
            self.output_py_path.set(filename)

    def _browse_hw_field(self):
        """Browse for HW field file."""
        filename = filedialog.askopenfilename(
            title="Select HW Field File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            self.hw_field_path.set(filename)

    def _browse_output_dir(self):
        """Browse for output directory."""
        dirname = filedialog.askdirectory(title="Select Output Directory")
        if dirname:
            self.output_dir.set(dirname)

    def _detect_class_name(self):
        """Detect class name from SV file."""
        sv_path = self.sv_file_path.get()
        if not sv_path or not os.path.exists(sv_path):
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

    def _update_results(self, results):
        """Update results summary."""
        self.results_text.config(state=tk.NORMAL)
        self.results_text.delete(1.0, tk.END)
        self.results_text.insert(tk.END, results)
        self.results_text.config(state=tk.DISABLED)

    def _run_command(self, cmd, description, use_wsl=False):
        """Run a command and capture output."""
        self._log(f"{'='*50}", 'header')
        self._log(f"{description}", 'header')
        self._log(f"{'='*50}", 'header')

        if use_wsl:
            # Convert Windows path to WSL path
            wsl_cmd = f'wsl bash -c "cd /mnt/c/D/Project_Files/Samsung/SystemVerilogToPython && source .wsl_venv/bin/activate && {cmd}"'
            self._log(f"Command (WSL): {cmd}", 'command')
        else:
            wsl_cmd = cmd
            self._log(f"Command: {cmd}", 'command')

        self._log("")

        try:
            process = subprocess.Popen(
                wsl_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=os.path.dirname(self.sv_file_path.get()) or os.getcwd()
            )

            # Read output line by line
            for line in process.stdout:
                line = line.rstrip()
                if 'error' in line.lower() or 'exception' in line.lower():
                    self._log(line, 'error')
                elif 'warning' in line.lower():
                    self._log(line, 'warning')
                elif 'success' in line.lower() or 'complete' in line.lower():
                    self._log(line, 'success')
                else:
                    self._log(line, 'info')

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

    def _run_translation(self):
        """Run SV to PyVSC translation."""
        sv_path = self.sv_file_path.get()
        py_path = self.output_py_path.get()

        if not sv_path or not os.path.exists(sv_path):
            messagebox.showerror("Error", "Please select a valid SystemVerilog file.")
            return

        self.status_var.set("Running translation...")

        def run():
            cmd = f"python sv_to_pyvsc.py \"{os.path.basename(sv_path)}\" -o \"{os.path.basename(py_path)}\""
            success = self._run_command(cmd, "Step 1: Translation", use_wsl=False)

            if success:
                self._update_results(f"Translation completed!\nOutput: {py_path}")
                self._detect_class_name()

            self.status_var.set("Ready")

        threading.Thread(target=run, daemon=True).start()

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

        def run():
            cmd = f"python {os.path.basename(py_path)}"
            success = self._run_command(cmd, "Step 2: PyVSC Randomization Test", use_wsl=True)

            if success:
                self._update_results("PyVSC randomization test passed!")
            else:
                self._update_results("PyVSC randomization test had issues. Check log for details.")

            self.status_var.set("Ready")

        threading.Thread(target=run, daemon=True).start()

    def _run_vector_generation(self):
        """Run test vector generation."""
        py_path = self.output_py_path.get()
        hw_path = self.hw_field_path.get()
        class_name = self.class_name.get()
        num_vectors = self.num_vectors.get()
        seed = self.random_seed.get()
        output_dir = self.output_dir.get()

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

        def run():
            module_name = os.path.basename(py_path).replace('.py', '')
            hw_file = os.path.basename(hw_path)

            cmd = f"python generate_test_vectors.py {module_name} {class_name} {hw_file} {num_vectors} {output_dir} --seed {seed}"
            success = self._run_command(cmd, "Step 3: Test Vector Generation", use_wsl=True)

            if success:
                self._update_results(
                    f"Test vector generation completed!\n"
                    f"Generated: {num_vectors} vectors\n"
                    f"Output directory: {output_dir}"
                )

            self.status_var.set("Ready")

        threading.Thread(target=run, daemon=True).start()

    def _run_all(self):
        """Run all steps in sequence."""
        self.status_var.set("Running all steps...")
        self._clear_log()

        def run():
            # Step 1: Translation
            sv_path = self.sv_file_path.get()
            py_path = self.output_py_path.get()

            if not sv_path or not os.path.exists(sv_path):
                self._log("Error: Please select a valid SystemVerilog file.", 'error')
                self.status_var.set("Ready")
                return

            cmd = f"python sv_to_pyvsc.py \"{os.path.basename(sv_path)}\" -o \"{os.path.basename(py_path)}\""
            success1 = self._run_command(cmd, "Step 1: Translation", use_wsl=False)

            if not success1:
                self._log("Translation failed. Stopping.", 'error')
                self.status_var.set("Ready")
                return

            self._detect_class_name()

            # Step 2: PyVSC Test
            cmd = f"python {os.path.basename(py_path)}"
            success2 = self._run_command(cmd, "Step 2: PyVSC Randomization Test", use_wsl=True)

            # Step 3: Vector Generation (if HW file exists)
            hw_path = self.hw_field_path.get()
            class_name = self.class_name.get()
            success3 = False

            if hw_path and os.path.exists(hw_path) and class_name:
                module_name = os.path.basename(py_path).replace('.py', '')
                hw_file = os.path.basename(hw_path)
                num_vectors = self.num_vectors.get()
                seed = self.random_seed.get()
                output_dir = self.output_dir.get()

                cmd = f"python generate_test_vectors.py {module_name} {class_name} {hw_file} {num_vectors} {output_dir} --seed {seed}"
                success3 = self._run_command(cmd, "Step 3: Test Vector Generation", use_wsl=True)
            else:
                self._log("Skipping vector generation (missing HW field file or class name)", 'warning')

            # Summary
            self._log("\n" + "="*50, 'header')
            self._log("SUMMARY", 'header')
            self._log("="*50, 'header')
            self._log(f"Step 1 (Translation):     {'PASS' if success1 else 'FAIL'}",
                      'success' if success1 else 'error')
            self._log(f"Step 2 (PyVSC Test):      {'PASS' if success2 else 'FAIL/WARNINGS'}",
                      'success' if success2 else 'warning')
            self._log(f"Step 3 (Vector Gen):      {'PASS' if success3 else 'SKIPPED/FAIL'}",
                      'success' if success3 else 'warning')

            results = f"Translation: {'PASS' if success1 else 'FAIL'}\n"
            results += f"PyVSC Test: {'PASS' if success2 else 'FAIL/WARNINGS'}\n"
            results += f"Vector Generation: {'PASS' if success3 else 'SKIPPED'}\n"
            if success3:
                results += f"Output: {self.output_dir.get()}"

            self._update_results(results)
            self.status_var.set("Ready")

        threading.Thread(target=run, daemon=True).start()

    def _show_about(self):
        """Show about dialog."""
        messagebox.showinfo(
            "About",
            "SystemVerilog to PyVSC Translation Tool\n\n"
            "Version: 1.0\n\n"
            "This tool converts SystemVerilog constraint models to PyVSC Python code "
            "and generates randomized test vectors.\n\n"
            "Features:\n"
            "- SV to PyVSC translation\n"
            "- PyVSC randomization testing\n"
            "- Bulk test vector generation\n\n"
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
