"""Aperçu autonome de la fenêtre glass de l'assistant.

Lancer :  python tools/glass_preview.py
Ouvre un petit fond coloré + la fenêtre glass par-dessus (pour juger le flou
acrylique, la teinte et l'animation). Échap ou clic hors fenêtre pour fermer.
Un bouton « Ouvrir » rejoue l'animation d'éclosion.
"""
import sys
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QLabel

sys.path.insert(0, r"C:\neoSlice")
from ui.components.glass_panel import GlassPanel


def main():
    app = QApplication(sys.argv)
    # Un fond bien coloré pour VOIR le flou acrylique par-dessus
    bg = QWidget()
    bg.setWindowTitle("Aperçu glass — fond de démo")
    bg.resize(1000, 700)
    bg.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                     "stop:0 #12203a, stop:0.5 #3a1a4a, stop:1 #0a1530);")
    lay = QVBoxLayout(bg)
    hint = QLabel("Voici un fond coloré. La fenêtre glass floute ce qui est derrière.\n"
                  "Bouge la fenêtre glass par-dessus le texte pour voir l'effet.")
    hint.setFont(QFont("Segoe UI", 13)); hint.setStyleSheet("color: #cfe;")
    hint.setAlignment(Qt.AlignCenter)
    lay.addWidget(hint)

    panel = GlassPanel(bg)   # rattaché au fond → se ferme avec lui

    btn = QPushButton("Ouvrir l'assistant (animation)")
    btn.setFixedHeight(40)
    btn.clicked.connect(lambda: panel.open_from(QPoint(bg.x() + 120, bg.y() + bg.height() - 40)))
    lay.addWidget(btn)

    bg.show()
    panel.open_from(QPoint(bg.x() + 120, bg.y() + bg.height() - 40))
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
