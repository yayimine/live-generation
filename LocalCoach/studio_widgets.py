"""Resizable, selectable text and form controls used by Studio."""
import tkinter as tk
from tkinter import ttk


class CopyText(tk.Text):
    def __init__(self, parent, **options):
        super().__init__(parent, wrap="word", state="disabled", takefocus=True, **options)
        self.bind("<Command-c>", self.copy_selection)
        self.bind("<Command-a>", self.select_all)
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Copy selection", command=self.copy_selection)
        menu.add_command(label="Copy all", command=self.copy_all)
        self.bind("<Button-2>", lambda event: menu.tk_popup(event.x_root, event.y_root))
        self.bind("<Control-Button-1>", lambda event: menu.tk_popup(event.x_root, event.y_root))

    def replace(self, value):
        self.configure(state="normal")
        self.delete("1.0", "end")
        self.insert("1.0", value)
        self.configure(state="disabled")

    def copy_selection(self, _event=None):
        if self.tag_ranges("sel"):
            self.copy(self.get("sel.first", "sel.last"))
        return "break"

    def select_all(self, _event=None):
        self.tag_add("sel", "1.0", "end-1c")
        return "break"

    def copy_all(self):
        self.copy(self.get("1.0", "end-1c"))

    def copy(self, value):
        self.clipboard_clear()
        self.clipboard_append(value)


def text_panel(parent, *, copy_button=True, **options):
    panel = ttk.Frame(parent)
    text = CopyText(panel, **options)
    scroll = ttk.Scrollbar(panel, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    if copy_button:
        ttk.Button(panel, text="Copy all", command=text.copy_all).pack(side="bottom", anchor="e")
    scroll.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)
    return panel, text


def scroll_form(parent):
    canvas = tk.Canvas(parent, width=1, height=1, highlightthickness=0, borderwidth=0)
    scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    form = ttk.Frame(canvas, padding=8)
    item = canvas.create_window(0, 0, window=form, anchor="nw")
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
    form.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox(item)))

    def wheel(event):
        if event.delta:
            amount = max(1, abs(event.delta) // 120)
            canvas.yview_scroll(-amount if event.delta > 0 else amount, "units")
            return "break"

    def bind_children(widget):
        widget.bind("<MouseWheel>", wheel, add="+")
        for child in widget.winfo_children():
            bind_children(child)

    form.after_idle(lambda: bind_children(canvas))
    return form


def fit_window(window, width, height, min_width, min_height):
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    window.minsize(min(min_width, screen_width - 40), min(min_height, screen_height - 100))
    window.geometry(f"{min(width, screen_width - 40)}x{min(height, screen_height - 100)}")
