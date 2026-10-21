"""A stand-in for Pythonista's `clipboard` module. Tests put the copied text in `text`."""

text = ''


def get():
    return text


def set(s):
    global text
    text = s
