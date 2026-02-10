#!/usr/bin/env python3
"""
SV / XML to PyVSC Translation Pipeline  (Console Runner)

A rich console-based tool that executes the same pipeline as the GUI
(sv_to_pyvsc_gui.py) with colored output, per-step timing, and session
persistence — no external dependencies beyond the Python stdlib.

Pipeline steps:
  0  XML -> SV conversion        (local, only for .xml input)
  1  SV  -> PyVSC translation    (local)
  2  PyVSC randomization test    (WSL on Windows, direct on Linux)
  3  Test-vector generation      (WSL on Windows, direct on Linux)

Supports both Windows (via WSL) and native Linux execution.
On Linux, PyVSC is expected to be installed system-wide (no venv).

Usage examples:
    python3 sv_to_pyvsc_console.py example_sv_classes.sv
    python3 sv_to_pyvsc_console.py isp_yuv2rgb.sv --hw-field hw_field.txt --num-vectors 10
    python3 sv_to_pyvsc_console.py --step 1 2
    python3 sv_to_pyvsc_console.py example_sv_classes.sv -v --step all
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION = "1.2.0"

# Use python3 on Linux, python on Windows
_PYTHON = "python3" if sys.platform != "win32" else "python"

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_FILE = os.path.join(_SCRIPT_DIR, "console_config.json")
_DEFAULT_OUTPUT_SUBDIR = "Output"

STEP_NAMES: Dict[int, str] = {
    0: "XML -> SV Conversion",
    1: "SV -> PyVSC Translation",
    2: "PyVSC Randomization Test",
    3: "Test Vector Generation",
}


# ---------------------------------------------------------------------------
# ANSI Color Support
# ---------------------------------------------------------------------------

class Color:
    """ANSI escape-code helper with automatic Windows / non-TTY fallback."""

    RESET = "\033[0m"
    BOLD  = "\033[1m"
    DIM   = "\033[2m"

    # Semantic colors (matching sv_to_pyvsc_gui.py tag scheme)
    RED    = "\033[91m"           # error    (#f14c4c)
    GREEN  = "\033[92m"           # success  (#4ec9b0)
    YELLOW = "\033[93m"           # warning  (#dcdcaa)
    BLUE   = "\033[94m"           # header   (#569cd6)
    CYAN   = "\033[96m"           # header alt
    ORANGE = "\033[38;5;208m"     # command  (#ce9178)
    GRAY   = "\033[90m"           # timestamp

    # Convenience aliases used by _log()
    INFO    = ""                  # default terminal color
    SUCCESS = GREEN
    WARNING = YELLOW
    ERROR   = RED
    HEADER  = CYAN
    COMMAND = ORANGE

    _enabled: bool = True

    @classmethod
    def init(cls, force_no_color: bool = False) -> None:
        """Call once at startup to configure colour support."""
        if force_no_color or os.environ.get("NO_COLOR"):
            cls._disable_all()
            return

        # Auto-disable if stdout is not a terminal (e.g. piped to file)
        if not sys.stdout.isatty():
            cls._disable_all()
            return

        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32                     # type: ignore[attr-defined]
                handle = kernel32.GetStdHandle(-11)                   # STD_OUTPUT_HANDLE
                mode = ctypes.c_ulong()
                kernel32.GetConsoleMode(handle, ctypes.byref(mode))
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            except Exception:
                cls._disable_all()

    @classmethod
    def _disable_all(cls) -> None:
        cls._enabled = False
        for attr in list(vars(cls)):
            if attr.isupper() and isinstance(getattr(cls, attr), str) and attr != "_enabled":
                setattr(cls, attr, "")

    @classmethod
    def wrap(cls, text: str, color: str) -> str:
        if not cls._enabled or not color:
            return text
        return f"{color}{text}{cls.RESET}"


# ---------------------------------------------------------------------------
# Step Result
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    step_num: int
    name: str
    success: bool = False
    elapsed_secs: float = 0.0
    skipped: bool = False
    error_msg: str = ""


# ---------------------------------------------------------------------------
# Console Runner
# ---------------------------------------------------------------------------

class ConsoleRunner:
    """Orchestrates the full SV/XML -> PyVSC pipeline from the console."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.project_root: str = _SCRIPT_DIR
        self.verbose: bool = args.verbose
        self.quiet: bool = args.quiet
        self.no_save: bool = args.no_save

        # Output directory for all generated files
        self.output_base_dir: str = os.path.join(self.project_root, _DEFAULT_OUTPUT_SUBDIR)
        os.makedirs(self.output_base_dir, exist_ok=True)

        # Load WSL environment from Env.csh
        self.env_config: Dict[str, str] = self._load_env_config()

        # Merge CLI args with saved config
        self._merge_args_with_config(args)

        # Resolve input file and derived paths
        if self.input_file_path:
            self._resolve_input_file(self.input_file_path)
        else:
            self.input_type = "N/A"
            self.sv_file_path = ""
            self.output_py_path = ""

        # Auto-detect class name if not provided
        if not self.class_name:
            detected = self._detect_class_name()
            if detected:
                self.class_name = detected

        # Determine which steps to run
        if "all" in args.step:
            self.steps: List[int] = [0, 1, 2, 3]
        else:
            self.steps = sorted(set(int(s) for s in args.step))

    # -----------------------------------------------------------------
    # Env.csh / Config
    # -----------------------------------------------------------------

    def _load_env_config(self) -> Dict[str, str]:
        """Parse Env.csh for WSL configuration (same logic as GUI)."""
        env_file = os.path.join(self.project_root, "Env.csh")
        config: Dict[str, str] = {}

        if os.path.exists(env_file):
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            key, _, value = line.partition("=")
                            key, value = key.strip(), value.strip()
                            if key and value:
                                config[key] = value
            except Exception as exc:
                self._log(f"Warning: Error reading Env.csh: {exc}", "warning")
        else:
            self._log(f"Warning: Env.csh not found at {env_file}", "warning")

        # Fill defaults for anything missing
        defaults = {
            "WIN_PROJECT_PATH": self.project_root,
            "WSL_PROJECT_PATH": self._to_wsl_path(self.project_root),
            "WSL_VENV_PATH": ".wsl_venv",
            "WSL_DISTRO": "Ubuntu",
            "WSL_PYTHON_VERSION": "3.10",
        }
        for key, default_val in defaults.items():
            if key not in config:
                config[key] = default_val
        return config

    def _load_console_config(self) -> Dict:
        """Load saved settings from console_config.json."""
        if not os.path.exists(_CONFIG_FILE):
            return {}
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_console_config(self) -> None:
        """Persist current settings to console_config.json."""
        config = {
            "input_file_path": self.input_file_path,
            "hw_field_path": self.hw_field_path,
            "class_name": self.class_name,
            "num_vectors": self.num_vectors,
            "random_seed": self.random_seed,
            "output_dir": self.output_dir,
            "use_wsl": self.use_wsl,
            "top_params_csv": self.top_params_csv,
        }
        try:
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception as exc:
            self._log(f"Warning: Could not save config: {exc}", "warning")

    def _merge_args_with_config(self, args: argparse.Namespace) -> None:
        """Merge CLI arguments with saved config.  CLI always wins."""
        saved = self._load_console_config() if not args.reset_config else {}

        default_hw = os.path.join(self.project_root, "hw_field.txt")

        self.input_file_path: str = (
            args.input
            or saved.get("input_file_path", "")
        )
        self.hw_field_path: str = (
            args.hw_field
            or saved.get("hw_field_path", "")
            or (default_hw if os.path.exists(default_hw) else "")
        )
        self.class_name: str = args.class_name or saved.get("class_name", "")
        self.num_vectors: int = (
            args.num_vectors
            if args.num_vectors is not None
            else saved.get("num_vectors", 10)
        )
        self.random_seed: int = (
            args.seed if args.seed is not None else saved.get("random_seed", 12345)
        )
        self.output_dir: str = (
            args.output_dir or saved.get("output_dir", "./test_vectors")
        )
        # Default: WSL on Windows, direct execution on Linux
        default_wsl = sys.platform == "win32"
        self.use_wsl: bool = (
            args.use_wsl if args.use_wsl is not None else saved.get("use_wsl", default_wsl)
        )

        # TopParameter CSV path
        self.top_params_csv: str = (
            args.top_params
            or saved.get("top_params_csv", "")
        )

        # Resolve relative paths to absolute (critical for WSL commands
        # that cd into Output/ — relative paths would break).
        if self.input_file_path and not os.path.isabs(self.input_file_path):
            self.input_file_path = os.path.abspath(self.input_file_path)
        if self.hw_field_path and not os.path.isabs(self.hw_field_path):
            self.hw_field_path = os.path.abspath(self.hw_field_path)
        if self.top_params_csv and not os.path.isabs(self.top_params_csv):
            self.top_params_csv = os.path.abspath(self.top_params_csv)

    # -----------------------------------------------------------------
    # Path Utilities
    # -----------------------------------------------------------------

    @staticmethod
    def _to_wsl_path(win_path: str) -> str:
        """Convert a Windows path to a WSL path.
        e.g.  C:\\Users\\foo\\bar  ->  /mnt/c/Users/foo/bar
        """
        path = win_path.replace("\\", "/")
        if len(path) >= 2 and path[1] == ":":
            drive = path[0].lower()
            path = f"/mnt/{drive}{path[2:]}"
        return path

    def _resolve_input_file(self, filepath: str) -> None:
        """Determine input type and set derived paths."""
        ext = os.path.splitext(filepath)[1].lower()
        base_name = os.path.splitext(os.path.basename(filepath))[0]

        if ext == ".xml":
            self.input_type = "XML"
            self.sv_file_path = os.path.join(self.output_base_dir, base_name + ".sv")
            self.output_py_path = os.path.join(self.output_base_dir, base_name + ".py")
        elif ext == ".sv":
            self.input_type = "SV"
            self.sv_file_path = filepath
            self.output_py_path = os.path.join(self.output_base_dir, base_name + ".py")
        else:
            self.input_type = "SV"
            self.sv_file_path = filepath
            self.output_py_path = os.path.join(self.output_base_dir, base_name + ".py")
            self._log(f"Warning: Unknown extension '{ext}', treating as SV.", "warning")

    def _detect_class_name(self) -> str:
        """Detect PyVSC class name from SV source (regex + PascalCase)."""
        sv_path = getattr(self, "sv_file_path", "")
        if not sv_path or not os.path.exists(sv_path):
            return ""
        try:
            with open(sv_path, "r", encoding="utf-8") as f:
                content = f.read()
            matches = re.findall(r"class\s+(\w+)", content)
            if matches:
                pascal = "".join(w.capitalize() for w in matches[0].split("_"))
                return pascal
        except Exception:
            pass
        return ""

    def _validate_hw_fields(self) -> None:
        """Cross-reference hw_field.txt entries against SV field declarations."""
        sv_path = getattr(self, "sv_file_path", "")
        if not sv_path or not os.path.exists(sv_path):
            return
        if not self.hw_field_path or not os.path.exists(self.hw_field_path):
            return

        # Parse hw_field.txt
        hw_fields: set = set()
        try:
            with open(self.hw_field_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    token = line.split("#")[0].split()[0]
                    hw_fields.add(token)
        except Exception as exc:
            self._log(f"Could not read HW field file: {exc}", "error")
            return

        if not hw_fields:
            self._log("Warning: HW field file is empty.", "warning")
            return

        # Parse SV field names
        sv_fields: set = set()
        try:
            with open(sv_path, "r", encoding="utf-8") as f:
                content = f.read()
            for m in re.finditer(
                r"\b(?:rand|randc)\s+(?:bit|logic|int|byte|shortint|longint|integer)\b"
                r"[^;]*?(\w+)\s*;",
                content,
            ):
                sv_fields.add(m.group(1))
            for m in re.finditer(r"\brand\s+\w+\s+(\w+)\s*;", content):
                sv_fields.add(m.group(1))
        except Exception as exc:
            self._log(f"Could not parse SV file: {exc}", "error")
            return

        missing = hw_fields - sv_fields
        if missing:
            self._log(
                f"HW field validation: {len(missing)} field(s) NOT in SV: "
                f"{', '.join(sorted(missing))}",
                "warning",
            )
        else:
            self._log(
                f"HW field validation: all {len(hw_fields)} field(s) found in SV.",
                "success",
            )

    # -----------------------------------------------------------------
    # Logging / Printing
    # -----------------------------------------------------------------

    @staticmethod
    def _log(message: str, level: str = "info") -> None:
        """Print a timestamped, colour-coded line."""
        if not message:
            print()
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        color_map = {
            "info":    Color.INFO,
            "success": Color.SUCCESS,
            "warning": Color.WARNING,
            "error":   Color.ERROR,
            "header":  Color.HEADER,
            "command": Color.COMMAND,
        }
        color = color_map.get(level, Color.INFO)
        ts = Color.wrap(f"[{timestamp}]", Color.GRAY)
        msg = Color.wrap(message, color) if color else message
        print(f"{ts} {msg}")

    def _print_banner(self) -> None:
        bar = Color.wrap("=" * 80, Color.CYAN)
        title = Color.wrap(
            "  SV / XML  to  PyVSC  Translation Pipeline  (Console)", Color.CYAN + Color.BOLD
        )
        ver = Color.wrap(f"  Version {VERSION}", Color.GRAY)
        print()
        print(bar)
        print(title)
        print(ver)
        print(bar)
        print()

    def _print_config_summary(self) -> None:
        """Show resolved configuration before pipeline execution."""
        self._log("Configuration:", "header")
        self._log(f"  Input file   : {self.input_file_path or '(none)'}")
        self._log(f"  Input type   : {self.input_type}")
        self._log(f"  SV file      : {self.sv_file_path}")
        self._log(f"  PyVSC output : {self.output_py_path}")
        self._log(f"  HW field     : {self.hw_field_path or '(none)'}")
        self._log(f"  Class name   : {self.class_name or '(auto-detect)'}")
        self._log(f"  Num vectors  : {self.num_vectors}")
        self._log(f"  Random seed  : {self.random_seed}")
        self._log(f"  Output dir   : {self.output_dir}")
        self._log(f"  Top params   : {self.top_params_csv or '(none)'}")
        self._log(f"  Platform     : {sys.platform}")
        self._log(f"  Use WSL      : {self.use_wsl}")
        if self.use_wsl:
            self._log(f"  WSL distro   : {self.env_config.get('WSL_DISTRO', 'N/A')}")
            self._log(f"  WSL project  : {self.env_config.get('WSL_PROJECT_PATH', 'N/A')}")
            self._log(f"  WSL venv     : {self.env_config.get('WSL_VENV_PATH', 'N/A')}")
        else:
            self._log(f"  Python       : {_PYTHON} (native, no venv)")
        self._log(f"  Steps        : {self.steps}")
        self._log("")

    def _print_step_header(self, step_num: int, description: str) -> None:
        inner = f" Step {step_num}: {description} "
        width = max(len(inner) + 2, 62)
        top = "+" + "=" * (width - 2) + "+"
        mid = "|" + inner.ljust(width - 2) + "|"
        bot = "+" + "=" * (width - 2) + "+"
        self._log("")
        self._log(top, "header")
        self._log(mid, "header")
        self._log(bot, "header")

    @staticmethod
    def _print_step_footer(step_num: int, success: bool, elapsed: float) -> None:
        status = "PASSED" if success else "FAILED"
        level = "success" if success else "error"
        ConsoleRunner._log(f"  Step {step_num} {status}  [{elapsed:.2f}s]", level)
        ConsoleRunner._log("")

    def _print_summary_table(self, results: List[StepResult], total_elapsed: float) -> None:
        """Print a coloured summary table."""
        bar = "=" * 80
        self._log("")
        self._log(bar, "header")
        self._log("PIPELINE SUMMARY".center(80), "header")
        self._log(bar, "header")

        hdr = f" {'Step':^5} | {'Name':<28} | {'Status':<8} | {'Time':>8}"
        sep = f" {'-'*5}-+-{'-'*28}-+-{'-'*8}-+-{'-'*8}"
        self._log(hdr, "header")
        self._log(sep, "header")

        for r in results:
            if r.skipped:
                status, color, time_str = "SKIP", "warning", "     --"
            elif r.success:
                status, color, time_str = "PASS", "success", f"{r.elapsed_secs:6.2f}s"
            else:
                status, color, time_str = "FAIL", "error", f"{r.elapsed_secs:6.2f}s"
            self._log(
                f"   {r.step_num}   | {r.name:<28} | {status:<8} | {time_str:>8}",
                color,
            )

        self._log(sep, "header")
        self._log(f" {'':>37} Total: {total_elapsed:7.2f}s", "header")
        self._log("")
        self._log(f" Output directory : {self.output_base_dir}")
        if any(r.step_num == 3 and not r.skipped for r in results):
            self._log(f" Test vectors     : {self.output_dir}")
        self._log(bar, "header")
        self._log("")

    # -----------------------------------------------------------------
    # Subprocess Execution
    # -----------------------------------------------------------------

    def _run_command(
        self,
        cmd: str,
        description: str,
        use_wsl: bool = False,
        cwd: Optional[str] = None,
    ) -> Tuple[bool, float]:
        """Execute *cmd* with real-time streaming output.

        Returns ``(success, elapsed_seconds)``.
        """
        start = time.time()

        if use_wsl:
            wsl_project = self.env_config["WSL_PROJECT_PATH"]
            wsl_venv = self.env_config["WSL_VENV_PATH"]
            wsl_distro = self.env_config["WSL_DISTRO"]
            full_cmd = (
                f'wsl -d {wsl_distro} -- bash -lc '
                f'"cd {wsl_project} '
                f'&& source {wsl_venv}/bin/activate && {cmd}"'
            )
            if self.verbose:
                self._log(f"WSL> {cmd}", "command")
        else:
            full_cmd = cmd
            if self.verbose:
                self._log(f"CMD> {cmd}", "command")

        if cwd is None:
            cwd = self.project_root

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        try:
            process = subprocess.Popen(
                full_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=cwd,
                env=env,
                bufsize=1,
            )

            if not self.quiet:
                for line in process.stdout:                  # type: ignore[union-attr]
                    line = line.rstrip()
                    lower = line.lower()
                    if "error" in lower or "exception" in lower:
                        self._log(f"  {line}", "error")
                    elif "warning" in lower:
                        self._log(f"  {line}", "warning")
                    elif "success" in lower or "complete" in lower:
                        self._log(f"  {line}", "success")
                    else:
                        self._log(f"  {line}")
            else:
                process.stdout.read()                        # type: ignore[union-attr]

            process.wait()
            elapsed = time.time() - start
            return (process.returncode == 0, elapsed)

        except Exception as exc:
            elapsed = time.time() - start
            self._log(f"Error running command: {exc}", "error")
            return (False, elapsed)

    # -----------------------------------------------------------------
    # Pipeline Steps
    # -----------------------------------------------------------------

    def _run_step_0_xml_to_sv(self) -> StepResult:
        result = StepResult(step_num=0, name=STEP_NAMES[0])

        if self.input_type != "XML":
            self._log("Input is SV file. Skipping XML->SV conversion.", "info")
            result.skipped = True
            result.success = True
            return result

        if not os.path.exists(self.input_file_path):
            self._log(f"Error: XML file not found: {self.input_file_path}", "error")
            result.error_msg = "XML file not found"
            return result

        converter = os.path.join(self.project_root, "XML_to_sv_Converter.py")
        if not os.path.exists(converter):
            self._log("Error: XML_to_sv_Converter.py not found!", "error")
            result.error_msg = "Converter script missing"
            return result

        # Auto-derive TopParameter CSV path alongside the SV output
        auto_csv = os.path.join(
            os.path.dirname(self.sv_file_path),
            os.path.splitext(os.path.basename(self.sv_file_path))[0] + "_top_params.csv",
        )
        cmd = f'{_PYTHON} "{converter}" "{self.input_file_path}" "{self.sv_file_path}" "{auto_csv}"'

        self._print_step_header(0, STEP_NAMES[0])
        success, elapsed = self._run_command(cmd, STEP_NAMES[0], use_wsl=False)
        result.success = success
        result.elapsed_secs = elapsed

        if success:
            self._log(f"SV file generated: {self.sv_file_path}", "success")
            # Auto-set top_params_csv if the CSV was created
            if os.path.exists(auto_csv):
                self.top_params_csv = auto_csv
                self._log(f"TopParameter CSV: {auto_csv}", "success")
            detected = self._detect_class_name()
            if detected:
                self.class_name = detected

        self._print_step_footer(0, success, elapsed)
        return result

    def _run_step_1_translate(self) -> StepResult:
        result = StepResult(step_num=1, name=STEP_NAMES[1])

        if not os.path.exists(self.sv_file_path):
            self._log(f"Error: SV file not found: {self.sv_file_path}", "error")
            result.error_msg = "SV file not found"
            return result

        translator = os.path.join(self.project_root, "sv_to_pyvsc.py")
        cmd = f'{_PYTHON} "{translator}" "{self.sv_file_path}" -o "{self.output_py_path}"'

        self._print_step_header(1, STEP_NAMES[1])
        success, elapsed = self._run_command(cmd, STEP_NAMES[1], use_wsl=False)
        result.success = success
        result.elapsed_secs = elapsed

        if success:
            self._log(f"PyVSC output: {self.output_py_path}", "success")
            detected = self._detect_class_name()
            if detected:
                self.class_name = detected

        self._print_step_footer(1, success, elapsed)
        return result

    def _run_step_2_test(self) -> StepResult:
        result = StepResult(step_num=2, name=STEP_NAMES[2])

        if not os.path.exists(self.output_py_path):
            self._log("Error: PyVSC file not found. Run translation first.", "error")
            result.error_msg = "PyVSC file missing"
            return result

        py_filename = os.path.basename(self.output_py_path)

        if self.use_wsl:
            wsl_output_dir = self._to_wsl_path(self.output_base_dir)
            cmd = f"cd {wsl_output_dir} && python {py_filename}"
        else:
            cmd = f'{_PYTHON} "{py_filename}"'

        self._print_step_header(2, STEP_NAMES[2])
        success, elapsed = self._run_command(
            cmd, STEP_NAMES[2],
            use_wsl=self.use_wsl,
            cwd=self.output_base_dir if not self.use_wsl else None,
        )
        result.success = success
        result.elapsed_secs = elapsed
        self._print_step_footer(2, success, elapsed)
        return result

    def _run_step_3_generate(self) -> StepResult:
        result = StepResult(step_num=3, name=STEP_NAMES[3])

        if not os.path.exists(self.output_py_path):
            self._log("Error: PyVSC file not found.", "error")
            result.error_msg = "PyVSC file missing"
            return result

        if not self.hw_field_path or not os.path.exists(self.hw_field_path):
            self._log("Skipping: HW field file not specified or not found.", "warning")
            result.skipped = True
            result.success = True
            return result

        if not self.class_name:
            self._log("Skipping: Class name not specified.", "warning")
            result.skipped = True
            result.success = True
            return result

        module_name = os.path.splitext(os.path.basename(self.output_py_path))[0]
        generator = os.path.join(self.project_root, "generate_test_vectors.py")

        # Build --top-params argument if CSV is available
        top_params_arg = ""
        if self.top_params_csv and os.path.exists(self.top_params_csv):
            if self.use_wsl:
                top_params_arg = f" --top-params {self._to_wsl_path(self.top_params_csv)}"
            else:
                top_params_arg = f' --top-params "{self.top_params_csv}"'

        if self.use_wsl:
            wsl_hw_path = self._to_wsl_path(self.hw_field_path)
            wsl_output_dir = self._to_wsl_path(self.output_base_dir)
            wsl_project_root = self._to_wsl_path(self.project_root)

            wsl_output_arg = self.output_dir
            if self.output_dir and len(self.output_dir) >= 2 and self.output_dir[1] == ":":
                wsl_output_arg = self._to_wsl_path(self.output_dir)

            cmd = (
                f"cd {wsl_output_dir} && "
                f"python {wsl_project_root}/generate_test_vectors.py "
                f"{module_name} {self.class_name} {wsl_hw_path} "
                f"{self.num_vectors} {wsl_output_arg} --seed {self.random_seed}"
                f"{top_params_arg}"
            )
        else:
            # Native Linux: run directly from the Output directory
            cmd = (
                f'{_PYTHON} "{generator}" '
                f"{module_name} {self.class_name} "
                f'"{self.hw_field_path}" '
                f"{self.num_vectors} {self.output_dir} --seed {self.random_seed}"
                f"{top_params_arg}"
            )

        self._print_step_header(3, STEP_NAMES[3])
        success, elapsed = self._run_command(
            cmd, STEP_NAMES[3],
            use_wsl=self.use_wsl,
            cwd=self.output_base_dir if not self.use_wsl else None,
        )
        result.success = success
        result.elapsed_secs = elapsed
        self._print_step_footer(3, success, elapsed)
        return result

    # -----------------------------------------------------------------
    # Main Pipeline
    # -----------------------------------------------------------------

    def run(self) -> int:
        """Execute the pipeline.  Returns 0 on success, 1 on any failure."""
        pipeline_start = time.time()

        self._print_banner()
        self._print_config_summary()

        # Validate HW fields (non-blocking)
        self._validate_hw_fields()

        step_runners = {
            0: self._run_step_0_xml_to_sv,
            1: self._run_step_1_translate,
            2: self._run_step_2_test,
            3: self._run_step_3_generate,
        }

        results: List[StepResult] = []

        for step_num in self.steps:
            runner = step_runners[step_num]
            result = runner()
            results.append(result)

            # Stop on failure (unless step was skipped)
            if not result.success and not result.skipped:
                self._log(f"Step {step_num} failed. Stopping pipeline.", "error")
                for remaining in self.steps:
                    if remaining > step_num:
                        results.append(
                            StepResult(
                                step_num=remaining,
                                name=STEP_NAMES[remaining],
                                skipped=True,
                                success=True,
                            )
                        )
                break

        pipeline_elapsed = time.time() - pipeline_start
        self._print_summary_table(results, pipeline_elapsed)

        # Persist settings
        if not self.no_save:
            self._save_console_config()
            self._log(f"Settings saved to {_CONFIG_FILE}", "info")

        any_failure = any(not r.success for r in results)
        return 1 if any_failure else 0


# ---------------------------------------------------------------------------
# Argument Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sv_to_pyvsc_console",
        description="SV / XML to PyVSC Translation Pipeline (Console)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              %(prog)s example_sv_classes.sv
              %(prog)s input.xml --hw-field hw_field.txt --num-vectors 100
              %(prog)s --step 1 2
              %(prog)s example_sv_classes.sv -v --step all
        """),
    )

    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="Input file (.sv or .xml).  Uses saved config if omitted.",
    )

    # Step selection
    parser.add_argument(
        "--step",
        nargs="+",
        default=["all"],
        metavar="N",
        help="Steps to run: 0 1 2 3 or 'all' (default: all)",
    )

    # File paths
    parser.add_argument("--hw-field", default=None, help="Path to hw_field.txt")
    parser.add_argument(
        "-o", "--output-dir", default=None, help="Output directory for test vectors"
    )
    parser.add_argument(
        "--top-params", default=None, metavar="CSV",
        help="TopParameter CSV for range overrides (auto-detected from XML step)",
    )

    # Test-vector parameters
    parser.add_argument("--class-name", default=None, help="PyVSC class name (auto-detected if omitted)")
    parser.add_argument("--num-vectors", type=int, default=None, help="Number of test vectors (default: 10)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed (default: 12345)")

    # WSL control  (Python 3.9+)
    parser.add_argument(
        "--wsl",
        dest="use_wsl",
        action="store_true",
        default=None,
        help="Use WSL for PyVSC execution (default)",
    )
    parser.add_argument(
        "--no-wsl",
        dest="use_wsl",
        action="store_false",
        help="Disable WSL execution",
    )

    # Config management
    parser.add_argument("--no-save", action="store_true", help="Do not persist settings")
    parser.add_argument("--reset-config", action="store_true", help="Clear saved config and use defaults")

    # Display
    parser.add_argument("--no-color", action="store_true", help="Disable coloured output")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show full subprocess command strings")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress subprocess stdout")

    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Validate --step values
    valid_steps = {"0", "1", "2", "3", "all"}
    for s in args.step:
        if s not in valid_steps:
            parser.error(f"Invalid step '{s}'.  Choose from: 0, 1, 2, 3, all")

    Color.init(force_no_color=args.no_color)

    runner = ConsoleRunner(args)
    sys.exit(runner.run())


if __name__ == "__main__":
    main()
