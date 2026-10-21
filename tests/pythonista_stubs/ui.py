"""A strict stand-in for Pythonista's `ui` module, for smoke-testing horizon_app.py off the phone.

Only attributes and functions that exist in Pythonista's ui module are accepted on
the stand-in classes, so typos and misused APIs fail here instead of on the phone.
Drawing calls are recorded, not rendered.
"""

ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT, ALIGN_JUSTIFIED, ALIGN_NATURAL = 0, 1, 2, 3, 4
LB_WORD_WRAP, LB_CHAR_WRAP, LB_CLIP, LB_TRUNCATE_HEAD, LB_TRUNCATE_TAIL, LB_TRUNCATE_MIDDLE = range(6)
(KEYBOARD_DEFAULT, KEYBOARD_ASCII, KEYBOARD_NUMBERS, KEYBOARD_URL, KEYBOARD_NUMBER_PAD,
 KEYBOARD_PHONE_PAD, KEYBOARD_TWITTER, KEYBOARD_EMAIL, KEYBOARD_DECIMAL_PAD) = range(9)
AUTOCAPITALIZE_NONE, AUTOCAPITALIZE_WORDS, AUTOCAPITALIZE_SENTENCES, AUTOCAPITALIZE_ALL = range(4)

calls = []          # drawing calls, for tests to inspect
delayed = []        # functions passed to delay()
style = 'light'


def get_ui_style():
    return style


def get_screen_size():
    return (390.0, 844.0)


def set_color(color):
    calls.append(('set_color', color))


def fill_rect(x, y, w, h):
    calls.append(('fill_rect', x, y, w, h))


def draw_string(s, rect=(0, 0, 0, 0), font=('<system>', 12), color=None, alignment=ALIGN_LEFT,
                line_break_mode=LB_WORD_WRAP):
    assert isinstance(s, str)
    assert len(rect) == 4 and len(font) == 2
    calls.append(('draw_string', s))


def delay(func, seconds):
    assert callable(func)
    delayed.append(func)


def cancel_delays():
    del delayed[:]


def run_delayed():
    while delayed:
        delayed.pop(0)()


VIEW_ATTRS = {'alpha', 'background_color', 'border_color', 'border_width', 'bounds', 'center',
              'content_mode', 'corner_radius', 'flex', 'frame', 'height', 'hidden', 'left_button_items',
              'multitouch_enabled', 'name', 'right_button_items', 'tint_color', 'touch_enabled',
              'transform', 'width', 'x', 'y', 'update_interval'}


