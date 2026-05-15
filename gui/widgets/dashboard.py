"""Dashboard, log, and blocking overlay widgets."""

from __future__ import annotations

import logging
import tkinter as tk

import customtkinter as ctk
from PIL import Image

from core.assets import get_asset_path
from dsno_processor.i18n import t
from gui.themes.appearance import FONT_FAMILY as _FONT_FAMILY


# ── Logging handler ──────────────────────────────────────────────────
class _DashboardLogHandler(logging.Handler):
    """Route log records to a CTkTextbox inside a ProgressDashboard."""

    def __init__(self, textbox: ctk.CTkTextbox) -> None:
        super().__init__()
        self.textbox = textbox

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)

        def _append() -> None:
            self.textbox.configure(state="normal")
            self.textbox.insert("end", msg + "\n")
            self.textbox.configure(state="disabled")
            self.textbox.see("end")

        try:
            self.textbox.after(0, _append)
        except Exception:
            pass



class ProgressDashboard(ctk.CTkFrame):
    """Modern visual progress dashboard replacing raw log output.

    Provides phase indicator, progress bar, stat badges,
    per-item status cards, and a collapsible raw log.
    """

    _SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    _CARD_BG = {
        "success": ("#d7f5dd", "#17301a"),
        "error":   ("#fdd", "#301717"),
        "skipped": ("#fff4d6", "#302a17"),
    }
    _CARD_ICON = {
        "success": "✅", "error": "❌", "skipped": "⏭", "pending": "⏳",
    }
    _BADGE_FG = {
        "success": ("#2e7d32", "#66bb6a"),
        "error":   ("#c62828", "#ef5350"),
        "skipped": ("#e65100", "#ffb74d"),
        "pending": ("#455a64", "#90a4ae"),
    }

    def __init__(self, master, cancel_command=None, enable_idle_hourglass=True, start_btn_text=None, start_btn_command=None, **kwargs) -> None:
        self.cancel_command = cancel_command
        self.enable_idle_hourglass = enable_idle_hourglass
        self.start_btn_text = start_btn_text
        self.start_btn_command = start_btn_command
        super().__init__(master, fg_color="transparent", **kwargs)
        self._total = 0
        self._done = 0
        self._success_count = 0
        self._error_count = 0
        self._skipped_count = 0
        self._running = False
        self._spinner_idx = 0
        self._spinner_job = None
        self._cancelled = False
        
        self._idle_idx = 0
        self._idle_job = None
        
        try:
            from PIL import Image
            self._empty_img = ctk.CTkImage(light_image=Image.new("RGBA", (1, 1), (0,0,0,0)), size=(1, 1))
            self._hourglass_imgs = [
                ctk.CTkImage(
                    light_image=Image.open(get_asset_path(f"assets/icons/hourglass/hourglass-{p}_light.png")),
                    dark_image=Image.open(get_asset_path(f"assets/icons/hourglass/hourglass-{p}_dark.png")),
                    size=(20, 20)
                ) for p in ["high", "medium", "low"]
            ]
        except Exception as e:
            import logging
            logging.error(f"Could not load hourglass images: {e}")
            self._hourglass_imgs = []
            self._empty_img = None

        self._build_ui()
        if self._hourglass_imgs and self.enable_idle_hourglass:
            self._tick_idle()

    # ── UI construction ──────────────────────────────────────────
    def _build_ui(self) -> None:
        # Phase indicator
        phase_frame = ctk.CTkFrame(self, corner_radius=10)
        phase_frame.pack(fill="x", pady=(0, 6))
        phase_inner = ctk.CTkFrame(phase_frame, fg_color="transparent")
        phase_inner.pack(fill="x", padx=12, pady=8)
        phase_inner.grid_columnconfigure(0, weight=1)

        # Multi-purpose phase area: can show a button (idle) or status info (running)
        self._phase_info_frame = ctk.CTkFrame(phase_inner, fg_color="transparent")
        self._phase_info_frame.grid(row=0, column=0, sticky="nsew")
        self._phase_info_frame.grid_columnconfigure(1, weight=1)

        self._spinner_label = ctk.CTkLabel(
            self._phase_info_frame, text="", width=30,
            font=ctk.CTkFont(size=14),
        )
        self._spinner_label.grid(row=0, column=0, sticky="w")

        self._phase_label = ctk.CTkLabel(
            self._phase_info_frame,
            text=t("dash.waiting"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=13, weight="bold"),
            text_color=("gray40", "gray60"),
            image=(self._hourglass_imgs[0] if (getattr(self, "_hourglass_imgs", []) and self.enable_idle_hourglass) else self._empty_img),
            compound="left",
            padx=8
        )
        self._phase_label.grid(row=0, column=1, sticky="nsew")

        self._symmetry_spacer = ctk.CTkLabel(self._phase_info_frame, text="", width=30)
        self._symmetry_spacer.grid(row=0, column=2, sticky="e")

        self.start_btn = None
        if self.start_btn_text:
            self.start_btn = ctk.CTkButton(
                phase_inner,
                text=self.start_btn_text,
                font=ctk.CTkFont(family=_FONT_FAMILY, size=14, weight="bold"),
                height=40,
                corner_radius=10,
                width=280,
                command=self.start_btn_command,
            )
            self.start_btn.grid(row=0, column=0, sticky="")
            self._phase_info_frame.grid_remove() # Hide labels while button is visible

        # Progress bar
        prog_frame = ctk.CTkFrame(self, fg_color="transparent")
        prog_frame.pack(fill="x", pady=(0, 6))
        self._progress_bar = ctk.CTkProgressBar(
            prog_frame, height=10, corner_radius=5,
            progress_color=("#1f6aa5", "#1f6aa5"),
        )
        self._progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self._progress_bar.set(0)

        if getattr(self, "cancel_command", None):
            try:
                from PIL import Image
                self.cancel_btn = ctk.CTkButton(
                    prog_frame,
                    image=ctk.CTkImage(
                        light_image=Image.open(get_asset_path("assets/icons/cancel_light.png")),
                        dark_image=Image.open(get_asset_path("assets/icons/cancel_dark.png"))
                    ),
                    text="",
                    height=24, width=24,
                    corner_radius=4, fg_color="transparent", hover_color="#b71c1c",
                    state="disabled",
                    command=self.cancel_command
                )
                self.cancel_btn.pack(side="right", padx=(8, 0))
            except Exception as e:
                import logging
                logging.error(f"Could not load cancel icons for progress board: {e}")

        self._progress_label = ctk.CTkLabel(
            prog_frame, text="0 / 0",
            font=ctk.CTkFont(family=_FONT_FAMILY, size=11), width=50,
        )
        self._progress_label.pack(side="right")

        # Stats badges
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", pady=(0, 6))
        self._stat_labels: dict[str, ctk.CTkLabel] = {}
        for key, icon, text in [
            ("success", "✅", t("dash.success")), ("error", "❌", t("dash.errors")),
            ("skipped", "⏭", t("dash.skipped")), ("pending", "⏳", t("dash.pending")),
        ]:
            badge = ctk.CTkFrame(stats_frame, corner_radius=8, fg_color=("gray88", "gray20"))
            badge.pack(side="left", expand=True, fill="x", padx=2)
            inner = ctk.CTkFrame(badge, fg_color="transparent")
            inner.pack(padx=8, pady=4)
            ctk.CTkLabel(inner, text=icon, width=16, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 3))
            lbl = ctk.CTkLabel(
                inner, text="0",
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12, weight="bold"),
                text_color=self._BADGE_FG[key],
            )
            lbl.pack(side="left", padx=(0, 3))
            ctk.CTkLabel(inner, text=text, font=ctk.CTkFont(family=_FONT_FAMILY, size=10), text_color=("gray50", "gray55")).pack(side="left")
            self._stat_labels[key] = lbl

        # Item cards
        self._cards_frame = ctk.CTkScrollableFrame(self, corner_radius=8, fg_color=("gray92", "gray14"))
        self._cards_frame.pack(fill="both", expand=True, pady=(0, 6))
        self._empty_label = ctk.CTkLabel(
            self._cards_frame, text=t("dash.no_items"),
            font=ctk.CTkFont(family=_FONT_FAMILY, size=12), text_color=("gray50", "gray50"),
        )
        self._empty_label.pack(pady=20)

    # ── Public API (thread-safe via .after) ───────────────────────
    def reset(self, total: int) -> None:
        def _do():
            self._total = total
            self._done = self._success_count = self._error_count = self._skipped_count = 0
            self._cancelled = False
            self._running = True
            
            # Hide start button and show progress info
            if self.start_btn:
                self.start_btn.grid_remove()
            self._phase_info_frame.grid()
            
            for w in self._cards_frame.winfo_children():
                w.destroy()
            if total == 0:
                self._empty_label = ctk.CTkLabel(
                    self._cards_frame, text=t("dash.no_items_found"),
                    font=ctk.CTkFont(family=_FONT_FAMILY, size=12), text_color=("gray50", "gray50"),
                )
                self._empty_label.pack(pady=20)
            self._progress_bar.set(0)
            self._progress_label.configure(text=f"0 / {total}")
            for k in self._stat_labels:
                self._stat_labels[k].configure(text="0")
            self._stat_labels["pending"].configure(text=str(total))
            self._phase_label.configure(text=t("dash.starting"), text_color=("#1565c0", "#64b5f6"), image=self._empty_img)
            self._start_spinner()
        self.after(0, _do)

    def reset_to_idle(self) -> None:
        """Fully reset the dashboard to its initial idle state."""
        def _do():
            self._running = False
            self._stop_spinner()
            self._total = 0
            self._done = 0
            
            # Show start button if it exists
            if self.start_btn:
                self.start_btn.grid()
                self._phase_info_frame.grid_remove()
            else:
                self._phase_info_frame.grid()
                self._phase_label.configure(
                    text=t("dash.waiting"), 
                    text_color=("gray40", "gray60"),
                    image=(self._hourglass_imgs[0] if (getattr(self, "_hourglass_imgs", []) and self.enable_idle_hourglass) else self._empty_img)
                )
                self._spinner_label.configure(text="")
            
            self._progress_bar.set(0)
            self._progress_label.configure(text="0 / 0")
            for k in self._stat_labels:
                self._stat_labels[k].configure(text="0")
                
            for w in self._cards_frame.winfo_children():
                w.destroy()
                
            self._empty_label = ctk.CTkLabel(
                self._cards_frame, text=t("dash.no_items"),
                font=ctk.CTkFont(family=_FONT_FAMILY, size=12), text_color=("gray50", "gray50"),
            )
            self._empty_label.pack(pady=20)
            
            if self._hourglass_imgs and self.enable_idle_hourglass:
                self._tick_idle()
        self.after(0, _do)

    def set_phase(self, text: str) -> None:
        self.after(0, lambda: self._phase_label.configure(text=text, text_color=("#1565c0", "#64b5f6")))

    def mark_success(self, name: str, detail: str = "") -> None:
        def _do():
            self._success_count += 1
            self._done += 1
            self._add_card(name, "success", detail or t("dash.processed"))
            self._refresh()
        self.after(0, _do)

    def mark_error(self, name: str, detail: str) -> None:
        def _do():
            self._error_count += 1
            self._done += 1
            self._add_card(name, "error", detail)
            self._refresh()
        self.after(0, _do)

    def mark_skipped(self, name: str, detail: str = "") -> None:
        def _do():
            self._skipped_count += 1
            self._done += 1
            self._add_card(name, "skipped", detail or t("dash.skipped"))
            self._refresh()
        self.after(0, _do)

    def finish(self) -> None:
        def _do():
            self._running = False
            self._stop_spinner()
            
            # Keep the phase info visible at the end (don't show start button yet)
            self._phase_label.configure(image=self._empty_img)
            if self._cancelled:
                self._phase_label.configure(text=t("dash.cancelled"), text_color=("#c62828", "#ef5350"))
                self._spinner_label.configure(text="⚠️")
            elif self._error_count > 0:
                self._phase_label.configure(text=t("dash.completed_errors", count=self._error_count), text_color=("#c62828", "#ef5350"))
                self._spinner_label.configure(text="⚠️")
            else:
                self._phase_label.configure(text=t("dash.completed_success"), text_color=("#2e7d32", "#66bb6a"))
                self._spinner_label.configure(text="✅")
            # Keep progress consistent with success/total semantics
            self._refresh()
        self.after(0, _do)

    def _tick_idle(self) -> None:
        if self._running:
            return
        if getattr(self, "_hourglass_imgs", []) and self._phase_label.cget("text") == t("dash.waiting"):
            img = self._hourglass_imgs[self._idle_idx % len(self._hourglass_imgs)]
            self._phase_label.configure(image=img)
            self._idle_idx += 1
            self._idle_job = self.after(200, self._tick_idle)
        else:
            self._idle_job = self.after(200, self._tick_idle)

    # ── Internal ──────────────────────────────────────────────────
    def _add_card(self, name: str, status: str, detail: str = "") -> None:
        try:
            if hasattr(self, "_empty_label") and self._empty_label.winfo_exists():
                self._empty_label.destroy()
        except Exception:
            pass
        bg = self._CARD_BG.get(status, ("gray90", "gray17"))
        card = ctk.CTkFrame(self._cards_frame, fg_color=bg, corner_radius=6, height=30)
        card.pack(fill="x", pady=1)
        card.pack_propagate(False)
        ctk.CTkLabel(card, text=self._CARD_ICON.get(status, "⏳"), width=22, font=ctk.CTkFont(size=12)).pack(side="left", padx=(8, 4))
        ctk.CTkLabel(card, text=name, anchor="w", font=ctk.CTkFont(family=_FONT_FAMILY, size=11, weight="bold")).pack(side="left", padx=(0, 8))
        if detail:
            ctk.CTkLabel(card, text=detail, anchor="e", font=ctk.CTkFont(family=_FONT_FAMILY, size=10), text_color=("gray45", "gray55")).pack(side="right", padx=(4, 8), fill="x", expand=True)
        self.after(10, lambda: self._cards_frame._parent_canvas.yview_moveto(1.0))

    def _refresh(self) -> None:
        if self._total > 0:
            # Progress bar should represent successful items, not total attempts.
            # Failures/skips are still tracked in stats and cards.
            pct = self._success_count / self._total
            self._progress_bar.set(pct)
            self._progress_label.configure(text=f"{self._success_count} / {self._total}  ({int(pct * 100)}%)")
        pending = max(0, self._total - self._done)
        self._stat_labels["success"].configure(text=str(self._success_count))
        self._stat_labels["error"].configure(text=str(self._error_count))
        self._stat_labels["skipped"].configure(text=str(self._skipped_count))
        self._stat_labels["pending"].configure(text=str(pending))

    def _start_spinner(self) -> None:
        self._spinner_idx = 0
        self._tick_spinner()

    def _stop_spinner(self) -> None:
        if self._spinner_job:
            self.after_cancel(self._spinner_job)
            self._spinner_job = None

    def _tick_spinner(self) -> None:
        if not self._running:
            return
        self._spinner_label.configure(text=self._SPINNER[self._spinner_idx % len(self._SPINNER)])
        self._spinner_idx += 1
        self._spinner_job = self.after(100, self._tick_spinner)


