"""Effet « Strands » (rubans lumineux dans une boule de verre) en OpenGL natif Qt.

Porté du composant React Bits (https://reactbits.dev/animations/strands) : on ne
garde QUE les 2 shaders GLSL (le cœur de l'effet), le reste (React/ogl/CSS) est
remplacé par du Qt natif → aucune dépendance web.

Utilisable en overlay transparent au-dessus d'un autre widget (ex. le viewer 3D) :
    w = StrandsWidget(parent, overlay=True)
    w.resize(150, 150); w.move(12, parent.height() - 162); w.raise_()

⚠️ PIÈGE PySide6 : QOpenGLShaderProgram.setUniformValue() est silencieusement
inopérant ici → on passe TOUJOURS par les fonctions GL brutes (glUniform*).
"""
from __future__ import annotations
import numpy as np

from PySide6.QtCore import Qt, QTimer, QElapsedTimer, Signal
from PySide6.QtGui import (QSurfaceFormat, QOffscreenSurface, QOpenGLContext, QPixmap,
                           QRegion)
from PySide6.QtWidgets import QLabel
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtOpenGL import (
    QOpenGLShader, QOpenGLShaderProgram, QOpenGLFramebufferObject,
    QOpenGLBuffer, QOpenGLVertexArrayObject,
)

# Constantes OpenGL (évite une dépendance à PyOpenGL)
GL_COLOR_BUFFER_BIT = 0x00004000
GL_TRIANGLES = 0x0004
GL_FLOAT = 0x1406
GL_BLEND = 0x0BE2
GL_ONE = 1
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE0 = 0x84C0
GL_FRAMEBUFFER = 0x8D40

MAX_STRANDS = 12
MAX_COLORS = 8

VERT = """#version 330 core
in vec2 position;
void main() { gl_Position = vec4(position, 0.0, 1.0); }
"""

FRAG = f"""#version 330 core
uniform float uTime;
uniform vec2 uResolution;
uniform vec3 uColors[{MAX_COLORS}];
uniform int uColorCount;
uniform int uStrandCount;
uniform float uSpeed, uAmplitude, uWaviness, uThickness, uGlow, uTaper, uSpread,
              uHueShift, uIntensity, uOpacity, uScale, uSaturation;
out vec4 fragColor;
const float PI = 3.14159265;
vec3 spectrum(float t) {{ return 0.5 + 0.5 * cos(2.0 * PI * (t + vec3(0.00, 0.33, 0.67))); }}
vec3 samplePalette(float t) {{
  t = fract(t);
  float scaled = t * float(uColorCount);
  int idx = int(floor(scaled));
  float blend = fract(scaled);
  int nextIdx = idx + 1;
  if (nextIdx >= uColorCount) nextIdx = 0;
  return mix(uColors[idx], uColors[nextIdx], blend);
}}
vec3 strandColor(float t) {{ if (uColorCount > 0) return samplePalette(t); return spectrum(t); }}
void main() {{
  vec2 uv = (gl_FragCoord.xy - 0.5 * uResolution) / uResolution.y;
  uv /= max(uScale, 0.0001);
  float e = 0.06 + uIntensity * 0.94;
  float env = pow(max(cos(uv.x * PI * 1.3), 0.0), uTaper);
  vec3 col = vec3(0.0);
  for (int i = 0; i < {MAX_STRANDS}; i++) {{
    if (i >= uStrandCount) break;
    float fi = float(i);
    float ph = fi * 1.7 * uSpread;
    float freq = (2.0 + fi * 0.35) * uWaviness;
    float spd = 1.4 + fi * 1.2;
    float tt = uTime * uSpeed;
    float w = sin(uv.x * freq + tt * spd + ph) * 0.60
            + sin(uv.x * freq * 1.1 - tt * spd * 0.7 + ph * 1.7) * 0.40;
    float amp = (0.1 + 0.02 * e) * env * uAmplitude;
    float y = w * amp;
    float d = abs(uv.y - y);
    float thick = (0.001 + 0.05 * e) * (0.35 + env) * uThickness;
    float g = thick / (d + thick * 0.45);
    g = g * g;
    float h = fi / float(uStrandCount) + uv.x * 0.30 + uTime * 0.04 + uHueShift;
    col += strandColor(h) * g * env;
  }}
  col *= 0.45 + 0.7 * e;
  col = 1.0 - exp(-col * uGlow);
  float gray = dot(col, vec3(0.2126, 0.7152, 0.0722));
  col = max(mix(vec3(gray), col, uSaturation), 0.0);
  float lum = max(max(col.r, col.g), col.b);
  float alpha = clamp(lum, 0.0, 1.0) * uOpacity;
  fragColor = vec4(col * uOpacity, alpha);
}}
"""

