from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
KNOTS_DIR = DATA_DIR / "knots"

GENERATORS_DIR = DATA_DIR / "generators"
RECTANGLES_DIR = DATA_DIR / "rectangles"
DOMAINS_DIR = DATA_DIR / "domains"
GRADING_DIR = DATA_DIR / "grading"
POLYNOMIAL_DIR = DATA_DIR / "polynomial"
HAT_DIR = DATA_DIR / "homology" / "hat"
MINUS_DIR = DATA_DIR / "homology" / "minus"