class BlockingOverlay(ctk.CTkFrame):
    """Full-screen overlay with blurred background to block UI during loading."""

    def __init__(self, master, hourglass_imgs, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0, **kwargs)
        self._hourglass_imgs = [
            ctk.CTkImage(
                light_image=img._light_image,
                dark_image=img._dark_image,
                size=(64, 64)
            ) for img in hourglass_imgs
        ] if hourglass_imgs else []
        self._idx = 0
        self._job = None
        self._bg_photo = None
        self._icon_photos = [] # Store PhotoImages for canvas use

        # Use a Canvas for true transparency over the background image
        self._canvas = tk.Canvas(self, bd=0, highlightthickness=0, bg="black")
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)

        self._bg_id = None
        self._icon_id = None
        self._text_id = None

    def capture_blur(self) -> None:
        """Take a screenshot, blur it, and set as canvas background."""
        try:
            import pyautogui
            from PIL import ImageFilter, ImageTk, Image as PilImage

            master = self.master
            master.update_idletasks()

            x = master.winfo_rootx()
            y = master.winfo_rooty()
            w = master.winfo_width()
            h = master.winfo_height()

            if w < 2 or h < 2:
                return

            screenshot = pyautogui.screenshot(region=(x, y, w, h))
            blurred = screenshot.filter(ImageFilter.GaussianBlur(radius=14))
            dim = PilImage.new("RGBA", blurred.size, (0, 0, 0, 160)) # slightly darker
            blurred = blurred.convert("RGBA")
            final_bg = PilImage.alpha_composite(blurred, dim).convert("RGB")

            self._bg_photo = ImageTk.PhotoImage(final_bg)
            
            # Clear existing canvas items
            self._canvas.delete("all")
            
            # Draw background
            self._bg_id = self._canvas.create_image(0, 0, image=self._bg_photo, anchor="nw")
            
            # Prepare icon PhotoImages if not done (Canvas needs PhotoImage, not CTkImage)
            if not self._icon_photos and self._hourglass_imgs:
                mode = ctk.get_appearance_mode().lower()
                for img in self._hourglass_imgs:
                    pil_img = img._dark_image if mode == "dark" else img._light_image
                    pil_img = pil_img.resize((64, 64), PilImage.Resampling.LANCZOS)
                    self._icon_photos.append(ImageTk.PhotoImage(pil_img))

            cx, cy = w // 2, h // 2
            
            # Draw Icon
            if self._icon_photos:
                self._icon_id = self._canvas.create_image(cx, cy - 30, image=self._icon_photos[0])
            
            # Draw Text
            self._text_id = self._canvas.create_text(
                cx, cy + 40,
                text=t("msg.cancelling", default="Cancelling..."),
                fill="white",
                font=(_FONT_FAMILY, 13, "normal"),
                justify="center"
            )

        except Exception as e:
            logging.warning(f"BlockingOverlay: canvas setup failed ({e})")
            self._canvas.configure(bg="#1a1a1a")

    def start_animation(self) -> None:
        if not self._icon_photos or self._icon_id is None:
            return
        self._idx = (self._idx + 1) % len(self._icon_photos)
        self._canvas.itemconfig(self._icon_id, image=self._icon_photos[self._idx])
        self._job = self.after(250, self.start_animation)

    def stop_animation(self) -> None:
        if self._job:
            self.after_cancel(self._job)
            self._job = None

class LogWindow(ctk.CTkToplevel):
    def __init__(self, master) -> None:
        super().__init__(master)
        self.title("Application Log")
        self.geometry("600x400")

        self.textbox = ctk.CTkTextbox(
            self, state="disabled", wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8
        )
        self.textbox.pack(fill="both", expand=True, padx=4, pady=4)
        
        self.protocol("WM_DELETE_WINDOW", self.hide)
        self.withdraw()
    
    def hide(self) -> None:
        self.withdraw()
        
    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.focus_force()
        self.after(50, lambda: self.attributes("-topmost", False))