GLASS_FRAG = """#version 330 core
uniform sampler2D uScene;
uniform vec2 uResolution;
uniform float uRadius, uRefraction, uDispersion;
out vec4 fragColor;
vec2 toUv(vec2 p) { return p * (uResolution.y / uResolution) + 0.5; }
void main() {
  vec2 p = (gl_FragCoord.xy - 0.5 * uResolution) / uResolution.y;
  float d = length(p);
  float r = uRadius;
  float edge = fwidth(d) * 1.5;
  float mask = 1.0 - smoothstep(r - edge, r + edge, d);
  if (mask <= 0.0) { fragColor = vec4(0.0); return; }
  float z = sqrt(max(r * r - d * d, 0.0)) / r;
  float nd = d / r;
  vec2 dir = d > 0.0 ? p / d : vec2(0.0);
  float lens = smoothstep(0.85, 1.0, nd) * pow(nd, 6.0);
  vec2 offset = -dir * lens * uRefraction * 0.15;
  vec2 disp = -dir * lens * uDispersion * 0.012;
  vec3 light;
  light.r = texture(uScene, toUv(p + offset - disp)).r;
  light.g = texture(uScene, toUv(p + offset)).g;
  light.b = texture(uScene, toUv(p + offset + disp)).b;
  float fres = pow(1.0 - z, 3.0);
  vec3 rim = vec3(1.0) * fres * 0.18;
  vec2 lightDir = normalize(vec2(-0.55, 0.6));
  float spec = pow(max(dot(p / max(r, 1e-4), lightDir), 0.0), 6.0);
  spec *= smoothstep(r, r * 0.55, d);
  vec3 emissive = light + rim + vec3(spec) * 0.4;
  float emissiveA = clamp(max(max(emissive.r, emissive.g), emissive.b), 0.0, 1.0);
  float bodyA = 0.05 + fres * 0.05;
  float outA = emissiveA + bodyA * (1.0 - emissiveA);
  vec3 outRGB = emissive;
  outRGB *= mask; outA *= mask;
  fragColor = vec4(outRGB, outA);
}
"""


def _hex(c: str):
    c = c.lstrip("#")
    return (int(c[0:2], 16) / 255.0, int(c[2:4], 16) / 255.0, int(c[4:6], 16) / 255.0)


