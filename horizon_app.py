"""Event Horizon for Pythonista: run this file on your iPhone or iPad.

Calc     staffing for one interval, with the service-level cliff
What-if  AI containment and assist, pooling, moving agents, chat concurrency
Sites    every site's clock, hours and daylight-saving shifts; Paste setup link loads your sites

Everything runs on the device; no internet needed.
"""

import json
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import clipboard  # noqa: E402  (Pythonista)
import ui  # noqa: E402  (Pythonista)

from horizon import config, screens  # noqa: E402

STATE_PATH = os.path.join(HERE, '.state.json')

try:
    DARK = ui.get_ui_style() == 'dark'
except Exception:
    DARK = False

BG = '#101114' if DARK else '#ffffff'
TEXT = '#f2f2f4' if DARK else '#121214'
MUTED = '#9b9ba3' if DARK else '#66666d'
FIELD = '#1d1e23' if DARK else '#f1f1f5'
ACCENT = '#ff9f0a'
MISS = '#c4515a' if DARK else '#d9636c'
HIT = '#4f8fd6' if DARK else '#3f7fcc'
MONO = ('Menlo', 12)
LINE = 15
PAD = 16


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    try:
        with open(STATE_PATH, 'w') as f:
            json.dump(state, f)
    except Exception:
        pass


class Cliff(ui.View):
    """Service level at each staffing level around the recommendation."""

    def __init__(self):
        self.bars = []
        self.goal = 0.8
        self.background_color = FIELD
        self.corner_radius = 10

    def set_data(self, bars, goal):
        self.bars, self.goal = bars, goal
        self.set_needs_display()

    def draw(self):
        if not self.bars:
            return
        w, h = self.width, self.height
        top, bottom = 22, 22
        plot = h - top - bottom
        slot = (w - 16) / len(self.bars)
        for i, (agents, sl, chosen) in enumerate(self.bars):
            x = 8 + i * slot
            bar_h = max(1, plot * sl)
            ui.set_color(ACCENT if chosen else (HIT if sl >= self.goal else MISS))
            ui.Path.rounded_rect(x + slot * 0.18, top + plot - bar_h, slot * 0.64, bar_h, 3).fill()
            ui.draw_string('%d' % agents, rect=(x, h - bottom + 4, slot, 16), font=('<system>', 11),
                           color=TEXT if chosen else MUTED, alignment=ui.ALIGN_CENTER)
            ui.draw_string('%d%%' % round(100 * sl), rect=(x, max(0, top + plot - bar_h - 16), slot, 14),
                           font=('<system>', 10), color=MUTED, alignment=ui.ALIGN_CENTER)
        y = top + plot * (1 - self.goal)
        line = ui.Path()
        line.move_to(8, y)
        line.line_to(w - 8, y)
        line.line_width = 1
        line.set_line_dash([4, 3])
        ui.set_color(MUTED)
        line.stroke()


class Row(ui.View):
    """A label and a text field."""

    def __init__(self, key, label, value, hint, delegate):
        self.key = key
        self.label = ui.Label(text=label, font=('<system>', 15), text_color=MUTED)
        self.field = ui.TextField(text=value, placeholder=hint, font=('<system>', 16), text_color=TEXT,
                                  alignment=ui.ALIGN_RIGHT)
        self.field.keyboard_type = ui.KEYBOARD_DEFAULT if key.endswith('name') else ui.KEYBOARD_NUMBERS
        self.field.autocorrection_type = False
        self.field.autocapitalization_type = ui.AUTOCAPITALIZE_NONE
        self.field.clear_button_mode = 'while_editing'
        self.field.bordered = False
        self.field.background_color = FIELD
        self.field.corner_radius = 8
        self.field.delegate = delegate
        self.add_subview(self.label)
        self.add_subview(self.field)

    def layout(self):
        w, h = self.width, self.height
        self.label.frame = (0, 0, w * 0.52, h)
        self.field.frame = (w * 0.52, 3, w * 0.48, h - 6)


