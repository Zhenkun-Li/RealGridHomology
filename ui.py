import json
from pathlib import Path
import threading
import time

UI_IMPORT_ERROR = None
try:
    import tkinter as tk
    from tkinter import ttk, messagebox

    import matplotlib
    matplotlib.use('TkAgg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    try:
        from tkmacosx import Button as MacButton  # type: ignore[import-not-found]
        USE_MACOS_BUTTON = True
    except ImportError:
        USE_MACOS_BUTTON = False
except ModuleNotFoundError as exc:
    UI_IMPORT_ERROR = exc
    tk = None
    ttk = None
    messagebox = None
    Figure = None
    FigureCanvasTkAgg = None
    MacButton = None
    USE_MACOS_BUTTON = False

from real_grid_homology.io import load_json, save_json
from real_grid_homology.knot import Knot, SymmetryKind, detect_symmetry_kind
from real_grid_homology.stages.domains import DomainStage
from real_grid_homology.stages.generators import GeneratorStage
from real_grid_homology.stages.grading import GradingStage
from real_grid_homology.stages.hat_homology import HatHomologyStage
from real_grid_homology.stages.minus_homology import MinusHomologyStage
from real_grid_homology.stages.polynomial import PolynomialStage
from real_grid_homology.stages.rectangles import RectangleStage

# Grid display constants
CELL_SIZE = 40          # Pixels per cell
MIN_CELL_SIZE = 30      # Minimum cell size for larger grids
MAX_CELL_SIZE = 50      # Maximum cell size for smaller grids
GRID_PADDING = 20       # Padding around grid
GRID_LINE_COLOR = 'gray'
AXIS_COLOR = '#016646'  # Same as draw_domains.py
AXIS_WIDTH = 2

# Knot lines (for display knot feature)
KNOT_LINE_COLOR = 'red'
KNOT_LINE_WIDTH = 2
MARK_MARGIN = 0.2
CROSSING_MARGIN = 0.35

# Available sizes
SIZES = list(range(2, 18))
DEFAULT_SIZE = 5

# Size limits for computations
SIZE_LIMIT_POLYNOMIAL = 17
SIZE_LIMIT_HAT = 13
SIZE_LIMIT_MINUS = 11

# Tool modes
TOOL_NONE = None
TOOL_O = 'O'
TOOL_X = 'X'
TOOL_ERASER = 'eraser'

SETUP_STRONGLY_INVERTIBLE = SymmetryKind.STRONGLY_INVERTIBLE.value
SETUP_PERIODIC = SymmetryKind.PERIODIC.value

# Path constants
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
KNOTS_DIR = DATA_DIR / "knots"
POLYNOMIAL_PATH = DATA_DIR / "polynomial" / "polynomial.json"
HOMOLOGY_HAT_DIR = DATA_DIR / "homology" / "hat"
HOMOLOGY_MINUS_DIR = DATA_DIR / "homology" / "minus"

GENERATORS_DIR = DATA_DIR / "generators"
RECTANGLES_DIR = DATA_DIR / "rectangles"
DOMAINS_DIR = DATA_DIR / "domains"
GRADING_DIR = DATA_DIR / "grading"


def log(message: str, progress_callback=None) -> None:
    if progress_callback is not None:
        progress_callback(message)


def delete_if_exists(path: Path, progress_callback=None) -> None:
    if path.exists():
        path.unlink()
        log(f"  Deleted existing file: {path}", progress_callback)


def delete_polynomial_entry(knot_name: str, progress_callback=None) -> None:
    if not POLYNOMIAL_PATH.exists():
        return
    polynomial_results = load_json(POLYNOMIAL_PATH)
    if knot_name not in polynomial_results:
        return
    del polynomial_results[knot_name]
    save_json(POLYNOMIAL_PATH, polynomial_results)
    log(f"  Removed polynomial entry for {knot_name}", progress_callback)


def run_workflow(knot_name: str, mode: str, progress_callback=None) -> None:
    knot_path = KNOTS_DIR / f"{knot_name}.json"
    if not knot_path.exists():
        raise FileNotFoundError(f"Knot data file not found: {knot_path}")

    knot = Knot.from_path(knot_path)
    size = knot.size
    log(
        f"Loaded knot '{knot_name}' ({knot.symmetry_kind.value}) with grid size {size}",
        progress_callback,
    )

    if size > SIZE_LIMIT_POLYNOMIAL:
        log(f"Size {size} > {SIZE_LIMIT_POLYNOMIAL}: no computation performed", progress_callback)
        return

    compute_polynomial = (
        knot.symmetry_kind is SymmetryKind.STRONGLY_INVERTIBLE
        and size <= SIZE_LIMIT_POLYNOMIAL
    )
    compute_hat = size <= SIZE_LIMIT_HAT
    compute_minus = (
        knot.symmetry_kind is SymmetryKind.STRONGLY_INVERTIBLE
        and size <= SIZE_LIMIT_MINUS
    )

    generator_path = GENERATORS_DIR / f"size-{size}.jsonl"
    if generator_path.exists():
        log("Step 1: Generators exist (skipping)", progress_callback)
    else:
        log("Step 1: Generating generators...", progress_callback)
        GeneratorStage(size).compute()

    rectangle_path = RECTANGLES_DIR / f"{knot_name}.jsonl"
    if mode == "delete":
        delete_if_exists(rectangle_path, progress_callback)
    if mode == "skip" and rectangle_path.exists():
        log("Step 2: Rectangles exist (skipping)", progress_callback)
    else:
        log("Step 2: Generating rectangles...", progress_callback)
        RectangleStage(knot).compute()

    domain_path = DOMAINS_DIR / f"{knot_name}.jsonl"
    if mode == "delete":
        delete_if_exists(domain_path, progress_callback)
    if mode == "skip" and domain_path.exists():
        log("Step 3: Domains exist (skipping)", progress_callback)
    else:
        log("Step 3: Generating domains...", progress_callback)
        DomainStage(knot).compute()

    grading_path = GRADING_DIR / f"{knot_name}.jsonl"
    if mode == "delete":
        delete_if_exists(grading_path, progress_callback)
    if mode == "skip" and grading_path.exists():
        log("Step 4: Gradings exist (skipping)", progress_callback)
    else:
        log("Step 4: Computing gradings...", progress_callback)
        GradingStage(knot).compute()

    if compute_polynomial:
        polynomial_results = load_json(POLYNOMIAL_PATH) if POLYNOMIAL_PATH.exists() else {}
        if mode == "skip" and knot_name in polynomial_results:
            log("Step 5: Polynomial exists (skipping)", progress_callback)
        else:
            log("Step 5: Computing polynomial...", progress_callback)
            PolynomialStage(knot).compute()
    else:
        if mode == "delete":
            delete_polynomial_entry(knot_name, progress_callback)
        if knot.symmetry_kind is SymmetryKind.PERIODIC:
            log("Step 5: Polynomial skipped (periodic setup)", progress_callback)
        else:
            log(f"Step 5: Polynomial skipped (size {size} > {SIZE_LIMIT_POLYNOMIAL})", progress_callback)

    hat_path = HOMOLOGY_HAT_DIR / f"{knot_name}.json"
    hat_meta_path = HOMOLOGY_HAT_DIR / f"{knot_name}.meta.json"
    if compute_hat:
        if mode == "delete":
            delete_if_exists(hat_path, progress_callback)
            delete_if_exists(hat_meta_path, progress_callback)
        if mode == "skip" and hat_path.exists():
            log("Step 6: Hat homology exists (skipping)", progress_callback)
        else:
            log("Step 6: Computing hat homology...", progress_callback)
            HatHomologyStage(knot, check_diff=False).compute()
    else:
        log(f"Step 6: Hat homology skipped (size {size} > {SIZE_LIMIT_HAT})", progress_callback)

    minus_path = HOMOLOGY_MINUS_DIR / f"{knot_name}.json"
    if compute_minus:
        if mode == "delete":
            delete_if_exists(minus_path, progress_callback)
        if mode == "skip" and minus_path.exists():
            log("Step 7: Minus homology exists (skipping)", progress_callback)
        else:
            log("Step 7: Computing minus homology...", progress_callback)
            MinusHomologyStage(knot, check_diff=False).compute()
    else:
        if knot.symmetry_kind is SymmetryKind.PERIODIC:
            log("Step 7: Minus homology skipped (periodic setup)", progress_callback)
        else:
            log(f"Step 7: Minus homology skipped (size {size} > {SIZE_LIMIT_MINUS})", progress_callback)

    log(f"Workflow completed for '{knot_name}'", progress_callback)


class KnotInputApp:
    def __init__(self, root):
        if UI_IMPORT_ERROR is not None:
            raise RuntimeError(
                "Tk UI dependencies are unavailable in this Python environment. "
                f"Original error: {UI_IMPORT_ERROR}"
            )
        self.root = root
        self.root.title("Real invariants of knots")

        # State variables
        self.size = DEFAULT_SIZE
        self.O_marks = {}  # {col: row}
        self.X_marks = {}  # {col: row}
        self.current_tool = TOOL_NONE
        self.knot_displayed = False
        self.current_knot_name = None  # Track loaded knot name
        self.setup_var = None
        self.setup_hint_label = None

        # Computation state
        self.computing = False
        self.timer_running = False
        self.timer_start = None
        self.current_progress_message = ""

        # UI components
        self.canvas = None
        self.size_var = None
        self.name_entry = None
        self.btn_O = None
        self.btn_X = None
        self.btn_eraser = None
        self.btn_display = None

        # Layout frames
        self.floor2_frame = None  # Top floor: options, grid, computation
        self.floor1_frame = None  # Bottom floor: results display
        self.left_panel = None    # Options panel (Floor 2 left)
        self.middle_panel = None  # Grid panel (Floor 2 middle)
        self.right_panel = None   # Computation panel (Floor 2 right)

        # Dynamic cell size based on grid size
        self.current_cell_size = CELL_SIZE

        # Load knot dropdown
        self.load_knot_var = None
        self.load_knot_dropdown = None

        # Computation controls
        self.mode_var = None
        self.mode_explanation_label = None
        self.btn_compute = None
        self.progress_label = None

        # Results display - separate figures for polynomial, hat homology, and minus homology
        self.poly_figure = None
        self.poly_canvas = None
        self.poly_frame = None
        self.homology_figure = None
        self.homology_canvas = None
        self.homology_frame = None
        self.minus_figure = None
        self.minus_canvas = None
        self.minus_frame = None

        self._create_ui()

    def _create_ui(self):
        """Create the main UI layout with 2 floors.

        Floor 2 (top): Left options panel | Middle grid | Right computation panel
        Floor 1 (bottom): Polynomial and Homology results display
        """
        # Floor 2: Top section with options, grid, and computation
        self.floor2_frame = tk.Frame(self.root)
        self.floor2_frame.pack(side=tk.TOP, fill=tk.BOTH)

        # Floor 2 - Left panel: Options/controls
        self.left_panel = tk.Frame(self.floor2_frame, padx=10, pady=10)
        self.left_panel.pack(side=tk.LEFT, fill=tk.Y)

        # Floor 2 - Middle panel: Grid canvas
        self.middle_panel = tk.Frame(self.floor2_frame, padx=10, pady=10)
        self.middle_panel.pack(side=tk.LEFT, fill=tk.BOTH)

        # Floor 2 - Right panel: Computation controls
        self.right_panel = tk.Frame(self.floor2_frame, padx=10, pady=10)
        self.right_panel.pack(side=tk.LEFT, fill=tk.Y)

        # Floor 1: Bottom section for results display
        self.floor1_frame = tk.Frame(self.root, padx=10, pady=5)
        self.floor1_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # Create all UI components
        self._create_left_panel()
        self._create_canvas()
        self._create_computation_panel()
        self._create_results_panel()
        self._update_setup_controls()

    def _create_left_panel(self):
        """Create the left options panel (Floor 2 left)."""
        self._create_load_knot_dropdown()
        self._create_setup_selector()
        self._create_size_dropdown()
        self._create_tool_buttons()
        self._create_name_input()
        self._create_action_buttons()

    def _create_setup_selector(self):
        """Create the symmetry/setup selector."""
        tk.Label(self.left_panel, text="Setup:").pack(anchor='w')
        self.setup_var = tk.StringVar(value=SETUP_STRONGLY_INVERTIBLE)

        setup_frame = tk.Frame(self.left_panel)
        setup_frame.pack(anchor='w')

        tk.Radiobutton(
            setup_frame,
            text="Strong",
            variable=self.setup_var,
            value=SETUP_STRONGLY_INVERTIBLE,
            command=self._on_setup_change,
        ).pack(side=tk.LEFT)
        tk.Radiobutton(
            setup_frame,
            text="Periodic",
            variable=self.setup_var,
            value=SETUP_PERIODIC,
            command=self._on_setup_change,
        ).pack(side=tk.LEFT)

        self.setup_hint_label = tk.Label(
            self.left_panel,
            text="O and X are mirrored separately",
            font=('Arial', 9),
            fg='gray',
        )
        self.setup_hint_label.pack(anchor='w', pady=(0, 10))

    def _create_load_knot_dropdown(self):
        """Create the load knot dropdown."""
        tk.Label(self.left_panel, text="Load Knot:").pack(anchor='w')
        self.load_knot_var = tk.StringVar(value="")
        self.load_knot_dropdown = ttk.Combobox(
            self.left_panel,
            textvariable=self.load_knot_var,
            values=self._get_available_knots(),
            state='readonly',
            width=15
        )
        self.load_knot_dropdown.pack(anchor='w', pady=(0, 10))
        self.load_knot_dropdown.bind('<<ComboboxSelected>>', self._on_load_knot)

        # Refresh button to update knot list
        tk.Button(self.left_panel, text="Refresh List", width=15,
                  command=self._refresh_knot_list).pack(anchor='w', pady=(0, 10))

    def _get_available_knots(self):
        """Get list of available knot names from data/knots directory."""
        if not KNOTS_DIR.exists():
            return []
        knots = [f.stem for f in KNOTS_DIR.glob("*.json")]
        return sorted(knots)

    def _refresh_knot_list(self):
        """Refresh the knot dropdown list."""
        knots = self._get_available_knots()
        self.load_knot_dropdown['values'] = knots

    def _on_load_knot(self, event=None):
        """Handle loading a knot from the dropdown."""
        knot_name = self.load_knot_var.get()
        if not knot_name:
            return

        knot_path = KNOTS_DIR / f"{knot_name}.json"
        if not knot_path.exists():
            messagebox.showerror("Error", f"Knot file not found: {knot_path}")
            return

        try:
            data = load_json(knot_path)

            # Validate data
            if not self._validate_knot_data(data):
                messagebox.showerror("Error", "Invalid knot data format")
                return

            symmetry_kind = detect_symmetry_kind(
                size=int(data["size"]),
                o_marks=tuple(int(value) for value in data["O"]),
                x_marks=tuple(int(value) for value in data["X"]),
            )

            # Update state
            self.size = data["size"]
            self.size_var.set(str(self.size))
            self.setup_var.set(symmetry_kind.value)

            # Convert list format to dict format
            O_list = data["O"]
            X_list = data["X"]
            self.O_marks = {i: row for i, row in enumerate(O_list) if row is not None}
            self.X_marks = {i: row for i, row in enumerate(X_list) if row is not None}
            if self._is_periodic_setup():
                self._sync_periodic_x_from_o()

            # Update name entry
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, knot_name)
            self.current_knot_name = knot_name

            # Auto display knot
            self.knot_displayed = True
            self.btn_display.config(text="Hide Knot")

            # Update canvas and redraw
            self._update_canvas_size()
            self._update_setup_controls()
            self._redraw()

            # Auto-load and display results if they exist
            self._load_and_display_results(knot_name)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to load knot: {e}")

    def _validate_knot_data(self, data):
        """Validate knot data structure."""
        required_keys = ["size", "O", "X"]
        if not all(key in data for key in required_keys):
            return False

        size = data["size"]
        if not isinstance(size, int) or size < 1:
            return False

        O = data["O"]
        X = data["X"]
        if not isinstance(O, list) or not isinstance(X, list):
            return False

        if len(O) != size or len(X) != size:
            return False

        return True

    def _create_size_dropdown(self):
        """Create the grid size dropdown."""
        tk.Label(self.left_panel, text="Grid Size:").pack(anchor='w')
        self.size_var = tk.StringVar(value=str(DEFAULT_SIZE))
        dropdown = ttk.Combobox(
            self.left_panel,
            textvariable=self.size_var,
            values=[str(s) for s in SIZES],
            state='readonly',
            width=10
        )
        dropdown.pack(anchor='w', pady=(0, 10))
        dropdown.bind('<<ComboboxSelected>>', self._on_size_change)

    def _create_tool_buttons(self):
        """Create O, X, and Eraser tool buttons with visual active state."""
        tk.Label(self.left_panel, text="Tools:").pack(anchor='w', pady=(10, 5))

        btn_frame = tk.Frame(self.left_panel)
        btn_frame.pack(anchor='w')

        # Button colors
        self.inactive_bg = '#E0E0E0'  # Light gray for inactive
        self.active_bg = '#90CAF9'    # Light blue for active

        if USE_MACOS_BUTTON:
            # Use tkmacosx Button for proper background color support on macOS
            self.btn_O = MacButton(btn_frame, text="O", width=50, bg=self.inactive_bg,
                                   command=lambda: self._toggle_tool(TOOL_O))
            self.btn_O.pack(side=tk.LEFT, padx=2)

            self.btn_X = MacButton(btn_frame, text="X", width=50, bg=self.inactive_bg,
                                   command=lambda: self._toggle_tool(TOOL_X))
            self.btn_X.pack(side=tk.LEFT, padx=2)

            self.btn_eraser = MacButton(btn_frame, text="Eraser", width=70, bg=self.inactive_bg,
                                        command=lambda: self._toggle_tool(TOOL_ERASER))
            self.btn_eraser.pack(side=tk.LEFT, padx=2)
        else:
            # Fallback to standard tk.Button for other platforms
            self.btn_O = tk.Button(btn_frame, text="O", width=5, bg=self.inactive_bg,
                                   command=lambda: self._toggle_tool(TOOL_O))
            self.btn_O.pack(side=tk.LEFT, padx=2)

            self.btn_X = tk.Button(btn_frame, text="X", width=5, bg=self.inactive_bg,
                                   command=lambda: self._toggle_tool(TOOL_X))
            self.btn_X.pack(side=tk.LEFT, padx=2)

            self.btn_eraser = tk.Button(btn_frame, text="Eraser", width=7, bg=self.inactive_bg,
                                        command=lambda: self._toggle_tool(TOOL_ERASER))
            self.btn_eraser.pack(side=tk.LEFT, padx=2)

    def _is_periodic_setup(self):
        return self.setup_var is not None and self.setup_var.get() == SETUP_PERIODIC

    def _sync_periodic_x_from_o(self):
        if not self._is_periodic_setup():
            return
        self.X_marks = {
            self.size - 1 - row: self.size - 1 - col
            for col, row in self.O_marks.items()
        }

    def _update_setup_controls(self):
        if self.setup_hint_label is not None:
            if self._is_periodic_setup():
                self.setup_hint_label.config(text="Periodic: odd size only; no axis marks")
            else:
                if self.size % 2 == 0:
                    self.setup_hint_label.config(text="Strong even: even O on axis, no X on axis")
                else:
                    self.setup_hint_label.config(text="Strong odd: one O and one X on axis")

        if self._is_periodic_setup() and self.current_tool == TOOL_X:
            self.current_tool = TOOL_NONE

        x_state = 'disabled' if self._is_periodic_setup() else 'normal'
        if self.btn_X is not None:
            self.btn_X.config(state=x_state)

        self._update_tool_buttons()

    def _on_setup_change(self):
        if self.O_marks or self.X_marks:
            if not messagebox.askyesno(
                "Change Setup",
                "Changing setup will clear the current diagram. Continue?",
            ):
                other = SETUP_PERIODIC if self._is_periodic_setup() else SETUP_STRONGLY_INVERTIBLE
                self.setup_var.set(other)
                return
            self.O_marks = {}
            self.X_marks = {}
            self.knot_displayed = False
            self.btn_display.config(text="Display Knot")

        self._update_setup_controls()
        self._redraw()

    def _create_name_input(self):
        """Create the knot name input field."""
        tk.Label(self.left_panel, text="Knot Name:").pack(anchor='w', pady=(20, 5))
        self.name_entry = tk.Entry(self.left_panel, width=15)
        self.name_entry.pack(anchor='w')

    def _create_action_buttons(self):
        """Create Clear, Display, and Save buttons."""
        # Clear button
        tk.Button(self.left_panel, text="Clear All", width=15,
                  command=self._on_clear).pack(anchor='w', pady=(20, 5))

        # Display knot button
        self.btn_display = tk.Button(self.left_panel, text="Display Knot", width=15,
                                     command=self._on_toggle_display)
        self.btn_display.pack(anchor='w', pady=5)

        # Save button
        tk.Button(self.left_panel, text="Save Diagram", width=15,
                  command=self._on_save).pack(anchor='w', pady=5)

    def _create_computation_panel(self):
        """Create the computation panel (Floor 2 right)."""
        # Title
        tk.Label(self.right_panel, text="Computation",
                 font=('Arial', 11, 'bold')).pack(anchor='w', pady=(0, 10))

        # Mode selector
        tk.Label(self.right_panel, text="Mode:").pack(anchor='w')

        self.mode_var = tk.StringVar(value="skip")

        mode_frame = tk.Frame(self.right_panel)
        mode_frame.pack(anchor='w')

        tk.Radiobutton(mode_frame, text="Skip", variable=self.mode_var,
                       value="skip", command=self._on_mode_change).pack(side=tk.LEFT)
        tk.Radiobutton(mode_frame, text="Delete", variable=self.mode_var,
                       value="delete", command=self._on_mode_change).pack(side=tk.LEFT)

        # Mode explanation
        self.mode_explanation_label = tk.Label(
            self.right_panel,
            text="Skip existing steps",
            font=('Arial', 9),
            fg='gray'
        )
        self.mode_explanation_label.pack(anchor='w', pady=(0, 10))

        # Compute button
        self.btn_compute = tk.Button(
            self.right_panel,
            text="Compute",
            width=12,
            command=self._on_compute
        )
        self.btn_compute.pack(anchor='w', pady=5)

        # Progress label
        self.progress_label = tk.Label(
            self.right_panel,
            text="Ready",
            font=('Arial', 10),
            anchor='w',
            width=20
        )
        self.progress_label.pack(anchor='w', pady=(10, 0))

        # Size limits section
        tk.Label(self.right_panel, text="Size Limits:",
                 font=('Arial', 10, 'bold')).pack(anchor='w', pady=(15, 5))

        limits_frame = tk.Frame(self.right_panel)
        limits_frame.pack(anchor='w')

        tk.Label(limits_frame, text=f"• Polynomial: ≤{SIZE_LIMIT_POLYNOMIAL}",
                 font=('Arial', 9), fg='gray').pack(anchor='w')
        tk.Label(limits_frame, text=f"• Homology-hat: ≤{SIZE_LIMIT_HAT}",
                 font=('Arial', 9), fg='gray').pack(anchor='w')
        tk.Label(limits_frame, text=f"• Homology-minus: strong only, ≤{SIZE_LIMIT_MINUS}",
                 font=('Arial', 9), fg='gray').pack(anchor='w')

    def _on_mode_change(self):
        """Update mode explanation when mode changes."""
        mode = self.mode_var.get()
        if mode == "skip":
            self.mode_explanation_label.config(text="Skip existing steps")
        else:
            self.mode_explanation_label.config(text="Re-compute all (overwrite)")

    def _calculate_cell_size(self):
        """Calculate cell size based on grid size to fit within target height.

        Target: grid should fit within left panel height (roughly 350-400 pixels).
        Smaller grids get larger cells, larger grids get smaller cells.
        """
        # Target canvas size (aligned with left panel height)
        TARGET_CANVAS_SIZE = 350

        # Calculate cell size to fit grid within target
        available_space = TARGET_CANVAS_SIZE - 2 * GRID_PADDING
        calculated_cell = available_space // self.size

        # Clamp to min/max bounds
        cell_size = max(MIN_CELL_SIZE, min(MAX_CELL_SIZE, calculated_cell))
        return cell_size

    def _create_canvas(self):
        """Create the grid canvas with dynamic sizing."""
        self.current_cell_size = self._calculate_cell_size()
        canvas_size = self.size * self.current_cell_size + 2 * GRID_PADDING
        self.canvas = tk.Canvas(
            self.middle_panel,
            width=canvas_size,
            height=canvas_size,
            bg='white'
        )
        self.canvas.pack()
        self.canvas.bind('<Button-1>', self._on_canvas_click)
        self._redraw()

    def _create_results_panel(self):
        """Create the results display panel in Floor 1 (bottom)."""
        # Height for matplotlib canvas (1.5-2x regular line height, ~30-40 pixels)
        RESULT_HEIGHT = 35
        LABEL_WIDTH = 14  # Width for labels to align all rows

        # Polynomial section - horizontal layout: label + canvas
        poly_row = tk.Frame(self.floor1_frame)
        poly_row.pack(fill=tk.X, pady=2)

        tk.Label(poly_row, text="Polynomial:",
                 font=('Arial', 10, 'bold'), width=LABEL_WIDTH, anchor='w').pack(side=tk.LEFT)

        # Frame for polynomial canvas with fixed height
        self.poly_frame = tk.Frame(poly_row, bg='white', height=RESULT_HEIGHT)
        self.poly_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.poly_frame.pack_propagate(False)  # Keep fixed height

        # Create polynomial figure
        self.poly_figure = Figure(figsize=(6, 0.4), dpi=100)
        self.poly_figure.patch.set_facecolor('white')
        self.poly_figure.subplots_adjust(left=0.02, right=0.98, top=0.85, bottom=0.15)

        # Create polynomial canvas
        self.poly_canvas = FigureCanvasTkAgg(self.poly_figure, master=self.poly_frame)
        self.poly_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Homology-hat section - horizontal layout: label + canvas
        homology_row = tk.Frame(self.floor1_frame)
        homology_row.pack(fill=tk.X, pady=2)

        tk.Label(homology_row, text="Homology-hat:",
                 font=('Arial', 10, 'bold'), width=LABEL_WIDTH, anchor='w').pack(side=tk.LEFT)

        # Frame for homology canvas with fixed height
        self.homology_frame = tk.Frame(homology_row, bg='white', height=RESULT_HEIGHT)
        self.homology_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.homology_frame.pack_propagate(False)  # Keep fixed height

        # Create homology figure
        self.homology_figure = Figure(figsize=(6, 0.4), dpi=100)
        self.homology_figure.patch.set_facecolor('white')
        self.homology_figure.subplots_adjust(left=0.02, right=0.98, top=0.85, bottom=0.15)

        # Create homology canvas
        self.homology_canvas = FigureCanvasTkAgg(self.homology_figure, master=self.homology_frame)
        self.homology_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Homology-minus section - horizontal layout: label + canvas
        minus_row = tk.Frame(self.floor1_frame)
        minus_row.pack(fill=tk.X, pady=2)

        tk.Label(minus_row, text="Homology-minus:",
                 font=('Arial', 10, 'bold'), width=LABEL_WIDTH, anchor='w').pack(side=tk.LEFT)

        # Frame for minus homology canvas with fixed height
        self.minus_frame = tk.Frame(minus_row, bg='white', height=RESULT_HEIGHT)
        self.minus_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.minus_frame.pack_propagate(False)  # Keep fixed height

        # Create minus homology figure
        self.minus_figure = Figure(figsize=(6, 0.4), dpi=100)
        self.minus_figure.patch.set_facecolor('white')
        self.minus_figure.subplots_adjust(left=0.02, right=0.98, top=0.85, bottom=0.15)

        # Create minus homology canvas
        self.minus_canvas = FigureCanvasTkAgg(self.minus_figure, master=self.minus_frame)
        self.minus_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Initialize with empty display
        self._clear_results_display()

    def _clear_results_display(self):
        """Clear the results display."""
        # Clear polynomial display
        self.poly_figure.clear()
        ax = self.poly_figure.add_subplot(111)
        ax.axis('off')
        ax.text(0.5, 0.5, "No results",
                ha='center', va='center', fontsize=11, color='gray')
        self.poly_canvas.draw()

        # Clear hat homology display
        self.homology_figure.clear()
        ax = self.homology_figure.add_subplot(111)
        ax.axis('off')
        ax.text(0.5, 0.5, "No results",
                ha='center', va='center', fontsize=11, color='gray')
        self.homology_canvas.draw()

        # Clear minus homology display
        self.minus_figure.clear()
        ax = self.minus_figure.add_subplot(111)
        ax.axis('off')
        ax.text(0.5, 0.5, "No results",
                ha='center', va='center', fontsize=11, color='gray')
        self.minus_canvas.draw()

    def _calculate_fontsize(self, latex_text, canvas_widget, base_fontsize=14):
        """Calculate appropriate font size based on text length and canvas width."""
        # Get current canvas width
        canvas_width = canvas_widget.winfo_width()
        if canvas_width < 10:  # Not yet rendered
            canvas_width = 400  # Default

        # For LaTeX, effective display length is shorter than raw string
        # Remove LaTeX commands for length estimation
        display_text = latex_text.replace('$', '').replace('\\', '').replace('{', '').replace('}', '')
        display_text = display_text.replace('mathbb', '').replace('oplus', '+').replace('F', 'F')
        effective_len = len(display_text)

        # Estimate pixels needed at base font size (roughly 10 pixels per char)
        estimated_width = effective_len * 10

        # Calculate scale factor (use 90% of canvas width to leave margin)
        available_width = canvas_width * 0.9

        if estimated_width > available_width:
            scale = available_width / estimated_width
            fontsize = max(8, int(base_fontsize * scale))  # Min fontsize 8
        else:
            fontsize = base_fontsize

        return fontsize

    def _update_results_display(self, polynomial_latex, homology_latex, minus_latex):
        """Update the results display with polynomial, hat homology, and minus homology."""
        # Update polynomial display
        self.poly_figure.clear()
        ax = self.poly_figure.add_subplot(111)
        ax.axis('off')
        poly_fontsize = self._calculate_fontsize(polynomial_latex, self.poly_canvas.get_tk_widget())
        ax.text(0.5, 0.5, polynomial_latex,
                ha='center', va='center', fontsize=poly_fontsize)
        self.poly_canvas.draw()

        # Update hat homology display
        self.homology_figure.clear()
        ax = self.homology_figure.add_subplot(111)
        ax.axis('off')
        homology_fontsize = self._calculate_fontsize(homology_latex, self.homology_canvas.get_tk_widget())
        ax.text(0.5, 0.5, homology_latex,
                ha='center', va='center', fontsize=homology_fontsize)
        self.homology_canvas.draw()

        # Update minus homology display
        self.minus_figure.clear()
        ax = self.minus_figure.add_subplot(111)
        ax.axis('off')
        minus_fontsize = self._calculate_fontsize(minus_latex, self.minus_canvas.get_tk_widget())
        ax.text(0.5, 0.5, minus_latex,
                ha='center', va='center', fontsize=minus_fontsize)
        self.minus_canvas.draw()

    def _format_polynomial(self, data):
        """
        Format polynomial data to LaTeX string.
        Input: {"minimal_non-zero_grading": n, "coefficients": [a, b, c, ...]}
        """
        if not data or "coefficients" not in data:
            return "N/A"

        coefficients = list(data["coefficients"])
        minimal_grading = int(data.get("minimal_non-zero_grading", 0))

        # Strip leading and trailing zeros
        while coefficients and coefficients[0] == 0:
            coefficients = coefficients[1:]
            minimal_grading += 1
        while coefficients and coefficients[-1] == 0:
            coefficients = coefficients[:-1]

        if not coefficients:
            return "$0$"

        terms = []
        for i, coef in enumerate(coefficients):
            if coef == 0:
                continue

            power = minimal_grading + i

            # Format the term
            if power == 0:
                # Just the coefficient
                term = str(coef)
            elif power == 1:
                # Coefficient + t
                if coef == 1:
                    term = "t"
                elif coef == -1:
                    term = "-t"
                else:
                    term = f"{coef}t"
            elif power == -1:
                # Coefficient + t^{-1}
                if coef == 1:
                    term = "t^{-1}"
                elif coef == -1:
                    term = "-t^{-1}"
                else:
                    term = f"{coef}t^{{-1}}"
            else:
                # General case: coefficient + t^{power}
                if coef == 1:
                    term = f"t^{{{power}}}"
                elif coef == -1:
                    term = f"-t^{{{power}}}"
                else:
                    term = f"{coef}t^{{{power}}}"

            terms.append(term)

        if not terms:
            return "$0$"

        # Join terms with proper signs
        result = terms[0]
        for term in terms[1:]:
            if term.startswith('-'):
                result += f" - {term[1:]}"
            else:
                result += f" + {term}"

        return f"${result}$"

    def _format_homology(self, grading_dict):
        """
        Format homology data to LaTeX string.
        Input: {"(-1, 0)": 1, "(0, 0)": 2, "(1, 1)": 1}
        """
        if not grading_dict:
            return "$0$"

        parsed_bigraded = []
        parsed_maslov = []
        for grading_str, dim in grading_dict.items():
            grading_str = grading_str.strip()
            if grading_str.startswith('(') and grading_str.endswith(')'):
                inner = grading_str[1:-1]
                parts = inner.split(',')
                if len(parts) == 2:
                    a, b = int(parts[0].strip()), int(parts[1].strip())
                    parsed_bigraded.append(((a, b), dim))
                    continue
            try:
                parsed_maslov.append((int(grading_str), dim))
            except ValueError:
                continue

        components = []
        if parsed_bigraded:
            parsed_bigraded.sort(key=lambda x: x[0])
            for (a, b), dim in parsed_bigraded:
                grading = f"({a},{b})"
                if dim == 1:
                    components.append(f"\\mathbb{{F}}_{{{grading}}}")
                else:
                    components.append(f"\\mathbb{{F}}_{{{grading}}}^{{{dim}}}")
        elif parsed_maslov:
            parsed_maslov.sort(key=lambda x: x[0])
            for maslov, dim in parsed_maslov:
                grading = str(maslov)
                if dim == 1:
                    components.append(f"\\mathbb{{F}}_{{{grading}}}")
                else:
                    components.append(f"\\mathbb{{F}}_{{{grading}}}^{{{dim}}}")

        if not components:
            return "$0$"

        return "$" + " \\oplus ".join(components) + "$"

    def _load_polynomial(self, knot_name):
        """Load polynomial data for a knot."""
        if not POLYNOMIAL_PATH.exists():
            return None

        try:
            with open(POLYNOMIAL_PATH) as f:
                all_polys = json.load(f)
            return all_polys.get(knot_name)
        except Exception:
            return None

    def _load_homology(self, knot_name):
        """Load hat homology data for a knot."""
        homology_path = HOMOLOGY_HAT_DIR / f"{knot_name}.json"
        if not homology_path.exists():
            return None

        try:
            with open(homology_path) as f:
                return json.load(f)
        except Exception:
            return None

    def _load_minus_homology(self, knot_name):
        """Load minus homology data for a knot."""
        minus_path = HOMOLOGY_MINUS_DIR / f"{knot_name}.json"
        if not minus_path.exists():
            return None

        try:
            with open(minus_path) as f:
                return json.load(f)
        except Exception:
            return None

    def _format_minus_homology(self, minus_data):
        """
        Format minus homology data to LaTeX string.
        Input: {"free": "(i,j)", "torsion": {order: {"(i,j)": count, ...}, ...}}
        or {"free": {"(i,j)": count, ...}, "torsion": {...}}
        """
        if not minus_data:
            return "$0$"

        components = []

        # Format free part: \mathbb{F}[U]_{(i,j)}
        if "free" in minus_data and minus_data["free"]:
            free_part = minus_data["free"]
            if isinstance(free_part, str):
                components.append(f"\\mathbb{{F}}[U]_{{{free_part}}}")
            elif isinstance(free_part, dict):
                sorted_free = sorted(free_part.items(), key=lambda x: self._parse_grading(x[0]))
                for grading_str, count in sorted_free:
                    if count == 1:
                        components.append(f"\\mathbb{{F}}[U]_{{{grading_str}}}")
                    else:
                        components.append(f"\\mathbb{{F}}[U]_{{{grading_str}}}^{{{count}}}")

        # Format torsion part order by order
        if "torsion" in minus_data and minus_data["torsion"]:
            # Sort orders numerically
            for order in sorted(minus_data["torsion"].keys(), key=lambda x: int(x)):
                gradings = minus_data["torsion"][order]
                # Sort gradings by parsing (i,j)
                sorted_gradings = sorted(gradings.items(), key=lambda x: self._parse_grading(x[0]))
                for grading_str, count in sorted_gradings:
                    if count == 1:
                        components.append(f"(\\mathbb{{F}}[U]/U^{{{order}}})_{{{grading_str}}}")
                    else:
                        components.append(f"(\\mathbb{{F}}[U]/U^{{{order}}})^{{{count}}}_{{{grading_str}}}")

        if not components:
            return "$0$"

        return "$" + " \\oplus ".join(components) + "$"

    def _parse_grading(self, grading_str):
        """Parse a grading string like '(1, 2)' into a tuple (1, 2) for sorting."""
        try:
            grading_str = grading_str.strip()
            if grading_str.startswith('(') and grading_str.endswith(')'):
                inner = grading_str[1:-1]
                parts = inner.split(',')
                if len(parts) == 2:
                    return (int(parts[0].strip()), int(parts[1].strip()))
        except Exception:
            pass
        return (0, 0)

    def _load_and_display_results(self, knot_name):
        """Load and display results if they exist."""
        poly_data = self._load_polynomial(knot_name)
        homology_data = self._load_homology(knot_name)
        minus_data = self._load_minus_homology(knot_name)

        if poly_data or homology_data or minus_data:
            if self._is_periodic_setup():
                poly_latex = "Not available"
            else:
                poly_latex = self._format_polynomial(poly_data) if poly_data else "Not computed"
            homology_latex = self._format_homology(homology_data) if homology_data else "Not computed"
            if self._is_periodic_setup():
                minus_latex = "Not available"
            else:
                minus_latex = self._format_minus_homology(minus_data) if minus_data else "Not computed"
            self._update_results_display(poly_latex, homology_latex, minus_latex)
        else:
            self._clear_results_display()

    def _update_canvas_size(self):
        """Update canvas size when grid size changes."""
        self.current_cell_size = self._calculate_cell_size()
        canvas_size = self.size * self.current_cell_size + 2 * GRID_PADDING
        self.canvas.config(width=canvas_size, height=canvas_size)

    # ==================== Drawing Functions ====================

    def _redraw(self):
        """Redraw the entire canvas."""
        self._draw_grid()
        self._draw_marks()
        if self.knot_displayed:
            self._draw_knot_lines()

    def _draw_grid(self):
        """Draw the grid with lines and symmetry axis."""
        self.canvas.delete('all')
        cell = self.current_cell_size

        # Draw grid lines
        for i in range(self.size + 1):
            # Vertical lines
            x = GRID_PADDING + i * cell
            self.canvas.create_line(
                x, GRID_PADDING,
                x, GRID_PADDING + self.size * cell,
                fill=GRID_LINE_COLOR
            )
            # Horizontal lines
            y = GRID_PADDING + i * cell
            self.canvas.create_line(
                GRID_PADDING, y,
                GRID_PADDING + self.size * cell, y,
                fill=GRID_LINE_COLOR
            )

        # Draw symmetry axis: from top-left to bottom-right in canvas coords
        # (corresponds to (0, size) to (size, 0) in math coords)
        self.canvas.create_line(
            GRID_PADDING, GRID_PADDING,
            GRID_PADDING + self.size * cell, GRID_PADDING + self.size * cell,
            fill=AXIS_COLOR, width=AXIS_WIDTH
        )

    def _draw_marks(self):
        """Draw O and X marks."""
        # Draw O marks
        for col, row in self.O_marks.items():
            self._draw_mark_at(col, row, 'O')

        # Draw X marks
        for col, row in self.X_marks.items():
            self._draw_mark_at(col, row, 'X')

    def _draw_mark_at(self, col, row, mark_type):
        """Draw a single mark at the specified cell."""
        cell = self.current_cell_size
        # Convert to canvas coordinates (flip Y)
        canvas_row = self.size - 1 - row
        x = GRID_PADDING + col * cell + cell / 2
        y = GRID_PADDING + canvas_row * cell + cell / 2

        self.canvas.create_text(
            x, y, text=mark_type,
            font=('Arial', 14, 'bold'), fill='black'
        )

    def _draw_knot_lines(self):
        """Draw the knot lines when Display Knot is toggled on."""
        if len(self.O_marks) != self.size or len(self.X_marks) != self.size:
            return

        O = self._marks_to_list(self.O_marks)
        X = self._marks_to_list(self.X_marks)

        # Compute vertical occupation
        v_occupation = self._compute_v_occupation(O, X)

        # Draw vertical lines
        self._draw_vertical_lines(O, X)

        # Draw horizontal lines with breaks at crossings
        self._draw_horizontal_lines(O, X, v_occupation)

    def _marks_to_list(self, marks_dict):
        """Convert {col: row} dict to list where list[col] = row."""
        result = [None] * self.size
        for col, row in marks_dict.items():
            result[col] = row
        return result

    def _compute_v_occupation(self, O, X):
        """Build a 2D boolean array tracking which cells have vertical lines."""
        v_occupation = [[False] * self.size for _ in range(self.size)]

        for col in range(self.size):
            row_min = min(O[col], X[col])
            row_max = max(O[col], X[col])
            for row in range(row_min, row_max + 1):
                v_occupation[col][row] = True

        return v_occupation

    def _cell_to_canvas(self, col_frac, row_frac):
        """Convert cell coordinates to canvas coordinates.

        col_frac: column as float (e.g., 2.5 for center of column 2)
        row_frac: row as float (e.g., 2.5 for center of row 2)
        Returns (canvas_x, canvas_y)
        """
        cell = self.current_cell_size
        # Flip Y coordinate
        canvas_row_frac = self.size - row_frac
        x = GRID_PADDING + col_frac * cell
        y = GRID_PADDING + canvas_row_frac * cell
        return x, y

    def _draw_vertical_lines(self, O, X):
        """Draw vertical lines for each column."""
        for col in range(self.size):
            y_O = O[col] + 0.5
            y_X = X[col] + 0.5
            y_min, y_max = sorted([y_O, y_X])

            x1, y1 = self._cell_to_canvas(col + 0.5, y_min + MARK_MARGIN)
            x2, y2 = self._cell_to_canvas(col + 0.5, y_max - MARK_MARGIN)

            self.canvas.create_line(
                x1, y1, x2, y2,
                fill=KNOT_LINE_COLOR, width=KNOT_LINE_WIDTH
            )

    def _draw_horizontal_lines(self, O, X, v_occupation):
        """Draw horizontal lines for each row with breaks at crossings."""
        # Build reverse lookup: for each row, find which column has O and X
        O_col_by_row = {O[col]: col for col in range(self.size)}
        X_col_by_row = {X[col]: col for col in range(self.size)}

        for row in range(self.size):
            col_O = O_col_by_row[row]
            col_X = X_col_by_row[row]
            col_left, col_right = sorted([col_O, col_X])

            # Build segments: start from left mark, break at vertical crossings
            segments = []
            current_start = col_left + 0.5 + MARK_MARGIN

            for col in range(col_left + 1, col_right):
                if v_occupation[col][row]:
                    # End current segment before the crossing
                    current_end = col + CROSSING_MARGIN
                    if current_start < current_end:
                        segments.append((current_start, current_end))
                    # Start new segment after the crossing
                    current_start = col + 1 - CROSSING_MARGIN

            # Final segment to right mark
            current_end = col_right + 0.5 - MARK_MARGIN
            if current_start < current_end:
                segments.append((current_start, current_end))

            # Draw all segments
            y = row + 0.5
            for x_start, x_end in segments:
                cx1, cy1 = self._cell_to_canvas(x_start, y)
                cx2, cy2 = self._cell_to_canvas(x_end, y)
                self.canvas.create_line(
                    cx1, cy1, cx2, cy2,
                    fill=KNOT_LINE_COLOR, width=KNOT_LINE_WIDTH
                )

    # ==================== Event Handlers ====================

    def _on_size_change(self, event):
        """Handle grid size change."""
        new_size = int(self.size_var.get())
        if new_size != self.size:
            # Clear marks and reset
            self.size = new_size
            self.O_marks = {}
            self.X_marks = {}
            self.knot_displayed = False
            self.btn_display.config(text="Display Knot")
            self._update_canvas_size()
            if self._is_periodic_setup():
                self._sync_periodic_x_from_o()
            self._redraw()

    def _toggle_tool(self, tool):
        """Toggle the selected tool."""
        if self.current_tool == tool:
            # Deselect
            self.current_tool = TOOL_NONE
        else:
            self.current_tool = tool
        self._update_tool_buttons()

    def _update_tool_buttons(self):
        """Update tool button appearances based on selection."""
        # Reset all buttons to inactive background
        self.btn_O.config(bg=self.inactive_bg)
        self.btn_X.config(bg=self.inactive_bg)
        self.btn_eraser.config(bg=self.inactive_bg)

        # Highlight selected tool with active background color
        if self.current_tool == TOOL_O:
            self.btn_O.config(bg=self.active_bg)
        elif self.current_tool == TOOL_X:
            self.btn_X.config(bg=self.active_bg)
        elif self.current_tool == TOOL_ERASER:
            self.btn_eraser.config(bg=self.active_bg)

    def _on_canvas_click(self, event):
        """Handle canvas click events."""
        if self.current_tool == TOOL_NONE:
            return

        cell = self.current_cell_size
        # Convert canvas coords to grid cell
        col = int((event.x - GRID_PADDING) // cell)
        row_canvas = int((event.y - GRID_PADDING) // cell)
        row = self.size - 1 - row_canvas  # Flip Y

        # Check bounds
        if not (0 <= col < self.size and 0 <= row < self.size):
            return

        if self.current_tool == TOOL_ERASER:
            self._erase_at(col, row)
        else:
            self._place_mark(col, row, self.current_tool)

        # Hide knot if displayed (marks changed)
        if self.knot_displayed:
            self.knot_displayed = False
            self.btn_display.config(text="Display Knot")

        self._redraw()

    def _place_mark(self, col, row, mark_type):
        """Place a mark at the specified cell with auto-flip."""
        if self._is_periodic_setup():
            if mark_type != TOOL_O:
                return
            if not self._can_place_mark(col, row, mark_type):
                messagebox.showwarning(
                    "Invalid Placement",
                    "Cannot place O here. Check row/column/axis/symmetry constraints.",
                )
                return
            self.O_marks[col] = row
            self._sync_periodic_x_from_o()
            return

        marks = self.O_marks if mark_type == TOOL_O else self.X_marks

        # Check constraints before placing
        if not self._can_place_mark(col, row, mark_type):
            messagebox.showwarning("Invalid Placement",
                f"Cannot place {mark_type} here. Check row/column/axis constraints.")
            return

        # Place mark
        marks[col] = row

        # Auto-flip if not on axis
        if col + row != self.size - 1:
            flip_col = self.size - 1 - row
            flip_row = self.size - 1 - col

            # Check flip constraints (skip if would conflict)
            if self._can_place_mark(flip_col, flip_row, mark_type, is_flip=True):
                marks[flip_col] = flip_row

    def _can_place_mark(self, col, row, mark_type, is_flip=False):
        """Check if a mark can be placed at the specified cell."""
        marks = self.O_marks if mark_type == TOOL_O else self.X_marks

        # Check if column already has this mark type (unless replacing same position)
        if col in marks and marks[col] != row:
            return False

        # Check if row already has this mark type
        for c, r in marks.items():
            if r == row and c != col:
                return False

        on_axis = (col + row == self.size - 1)
        if self._is_periodic_setup():
            if on_axis:
                return False

            reflected_col = self.size - 1 - row
            reflected_row = self.size - 1 - col
            for existing_col, existing_row in self.O_marks.items():
                if existing_col == col and existing_row == row:
                    continue
                if existing_col == reflected_col and existing_row == reflected_row:
                    return False
            return True

        # Strongly invertible odd-size setup: at most one axis mark of each type.
        # Strongly invertible even-size setup: axis O marks are allowed, axis X marks are not.
        if on_axis:
            if self.size % 2 == 0:
                return mark_type == TOOL_O
            for c, r in marks.items():
                if c + r == self.size - 1 and c != col:
                    return False

        return True

    def _erase_at(self, col, row):
        """Erase marks at the specified cell with auto-flip."""
        if self._is_periodic_setup():
            removed = False
            if col in self.O_marks and self.O_marks[col] == row:
                del self.O_marks[col]
                removed = True
            else:
                source_col = self.size - 1 - row
                source_row = self.size - 1 - col
                if source_col in self.O_marks and self.O_marks[source_col] == source_row:
                    del self.O_marks[source_col]
                    removed = True
            if removed:
                self._sync_periodic_x_from_o()
            return

        # Check O marks
        if col in self.O_marks and self.O_marks[col] == row:
            del self.O_marks[col]
            # Erase symmetric point
            if col + row != self.size - 1:
                flip_col = self.size - 1 - row
                if flip_col in self.O_marks:
                    del self.O_marks[flip_col]

        # Check X marks
        if col in self.X_marks and self.X_marks[col] == row:
            del self.X_marks[col]
            # Erase symmetric point
            if col + row != self.size - 1:
                flip_col = self.size - 1 - row
                if flip_col in self.X_marks:
                    del self.X_marks[flip_col]

    def _on_clear(self):
        """Handle Clear All button click."""
        if self.O_marks or self.X_marks:
            if messagebox.askyesno("Confirm Clear", "Clear all marks?"):
                self.O_marks = {}
                self.X_marks = {}
                self.knot_displayed = False
                self.btn_display.config(text="Display Knot")
                self._redraw()

    def _on_toggle_display(self):
        """Handle Display Knot button click."""
        if self.knot_displayed:
            # Hide knot
            self.knot_displayed = False
            self.btn_display.config(text="Display Knot")
            self._redraw()
        else:
            # Validate and show knot
            if self._validate_complete():
                self.knot_displayed = True
                self.btn_display.config(text="Hide Knot")
                self._redraw()

    def _validate_complete(self):
        """Validate that the knot configuration is complete and valid."""
        errors = []

        # Check each column has exactly one O and one X
        if len(self.O_marks) != self.size:
            errors.append(f"Need {self.size} O marks, have {len(self.O_marks)}")
        if len(self.X_marks) != self.size:
            errors.append(f"Need {self.size} X marks, have {len(self.X_marks)}")

        # Check each row has exactly one O and one X
        O_rows = set(self.O_marks.values())
        X_rows = set(self.X_marks.values())
        if len(O_rows) != len(self.O_marks):
            errors.append("Multiple O marks in same row")
        if len(X_rows) != len(self.X_marks):
            errors.append("Multiple X marks in same row")

        if self._is_periodic_setup():
            if self.size % 2 == 0:
                errors.append("Periodic setup currently requires odd grid size")
            O_on_axis = sum(1 for c, r in self.O_marks.items() if c + r == self.size - 1)
            X_on_axis = sum(1 for c, r in self.X_marks.items() if c + r == self.size - 1)
            if O_on_axis != 0:
                errors.append(f"Need 0 O on axis, have {O_on_axis}")
            if X_on_axis != 0:
                errors.append(f"Need 0 X on axis, have {X_on_axis}")
            reflected_x = {
                self.size - 1 - row: self.size - 1 - col
                for col, row in self.O_marks.items()
            }
            if reflected_x != self.X_marks:
                errors.append("X marks must be the mirror image of O marks in periodic mode")
            overlap = {
                (col, row)
                for col, row in self.O_marks.items()
                if self.X_marks.get(col) == row
            }
            if overlap:
                errors.append("O and X marks overlap; periodic marks must be off the axis")
        else:
            O_on_axis = sum(1 for c, r in self.O_marks.items() if c + r == self.size - 1)
            X_on_axis = sum(1 for c, r in self.X_marks.items() if c + r == self.size - 1)
            if self.size % 2 == 0:
                if O_on_axis <= 0 or O_on_axis % 2 != 0:
                    errors.append(
                        "Even-size strongly invertible setup requires a positive even number of O marks on the axis"
                    )
                if X_on_axis != 0:
                    errors.append(f"Need 0 X on axis in even strong setup, have {X_on_axis}")
            else:
                if O_on_axis != 1:
                    errors.append(f"Need exactly 1 O on axis, have {O_on_axis}")
                if X_on_axis != 1:
                    errors.append(f"Need exactly 1 X on axis, have {X_on_axis}")

        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return False
        return True

    def _get_current_knot_data(self):
        """Get current knot data as a dictionary."""
        name = self.name_entry.get().strip()
        if self._is_periodic_setup():
            self._sync_periodic_x_from_o()
        O_list = self._marks_to_list(self.O_marks)
        X_list = self._marks_to_list(self.X_marks)
        return {
            "name": name,
            "size": self.size,
            "O": O_list,
            "X": X_list
        }

    def _knot_data_equals(self, data1, data2):
        """Check if two knot data dictionaries are equal."""
        return (data1.get("size") == data2.get("size") and
                data1.get("O") == data2.get("O") and
                data1.get("X") == data2.get("X"))

    def _save_knot_for_compute(self):
        """
        Smart save before computation.
        Returns True if save succeeded or was skipped (data identical).
        Returns False if user cancelled.
        """
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter a knot name")
            return False

        # Validate marks
        if not self._validate_complete():
            return False

        save_path = KNOTS_DIR / f"{name}.json"
        current_data = self._get_current_knot_data()

        if save_path.exists():
            # Load existing data and compare
            try:
                with open(save_path) as f:
                    existing_data = json.load(f)

                if self._knot_data_equals(current_data, existing_data):
                    # Data is identical, skip save silently
                    return True
                else:
                    # Data is different, ask for confirmation
                    if not messagebox.askyesno("Data Changed",
                            f"Knot data has changed. Save changes before computing?"):
                        return False
            except Exception:
                # If we can't read existing file, ask for confirmation
                if not messagebox.askyesno("File Exists",
                        f"Knot '{name}' already exists. Replace?"):
                    return False

        # Save the knot
        save_json(save_path, current_data)

        return True

    def _on_save(self):
        """Handle Save button click."""
        # Validate knot name
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter a knot name")
            return

        # Validate marks
        if not self._validate_complete():
            return

        save_path = KNOTS_DIR / f"{name}.json"
        current_data = self._get_current_knot_data()

        if save_path.exists():
            # Load existing data and compare
            try:
                with open(save_path) as f:
                    existing_data = json.load(f)

                if self._knot_data_equals(current_data, existing_data):
                    # Data is identical, skip save silently
                    return
                else:
                    # Data is different, ask for confirmation
                    if not messagebox.askyesno("File Exists",
                            f"Knot '{name}' already exists with different data. Replace?"):
                        return
            except Exception:
                # If we can't read existing file, ask for confirmation
                if not messagebox.askyesno("File Exists",
                        f"Knot '{name}' already exists. Replace?"):
                    return

        # Save
        save_json(save_path, current_data)

        messagebox.showinfo("Saved", f"Knot saved to {save_path}")

    # ==================== Computation ====================

    def _on_compute(self):
        """Handle Compute Invariants button click."""
        if self.computing:
            messagebox.showwarning("Busy", "Computation already in progress")
            return

        # Validate knot
        if not self._validate_complete():
            return

        # Smart save first
        if not self._save_knot_for_compute():
            return  # User cancelled save, terminate computation

        knot_name = self.name_entry.get().strip()
        mode = self.mode_var.get()

        # Check if results already exist
        poly_exists = self._load_polynomial(knot_name) is not None
        homology_exists = self._load_homology(knot_name) is not None
        minus_exists = self._load_minus_homology(knot_name) is not None
        needs_poly = not self._is_periodic_setup() and self.size <= SIZE_LIMIT_POLYNOMIAL
        needs_minus = not self._is_periodic_setup() and self.size <= SIZE_LIMIT_MINUS

        if homology_exists and (poly_exists or not needs_poly) and (minus_exists or not needs_minus):
            if not messagebox.askyesno("Results Exist",
                    f"Computation results already exist for '{knot_name}'. Re-compute?"):
                return

        # Start computation
        self._start_computation(knot_name, mode)

    def _start_computation(self, knot_name, mode):
        """Start the computation in a background thread."""
        self.computing = True
        self.btn_compute.config(state='disabled')
        self._start_timer()
        self._update_progress("Starting computation...")

        def computation_task():
            try:
                # Create a custom log function that updates progress
                def progress_callback(message):
                    self.root.after(0, lambda m=message: self._update_progress(m))

                # Run the workflow
                run_workflow(knot_name, mode, progress_callback=progress_callback)

                self.root.after(0, self._on_computation_complete)
            except Exception as e:
                self.root.after(0, lambda e=e: self._on_computation_error(str(e)))

        thread = threading.Thread(target=computation_task, daemon=True)
        thread.start()

    def _start_timer(self):
        """Start the timer display."""
        self.timer_start = time.time()
        self.timer_running = True
        self._update_timer()

    def _update_timer(self):
        """Update the timer display."""
        if self.timer_running:
            elapsed = time.time() - self.timer_start
            minutes, seconds = divmod(int(elapsed), 60)
            timer_str = f"[{minutes:02d}:{seconds:02d}]"
            self.progress_label.config(text=f"{self.current_progress_message} {timer_str}")
            self.root.after(500, self._update_timer)

    def _stop_timer(self):
        """Stop the timer."""
        self.timer_running = False

    def _update_progress(self, message):
        """Update the progress display."""
        self.current_progress_message = message
        if self.timer_running:
            elapsed = time.time() - self.timer_start
            minutes, seconds = divmod(int(elapsed), 60)
            timer_str = f"[{minutes:02d}:{seconds:02d}]"
            self.progress_label.config(text=f"{message} {timer_str}")
        else:
            self.progress_label.config(text=message)

    def _on_computation_complete(self):
        """Handle computation completion."""
        self._stop_timer()
        self.computing = False
        self.btn_compute.config(state='normal')

        # Update progress with final time
        elapsed = time.time() - self.timer_start
        minutes, seconds = divmod(int(elapsed), 60)
        self._update_progress(f"Complete [{minutes:02d}:{seconds:02d}]")

        # Load and display results
        knot_name = self.name_entry.get().strip()
        self._load_and_display_results(knot_name)

        messagebox.showinfo("Complete", f"Computation complete for '{knot_name}'")

    def _on_computation_error(self, error_msg):
        """Handle computation error."""
        self._stop_timer()
        self.computing = False
        self.btn_compute.config(state='normal')
        self._update_progress("Error")
        messagebox.showerror("Computation Error", f"An error occurred:\n{error_msg}")


if __name__ == "__main__":
    if UI_IMPORT_ERROR is not None:
        raise SystemExit(
            "Tk UI dependencies are unavailable in this Python environment. "
            f"Original error: {UI_IMPORT_ERROR}"
        )
    root = tk.Tk()
    app = KnotInputApp(root)
    root.mainloop()