class StrandsOverlay(QLabel):
    """Effet Strands rendu HORS-ÉCRAN (GL offscreen) puis affiché dans un QLabel
    transparent. Contrairement à un QOpenGLWidget, un QLabel est un widget Qt normal
    → il se compose correctement par-dessus la fenêtre native de VTK (le viewer 3D).
    Clics traversants (WA_TransparentForMouseEvents)."""

    clicked = Signal()   # émis au clic sur la sphère

    def __init__(self, parent=None, px=150,
                 colors=("#F97316", "#7C3AED", "#06B6D4"),
                 count=4, speed=0.5, amplitude=0.8, waviness=0.8, thickness=0.9,
                 glow=3.0, taper=3.4, spread=0.9, hueShift=0.18, intensity=0.45,
                 saturation=2.0, opacity=1.0, scale=1.2, glass=True, refraction=1.0,
                 dispersion=1.0, glassSize=0.49, bg=(0.03, 0.03, 0.05), translucent=False):
        super().__init__(parent)
        self._pulse = 0.0        # flash au clic (décroît chaque frame)
        self._hover_target = 0.0  # 1 au survol, 0 sinon
        self._hover = 0.0         # valeur lissée du survol
        self._active = False      # True pendant que l'IA rédige
        self._active_level = 0.0  # valeur lissée de l'état actif
        if translucent:
            # Mini-fenêtre top-level VRAIMENT transparente (composée par le système,
            # au-dessus de la fenêtre native VTK). CLIQUABLE (pas de TransparentForInput) :
            # un masque circulaire limite la zone cliquable/dessinée à la sphère → le
            # reste du carré laisse passer les clics vers le viewer.
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool
                                | Qt.NoDropShadowWindowHint)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setAttribute(Qt.WA_ShowWithoutActivating)
            self.setCursor(Qt.PointingHandCursor)
            self._bg = (0.0, 0.0, 0.0, 0.0)   # fond transparent réel
        else:
            # Fond opaque = couleur du viewer (fallback si pas de translucence).
            self._bg = (float(bg[0]), float(bg[1]), float(bg[2]), 1.0)
        self.p = dict(colors=[_hex(c) for c in colors], count=count, speed=speed,
                      amplitude=amplitude, waviness=waviness, thickness=thickness,
                      glow=glow, taper=taper, spread=spread, hueShift=hueShift,
                      intensity=intensity, saturation=saturation, opacity=opacity,
                      scale=scale, glass=glass, refraction=refraction,
                      dispersion=dispersion, glassSize=glassSize)
        self._px = px
        self.setFixedSize(px, px)
        self.setStyleSheet("background: transparent;")
        if translucent:
            # Masque circulaire (rayon ~ sphère + halo) → clics hors cercle traversent.
            m = int(px * 0.34)
            self.setMask(QRegion(px // 2 - m, px // 2 - m, 2 * m, 2 * m, QRegion.Ellipse))
        else:
            self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._ctx = self._surf = self._f = None
        self._prog = self._glass = self._vao = self._vbo = None
        self._fbo_scene = self._fbo_out = None
        self._fdim = 0
        self._ready = None   # None=pas tenté, True/False=résultat
        self._clock = QElapsedTimer(); self._clock.start()
        self._timer = QTimer(self); self._timer.timeout.connect(self._render)
        self._timer.start(33)   # ~30 fps (largement suffisant, économe)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._pulse = 1.0
            self.clicked.emit()
            e.accept()

    def enterEvent(self, e):
        self._hover_target = 1.0

    def leaveEvent(self, e):
        self._hover_target = 0.0

    def set_active(self, on: bool):
        """Active l'animation soutenue (vagues plus vives) pendant la rédaction."""
        self._active = bool(on)

    def _init_gl(self) -> bool:
        if self._ready is not None:
            return self._ready
        from loguru import logger
        try:
            fmt = QSurfaceFormat()
            fmt.setVersion(3, 3); fmt.setProfile(QSurfaceFormat.CoreProfile)
            fmt.setAlphaBufferSize(8)
            self._surf = QOffscreenSurface(); self._surf.setFormat(fmt); self._surf.create()
            self._ctx = QOpenGLContext(); self._ctx.setFormat(fmt)
            if not self._ctx.create() or not self._ctx.makeCurrent(self._surf):
                raise RuntimeError("contexte GL offscreen indisponible")
            self._f = self._ctx.functions()
            self._prog, m = self._make_program(FRAG)
            self._glass, g = self._make_program(GLASS_FRAG)
            verts = np.array([-1, -1, 3, -1, -1, 3], dtype=np.float32)
            self._vao = QOpenGLVertexArrayObject(); self._vao.create(); self._vao.bind()
            self._vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer); self._vbo.create(); self._vbo.bind()
            self._vbo.allocate(verts.tobytes(), verts.nbytes); self._vao.release()
            self._ctx.doneCurrent()
            self._ready = bool(m and g)
            logger.info(f"[Strands] overlay GL ok={self._ready} (offscreen)")
        except Exception as e:
            self._ready = False
            self._timer.stop()
            logger.warning(f"[Strands] overlay init failed: {e}")
        return self._ready

    def _make_program(self, frag):
        prog = QOpenGLShaderProgram()
        prog.addShaderFromSourceCode(QOpenGLShader.Vertex, VERT)
        prog.addShaderFromSourceCode(QOpenGLShader.Fragment, frag)
        return prog, prog.link()

    def _u(self, prog, name, *vals):
        loc = prog.uniformLocation(name)
        if loc < 0:
            return
        n = len(vals)
        if n == 1:
            v = vals[0]
            self._f.glUniform1i(loc, v) if isinstance(v, int) else self._f.glUniform1f(loc, float(v))
        elif n == 2:
            self._f.glUniform2f(loc, float(vals[0]), float(vals[1]))
        elif n == 3:
            self._f.glUniform3f(loc, float(vals[0]), float(vals[1]), float(vals[2]))

    def _set_main(self, prog, dim):
        p = self.p
        self._u(prog, "uTime", float(self._clock.elapsed() * 0.001))
        self._u(prog, "uResolution", float(dim), float(dim))
        cols = p["colors"] or [(1, 1, 1)]
        for i in range(MAX_COLORS):
            r, g, b = cols[i] if i < len(cols) else cols[-1]
            self._u(prog, f"uColors[{i}]", r, g, b)
        self._u(prog, "uColorCount", int(min(len(cols), MAX_COLORS)))
        self._u(prog, "uStrandCount", int(min(max(int(round(p["count"])), 1), MAX_STRANDS)))
        pulse = self._pulse          # halo doux au clic (décroît lentement)
        hov = self._hover            # survol lissé (0..1)
        act = self._active_level     # rédaction lissée (0..1)
        for name, key in (("uWaviness", "waviness"), ("uThickness", "thickness"),
                          ("uTaper", "taper"), ("uSpread", "spread"),
                          ("uHueShift", "hueShift"), ("uOpacity", "opacity"),
                          ("uSaturation", "saturation")):
            self._u(prog, name, float(p[key]))
        # Respiration lente et douce (pas d'accélération des vagues → aucun
        # scintillement). Le clic ne fait PLUS clignoter : juste un halo qui monte
        # puis se retire. Pendant qu'elle "parle", surtout du glow, tout en douceur.
        breathe = 0.5 + 0.5 * np.sin(self._clock.elapsed() * 0.0016)  # 0..1, lent
        self._u(prog, "uSpeed", float(p["speed"]))                    # vitesse constante
        self._u(prog, "uAmplitude", float(p["amplitude"] * (1.0 + act * 0.08)))
        self._u(prog, "uIntensity",
                float(p["intensity"] + pulse * 0.14 + hov * 0.14 + act * (0.16 + 0.08 * breathe)))
        self._u(prog, "uGlow",
                float(p["glow"] + pulse * 0.9 + hov * 0.8 + act * (1.5 + 0.6 * breathe)))
        self._u(prog, "uScale", float(p["scale"]))

    def _draw(self, prog):
        prog.bind(); self._vao.bind(); self._vbo.bind()
        prog.enableAttributeArray("position")
        prog.setAttributeBuffer("position", GL_FLOAT, 0, 2)
        self._f.glDrawArrays(GL_TRIANGLES, 0, 3)
        self._vao.release(); prog.release()

    def _render(self):
        if not self.isVisible() or not self._init_gl():
            return
        if self._pulse > 0.001:
            self._pulse *= 0.93   # halo de clic qui se retire en douceur (pas de flash)
        else:
            self._pulse = 0.0
        # Lissage fluide du survol et de l'état « en train de rédiger »
        self._hover += (self._hover_target - self._hover) * 0.20
        self._active_level += ((1.0 if self._active else 0.0) - self._active_level) * 0.12
        try:
            dpr = self.devicePixelRatioF() or 1.0
            dim = max(2, int(self._px * dpr))
            self._ctx.makeCurrent(self._surf)
            f = self._f
            if self._fdim != dim:
                self._fbo_scene = QOpenGLFramebufferObject(dim, dim)
                self._fbo_out = QOpenGLFramebufferObject(dim, dim)
                self._fdim = dim
            f.glViewport(0, 0, dim, dim)
            f.glEnable(GL_BLEND); f.glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)
            # Passe 1 : rubans -> fbo_scene
            self._fbo_scene.bind()
            f.glClearColor(0.0, 0.0, 0.0, 0.0); f.glClear(GL_COLOR_BUFFER_BIT)
            self._prog.bind(); self._set_main(self._prog, dim); self._prog.release()
            self._draw(self._prog)
            self._fbo_scene.release()
            if self.p["glass"]:
                self._fbo_out.bind()
                f.glClearColor(*self._bg); f.glClear(GL_COLOR_BUFFER_BIT)
                self._glass.bind()
                f.glActiveTexture(GL_TEXTURE0)
                f.glBindTexture(GL_TEXTURE_2D, self._fbo_scene.texture())
                self._u(self._glass, "uScene", int(0))
                self._u(self._glass, "uResolution", float(dim), float(dim))
                # La boule grossit doucement au survol (et un peu pendant la rédaction)
                eff_gs = self.p["glassSize"] * (1.0 + self._hover * 0.17 + self._active_level * 0.06)
                self._u(self._glass, "uRadius", float(0.46 * eff_gs))
                self._u(self._glass, "uRefraction", float(self.p["refraction"]))
                self._u(self._glass, "uDispersion", float(self.p["dispersion"]))
                self._glass.release()
                self._draw(self._glass)
                img = self._fbo_out.toImage()
                self._fbo_out.release()
            else:
                img = self._fbo_scene.toImage()
            self._ctx.doneCurrent()
            img.setDevicePixelRatio(dpr)
            self.setPixmap(QPixmap.fromImage(img))
        except Exception:
            pass