class ButtonRow(ui.View):
    """Buttons side by side."""

    def __init__(self, *buttons):
        self.buttons = buttons
        for b in buttons:
            self.add_subview(b)

    def layout(self):
        w = self.width / len(self.buttons)
        for i, b in enumerate(self.buttons):
            b.frame = (i * w, 0, w, self.height)


class Tab(ui.View):
    """A scrolling column of views."""

    def __init__(self):
        self.background_color = BG
        self.scroll = ui.ScrollView()
        self.scroll.background_color = BG
        self.add_subview(self.scroll)
        self.items = []

    def add(self, view, height):
        self.items.append((view, height))
        self.scroll.add_subview(view)
        return view

    def layout(self):
        self.scroll.frame = (0, 0, self.width, self.height)
        width = self.width - 2 * PAD
        y = 12
        for view, height in self.items:
            if view.hidden:
                continue
            h = height() if callable(height) else height
            view.frame = (PAD, y, width, h)
            y += h + 8
        self.scroll.content_size = (self.width, y + 320)   # room to scroll above the keyboard


def mono_label():
    return ui.Label(font=MONO, text_color=TEXT, number_of_lines=0)


def text_height(label):
    return (label.text or '').count('\n') * LINE + LINE + 8


class App(ui.View):
    def __init__(self):
        self.name = 'Event Horizon'
        self.background_color = BG
        self.state = load_state()
        try:
            self.cfg = config.load()
        except Exception as e:
            self.cfg = {'sites': [], 'goals': {}, '_path': '', '_error': str(e)}

        self.tabs_control = ui.SegmentedControl(segments=['Calc', 'What-if', 'Sites'])
        self.tabs_control.selected_index = min(max(int(self.state.get('tab', 0)), 0), 2)
        self.tabs_control.action = self.switch_tab
        self.add_subview(self.tabs_control)

        self.calc_tab = self.build_calc()
        self.whatif_tab = self.build_whatif()
        self.sites_tab = self.build_sites()
        self.tabs = [self.calc_tab, self.whatif_tab, self.sites_tab]
        for t in self.tabs:
            self.add_subview(t)
        self.switch_tab(None)

    # --- building -------------------------------------------------------

    def rows_for(self, tab, group, fields):
        saved = self.state.get(group, {})
        values = screens.defaults(fields, self.cfg)
        rows = []
        for key, label, _, hint in fields:
            row = Row(key, label, saved.get(key, values[key]), hint, self)
            row.group = group
            rows.append(tab.add(row, 40))
        return rows

    def build_calc(self):
        tab = Tab()
        self.headline = tab.add(ui.Label(font=('<system-bold>', 40), text_color=ACCENT), 48)
        self.detail = tab.add(ui.Label(font=('<system>', 13), text_color=MUTED, number_of_lines=0), 36)
        self.cliff = tab.add(Cliff(), 150)
        self.calc_rows = self.rows_for(tab, 'calc', screens.CALC_FIELDS)
        self.calc_report = tab.add(mono_label(), lambda: text_height(self.calc_report))
        return tab

    def build_whatif(self):
        tab = Tab()
        self.mode_control = tab.add(ui.SegmentedControl(segments=screens.WHATIF_MODES), 32)
        self.mode_control.selected_index = min(max(int(self.state.get('mode', 0)), 0),
                                               len(screens.WHATIF_MODES) - 1)
        self.mode_control.action = self.switch_mode
        self.mode_rows = {}
        for mode in screens.WHATIF_MODES:
            self.mode_rows[mode] = self.rows_for(tab, 'whatif-' + mode, screens.WHATIF_FIELDS[mode])
        self.whatif_report = tab.add(mono_label(), lambda: text_height(self.whatif_report))
        return tab

    def build_sites(self):
        tab = Tab()
        self.refresh_button = ui.Button(title='Refresh', font=('<system-bold>', 15), tint_color=ACCENT)
        self.refresh_button.action = lambda sender: self.update_sites()
        self.paste_button = ui.Button(title='Paste setup link', font=('<system-bold>', 15), tint_color=ACCENT)
        self.paste_button.action = lambda sender: self.paste_setup()
        tab.add(ButtonRow(self.refresh_button, self.paste_button), 32)
        self.sites_report = tab.add(mono_label(), lambda: text_height(self.sites_report))
        return tab

    # --- behaviour ------------------------------------------------------

    def layout(self):
        self.tabs_control.frame = (PAD, 8, self.width - 2 * PAD, 32)
        for t in self.tabs:
            t.frame = (0, 48, self.width, self.height - 48)

    def switch_tab(self, sender):
        index = self.tabs_control.selected_index
        for i, t in enumerate(self.tabs):
            t.hidden = i != index
        self.state['tab'] = index
        save_state(self.state)
        if index == 0:
            self.update_calc()
        elif index == 1:
            self.switch_mode(None)
        else:
            self.update_sites()

    def switch_mode(self, sender):
        mode = screens.WHATIF_MODES[self.mode_control.selected_index]
        for m, rows in self.mode_rows.items():
            for r in rows:
                r.hidden = m != mode
        self.state['mode'] = self.mode_control.selected_index
        save_state(self.state)
        self.update_whatif()

    def values(self, rows):
        return {r.key: r.field.text for r in rows}

    def remember(self, rows):
        if rows:
            self.state[rows[0].group] = self.values(rows)
            save_state(self.state)

    def update_calc(self):
        try:
            out = screens.calc(self.values(self.calc_rows))
            self.headline.text = out['headline']
            self.detail.text = out['detail']
            self.cliff.set_data(out['bars'], out['goal'])
            self.calc_report.text = out['report']
        except Exception as e:
            self.headline.text = '-'
            self.detail.text = 'Check the inputs: %s' % e
            self.cliff.set_data([], 0.8)
            self.calc_report.text = ''
        self.remember(self.calc_rows)
        self.calc_tab.layout()

    def update_whatif(self):
        mode = screens.WHATIF_MODES[self.mode_control.selected_index]
        rows = self.mode_rows[mode]
        try:
            self.whatif_report.text = screens.whatif(mode, self.values(rows))
        except Exception as e:
            self.whatif_report.text = 'Check the inputs:\n%s' % e
        self.remember(rows)
        self.whatif_tab.layout()

    def update_sites(self, message=None):
        try:
            text = screens.sites(self.cfg if self.cfg.get('_path') else None)
        except Exception as e:
            text = 'Could not read the sites config:\n%s' % e
        self.sites_report.text = message + '\n\n' + text if message else text
        self.sites_tab.layout()

    def paste_setup(self):
        # The same setup link (or setup code) the web app makes, from the clipboard.
        try:
            self.cfg = screens.use_setup(clipboard.get() or '')
            n = len(self.cfg['sites'])
            message = 'Loaded %d site%s from your setup link.' % (n, '' if n == 1 else 's')
        except Exception as e:
            message = 'That setup link could not be used:\n' + textwrap.fill(str(e), 36)
        self.update_sites(message)

    # TextField delegate: recalculate shortly after typing stops.
    def textfield_did_change(self, textfield):
        ui.cancel_delays()
        ui.delay(self.update_current, 0.35)

    def textfield_should_return(self, textfield):
        textfield.end_editing()
        return True

    def textfield_did_end_editing(self, textfield):
        self.update_current()

    def update_current(self):
        index = self.tabs_control.selected_index
        if index == 0:
            self.update_calc()
        elif index == 1:
            self.update_whatif()
        else:
            self.update_sites()


def main():
    app = App()
    app.present('fullscreen', hide_title_bar=False)
    return app


if __name__ == '__main__':
    main()