class View(object):
    _attrs = VIEW_ATTRS

    def __new__(cls, *args, **kwargs):
        self = object.__new__(cls)
        object.__setattr__(self, '_state', {'frame': (0.0, 0.0, 100.0, 100.0), 'hidden': False,
                                            'subviews': [], 'superview': None, 'presented': None,
                                            'needs_display': 0})
        return self

    def __init__(self, *args, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __setattr__(self, name, value):
        stand_in = type(self).__module__ == __name__
        if stand_in and not name.startswith('_') and name not in self._attrs:
            raise AttributeError('%s has no attribute %r in Pythonista' % (type(self).__name__, name))
        if name in ('frame', 'x', 'y', 'width', 'height', 'hidden'):
            self._set_geometry(name, value)
        else:
            object.__setattr__(self, name, value)

    def _set_geometry(self, name, value):
        x, y, w, h = self._state['frame']
        if name == 'frame':
            x, y, w, h = (float(v) for v in value)
        elif name == 'hidden':
            self._state['hidden'] = bool(value)
            return
        else:
            d = {'x': x, 'y': y, 'width': w, 'height': h}
            d[name] = float(value)
            x, y, w, h = d['x'], d['y'], d['width'], d['height']
        old = self._state['frame']
        self._state['frame'] = (x, y, w, h)
        if (old[2], old[3]) != (w, h):
            self.layout()

    frame = property(lambda self: self._state['frame'], lambda self, v: self._set_geometry('frame', v))
    x = property(lambda self: self._state['frame'][0])
    y = property(lambda self: self._state['frame'][1])
    width = property(lambda self: self._state['frame'][2])
    height = property(lambda self: self._state['frame'][3])
    hidden = property(lambda self: self._state['hidden'])
    bounds = property(lambda self: (0.0, 0.0) + self._state['frame'][2:])
    subviews = property(lambda self: tuple(self._state['subviews']))
    superview = property(lambda self: self._state['superview'])

    def add_subview(self, view):
        assert isinstance(view, View)
        self._state['subviews'].append(view)
        view._state['superview'] = self

    def remove_subview(self, view):
        self._state['subviews'].remove(view)

    def layout(self):
        pass

    def draw(self):
        pass

    def set_needs_display(self):
        self._state['needs_display'] += 1

    def size_to_fit(self):
        pass

    def bring_to_front(self):
        pass

    def send_to_back(self):
        pass

    def present(self, style='default', animated=True, popover_location=None, hide_title_bar=False,
                title_bar_color=None, title_color=None, orientations=None, hide_close_button=False):
        assert style in ('default', 'full_screen', 'fullscreen', 'sheet', 'popover', 'panel')
        self._state['presented'] = style
        w, h = get_screen_size()
        self.frame = (0, 0, w, h - 64)

    def close(self):
        self._state['presented'] = None


TEXT_ATTRS = {'alignment', 'font', 'text', 'text_color'}


class Label(View):
    _attrs = VIEW_ATTRS | TEXT_ATTRS | {'line_break_mode', 'number_of_lines', 'scales_font', 'min_font_scale'}

    def __init__(self, *args, **kwargs):
        object.__setattr__(self, 'text', '')
        View.__init__(self, *args, **kwargs)


class TextField(View):
    _attrs = VIEW_ATTRS | TEXT_ATTRS | {'action', 'autocapitalization_type', 'autocorrection_type', 'bordered',
                                        'clear_button_mode', 'delegate', 'enabled', 'keyboard_type',
                                        'placeholder', 'secure', 'spellchecking_type'}

    def __init__(self, *args, **kwargs):
        object.__setattr__(self, 'text', '')
        object.__setattr__(self, 'delegate', None)
        View.__init__(self, *args, **kwargs)

    def __setattr__(self, name, value):
        if name == 'clear_button_mode':
            assert value in ('never', 'always', 'while_editing', 'unless_editing')
        View.__setattr__(self, name, value)

    def begin_editing(self):
        pass

    def end_editing(self):
        if self.delegate is not None and hasattr(self.delegate, 'textfield_did_end_editing'):
            self.delegate.textfield_did_end_editing(self)

    def type(self, text):
        """Test helper: what the keyboard would do."""
        self.text = text
        if self.delegate is not None and hasattr(self.delegate, 'textfield_did_change'):
            self.delegate.textfield_did_change(self)


class Button(View):
    _attrs = VIEW_ATTRS | {'action', 'background_image', 'enabled', 'font', 'image', 'title'}

    def tap(self):
        """Test helper."""
        self.action(self)


class SegmentedControl(View):
    _attrs = VIEW_ATTRS | {'action', 'enabled', 'segments', 'selected_index'}

    def __init__(self, *args, **kwargs):
        object.__setattr__(self, 'selected_index', -1)
        object.__setattr__(self, 'action', None)
        View.__init__(self, *args, **kwargs)

    def __setattr__(self, name, value):
        if name == 'selected_index':
            assert isinstance(value, int)
        View.__setattr__(self, name, value)

    def pick(self, index):
        """Test helper: tap a segment."""
        self.selected_index = index
        if self.action:
            self.action(self)


class ScrollView(View):
    _attrs = VIEW_ATTRS | {'always_bounce_horizontal', 'always_bounce_vertical', 'bounces', 'content_inset',
                           'content_offset', 'content_size', 'delegate', 'directional_lock_enabled',
                           'indicator_style', 'paging_enabled', 'scroll_enabled', 'scroll_indicator_insets',
                           'shows_horizontal_scroll_indicator', 'shows_vertical_scroll_indicator'}

    def __setattr__(self, name, value):
        if name == 'content_size':
            assert len(value) == 2
        View.__setattr__(self, name, value)


class TextView(View):
    _attrs = VIEW_ATTRS | TEXT_ATTRS | {'autocapitalization_type', 'autocorrection_type', 'auto_content_inset',
                                        'delegate', 'editable', 'keyboard_type', 'selectable', 'selected_range',
                                        'spellchecking_type'}


class Path(object):
    def __init__(self):
        self.line_width = 1.0
        self.ops = []

    @classmethod
    def rect(cls, x, y, w, h):
        p = cls()
        p.ops.append(('rect', x, y, w, h))
        return p

    @classmethod
    def rounded_rect(cls, x, y, w, h, corner_radius):
        p = cls()
        p.ops.append(('rounded_rect', x, y, w, h, corner_radius))
        return p

    @classmethod
    def oval(cls, x, y, w, h):
        p = cls()
        p.ops.append(('oval', x, y, w, h))
        return p

    def move_to(self, x, y):
        self.ops.append(('move_to', x, y))

    def line_to(self, x, y):
        self.ops.append(('line_to', x, y))

    def close(self):
        self.ops.append(('close',))

    def set_line_dash(self, sequence, phase=0.0):
        assert all(v > 0 for v in sequence)

    def fill(self):
        calls.append(('fill', self.ops))

    def stroke(self):
        calls.append(('stroke', self.ops))