class StrandsWidget(QOpenGLWidget):
    """Effet Strands + boule de verre. `overlay=True` → fond transparent + clics
    qui traversent (pour se poser au-dessus du viewer 3D)."""

    def __init__(self, parent=None, overlay=True,
                 colors=("#F97316", "#7C3AED", "#06B6D4"),
                 count=4, speed=0.5, amplitude=0.8, waviness=0.8, thickness=0.9,
                 glow=3.0, taper=3.4, spread=0.9, hueShift=0.18, intensity=0.45,
                 saturation=2.0, opacity=1.0, scale=1.2, glass=True, refraction=1.0,
                 dispersion=1.0, glassSize=0.57, bg=(0.0, 0.0, 0.0, 0.0)):
        super().__init__(parent)
        self.p = dict(colors=[_hex(c) for c in colors], count=count, speed=speed,
                      amplitude=amplitude, waviness=waviness, thickness=thickness,
                      glow=glow, taper=taper, spread=spread, hueShift=hueShift,
                      intensity=intensity, saturation=saturation, opacity=opacity,
                      scale=scale, glass=glass, refraction=refraction,
                      dispersion=dispersion, glassSize=glassSize)
        self._bg = bg
        self._ok = False
        self._w = self._h = 1
        self._fbo = None

        fmt = QSurfaceFormat()
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setAlphaBufferSize(8)
        self.setFormat(fmt)
        if overlay:
            # Transparent au-dessus du viewer + clics qui passent au travers
            self.setAttribute(Qt.WA_AlwaysStackOnTop)
            self.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.setAttribute(Qt.WA_NoSystemBackground)

        self._clock = QElapsedTimer(); self._clock.start()
        self._timer = QTimer(self); self._timer.timeout.connect(self.update)
        self._timer.start(16)  # ~60 fps

    # ── GL ──────────────────────────────────────────────────────────────────
    def initializeGL(self):
        from loguru import logger
        try:
            self._f = self.context().functions()
            fmt = self.format()
            ver = None
            try:
                ver = bytes(self._f.glGetString(0x1F02)).decode(errors="ignore")  # GL_VERSION
            except Exception:
                pass
            self._prog, m_ok = self._make_program(FRAG)
            self._glass, g_ok = self._make_program(GLASS_FRAG)
            verts = np.array([-1, -1, 3, -1, -1, 3], dtype=np.float32)
            self._vao = QOpenGLVertexArrayObject(); self._vao.create(); self._vao.bind()
            self._vbo = QOpenGLBuffer(QOpenGLBuffer.VertexBuffer); self._vbo.create(); self._vbo.bind()
            self._vbo.allocate(verts.tobytes(), verts.nbytes)
            self._vao.release()
            self._ok = m_ok and g_ok
            logger.info(f"[Strands] init ok={self._ok} version='{ver}' "
                        f"profile={fmt.profile()} alpha={fmt.alphaBufferSize()} "
                        f"main_link={m_ok} glass_link={g_ok}")
        except Exception as e:
            self._ok = False
            self._timer.stop()
            logger.warning(f"[Strands] initializeGL failed: {e}")

    def _make_program(self, frag):
        prog = QOpenGLShaderProgram(self)
        prog.addShaderFromSourceCode(QOpenGLShader.Vertex, VERT)
        prog.addShaderFromSourceCode(QOpenGLShader.Fragment, frag)
        ok = prog.link()
        if not ok:
            from loguru import logger
            logger.warning(f"[Strands] shader link failed: {prog.log()}")
        return prog, ok

    def resizeGL(self, w, h):
        self._w, self._h = max(1, w), max(1, h)
        if self._ok:
            self._fbo = QOpenGLFramebufferObject(self._w, self._h)

    def _u(self, prog, name, *vals):
        loc = prog.uniformLocation(name)
        if loc < 0:
            return
        n = len(vals)
        if n == 1:
            v = vals[0]
            if isinstance(v, int):
                self._f.glUniform1i(loc, v)
            else:
                self._f.glUniform1f(loc, float(v))
        elif n == 2:
            self._f.glUniform2f(loc, float(vals[0]), float(vals[1]))
        elif n == 3:
            self._f.glUniform3f(loc, float(vals[0]), float(vals[1]), float(vals[2]))

    def _set_main(self, prog):
        p = self.p
        self._u(prog, "uTime", float(self._clock.elapsed() * 0.001))
        self._u(prog, "uResolution", float(self._w), float(self._h))
        cols = p["colors"] or [(1, 1, 1)]
        for i in range(MAX_COLORS):
            r, g, b = cols[i] if i < len(cols) else cols[-1]
            self._u(prog, f"uColors[{i}]", r, g, b)
        self._u(prog, "uColorCount", int(min(len(cols), MAX_COLORS)))
        self._u(prog, "uStrandCount", int(min(max(int(round(p["count"])), 1), MAX_STRANDS)))
        for name, key in (("uSpeed", "speed"), ("uAmplitude", "amplitude"),
                          ("uWaviness", "waviness"), ("uThickness", "thickness"),
                          ("uGlow", "glow"), ("uTaper", "taper"), ("uSpread", "spread"),
                          ("uHueShift", "hueShift"), ("uIntensity", "intensity"),
                          ("uOpacity", "opacity"), ("uScale", "scale"),
                          ("uSaturation", "saturation")):
            self._u(prog, name, float(p[key]))

    def _draw(self, prog):
        prog.bind(); self._vao.bind(); self._vbo.bind()
        prog.enableAttributeArray("position")
        prog.setAttributeBuffer("position", GL_FLOAT, 0, 2)
        self._f.glDrawArrays(GL_TRIANGLES, 0, 3)
        self._vao.release(); prog.release()

    def paintGL(self):
        if not self._ok:
            return
        f = self._f
        f.glViewport(0, 0, self._w, self._h)
        f.glEnable(GL_BLEND)
        f.glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA)

        if self.p["glass"] and self._fbo is not None:
            self._fbo.bind()
            f.glClearColor(0.0, 0.0, 0.0, 0.0)
            f.glClear(GL_COLOR_BUFFER_BIT)
            self._prog.bind(); self._set_main(self._prog); self._prog.release()
            self._draw(self._prog)
            self._fbo.release()
            f.glBindFramebuffer(GL_FRAMEBUFFER, self.defaultFramebufferObject())
            f.glClearColor(*self._bg)
            f.glClear(GL_COLOR_BUFFER_BIT)
            self._glass.bind()
            f.glActiveTexture(GL_TEXTURE0)
            f.glBindTexture(GL_TEXTURE_2D, self._fbo.texture())
            self._u(self._glass, "uScene", int(0))
            self._u(self._glass, "uResolution", float(self._w), float(self._h))
            self._u(self._glass, "uRadius", float(0.46 * float(self.p["glassSize"])))
            self._u(self._glass, "uRefraction", float(self.p["refraction"]))
            self._u(self._glass, "uDispersion", float(self.p["dispersion"]))
            self._glass.release()
            self._draw(self._glass)
        else:
            f.glClearColor(*self._bg)
            f.glClear(GL_COLOR_BUFFER_BIT)
            self._prog.bind(); self._set_main(self._prog); self._prog.release()
            self._draw(self._prog)
