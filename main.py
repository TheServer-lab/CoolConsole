import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from renderer.terminal_widget import CoolConsoleWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("CoolConsole")

    root = Path(__file__).resolve().parent
    window = CoolConsoleWindow(root)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
