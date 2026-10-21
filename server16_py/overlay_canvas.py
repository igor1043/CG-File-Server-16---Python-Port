"""Logical-coordinate drawing onto a high-resolution overlay texture."""
from PIL import ImageDraw

FOCUS_BLUE = '#0052cc'
FOCUSED_PRIMARY = '#123d86'


def fit_text(draw, value, font, max_width):
    """Fit by rendered width, including the ellipsis and proportional glyphs."""
    value = str(value)
    if draw.textlength(value, font=font) <= max_width:
        return value
    if draw.textlength('…', font=font) > max_width:
        return ''
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        if draw.textlength(value[:middle].rstrip() + '…', font=font) <= max_width:
            low = middle
        else:
            high = middle - 1
    return value[:low].rstrip() + '…'


def draw_focus_ring(draw, rect, radius=10):
    """Keep focus distinct from both a photograph and a blue action fill."""
    x1, y1, x2, y2 = rect
    draw.rounded_rectangle((x1-5, y1-5, x2+5, y2+5), radius+5, outline=FOCUS_BLUE, width=4)
    draw.rounded_rectangle((x1-1, y1-1, x2+1, y2+1), radius+1, outline='white', width=2)


class OverlayDraw:
    SCALE = 2

    def __init__(self, image):
        self.draw = ImageDraw.Draw(image)

    def _shape(self, method, xy, **kwargs):
        coords = [(x*self.SCALE, y*self.SCALE) for x, y in xy] if isinstance(xy[0], (tuple, list)) else tuple(v*self.SCALE for v in xy)
        for key in ('width', 'radius'):
            if key in kwargs:
                kwargs[key] *= self.SCALE
        return getattr(self.draw, method)(coords, **kwargs)

    def rounded_rectangle(self, xy, radius=0, **kwargs):
        return self._shape('rounded_rectangle', xy, radius=radius, **kwargs)

    def ellipse(self, xy, **kwargs):
        return self._shape('ellipse', xy, **kwargs)

    def line(self, xy, **kwargs):
        return self._shape('line', xy, **kwargs)

    def arc(self, xy, start, end, **kwargs):
        return self._shape('arc', xy, start=start, end=end, **kwargs)

    def text(self, xy, value, max_width=None, **kwargs):
        if max_width is not None:
            value = fit_text(self, value, kwargs.get('font'), max_width)
        return self.draw.text(tuple(v*self.SCALE for v in xy), value, **kwargs)

    def textlength(self, value, **kwargs):
        return self.draw.textlength(value, **kwargs)/self.SCALE
