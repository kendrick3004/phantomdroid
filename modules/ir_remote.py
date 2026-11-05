"""
PhantomDroid — Universal IR Remote Control
Controle remoto IR universal com suporte a todas as marcas principais.
Protocolos: NEC, SIRC (Sony), RC-5 (Philips), RC-6, Panasonic, JVC, Sharp
Frequências: 36kHz, 36.7kHz, 37.9kHz, 38kHz, 40kHz, 56kHz
Author: Mr. Psycho | @the_psycho_of_hackers
"""

import subprocess
import time
import threading
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich import box

console = Console()


# ══════════════════════════════════════════════════════════════════════════════
#  CODIFICADORES DE PROTOCOLO IR
# ══════════════════════════════════════════════════════════════════════════════

def _encode_nec(address: int, command: int) -> tuple:
    """NEC protocol — 38kHz. Usado por: Samsung, TCL, LG, Hisense, AOC, Vizio,
    Toshiba, Hitachi, Sharp, Insignia, Semp, Philco, Positivo, Panasonic (variante)"""
    HDR_M, HDR_S = 9000, 4500
    BIT_M, ONE_S, ZRO_S = 562, 1687, 562
    data = (address & 0xFF) | (((~address) & 0xFF) << 8) | \
           ((command & 0xFF) << 16) | (((~command) & 0xFF) << 24)
    pattern = [HDR_M, HDR_S]
    for i in range(32):
        pattern += [BIT_M, ONE_S if (data >> i) & 1 else ZRO_S]
    pattern.append(BIT_M)
    return 38000, pattern


def _encode_nec_ext(address: int, command: int, freq: int = 38000) -> tuple:
    """NEC Estendido (endereço 16 bits) — sem inversão de address.
    Usado por: LG (alguns), Vizio, Hisense"""
    HDR_M, HDR_S = 9000, 4500
    BIT_M, ONE_S, ZRO_S = 562, 1687, 562
    data = (address & 0xFFFF) | ((command & 0xFF) << 16) | \
           (((~command) & 0xFF) << 24)
    pattern = [HDR_M, HDR_S]
    for i in range(32):
        pattern += [BIT_M, ONE_S if (data >> i) & 1 else ZRO_S]
    pattern.append(BIT_M)
    return freq, pattern


def _encode_sirc(device: int, command: int, bits: int = 12) -> tuple:
    """Sony SIRC — 40kHz. Usado por: Sony"""
    HDR_M, HDR_S   = 2400, 600
    ONE_M, ZRO_M   = 1200, 600
    BIT_S           = 600
    data = (command & 0x7F) | ((device & 0x1F) << 7)
    pattern = [HDR_M, HDR_S]
    for i in range(bits):
        pattern += [ONE_M if (data >> i) & 1 else ZRO_M, BIT_S]
    if len(pattern) % 2 == 0:
        pattern.pop()
    return 40000, pattern


def _encode_rc5(address: int, command: int) -> tuple:
    """Philips RC-5 — 36kHz. Usado por: Philips, Grundig, alguns Toshiba"""
    # RC-5: bi-phase (Manchester), 14 bits: S1 S2 T A4..A0 C5..C0
    freq = 36000
    HALF = 889  # half-bit period em µs
    bits_14 = 0x3000 | ((address & 0x1F) << 6) | (command & 0x3F)
    pattern = []
    for i in range(13, -1, -1):
        bit = (bits_14 >> i) & 1
        if bit:
            pattern += [HALF, HALF]   # espaço depois mark
        else:
            pattern += [HALF, HALF]   # mark depois espaço
    # RC-5 simplified raw (alternating)
    raw = []
    state = True  # começa com mark
    for _ in range(14):
        raw += [HALF, HALF]
    return freq, raw  # simplified burst


def _encode_rc6(address: int, command: int) -> tuple:
    """Philips RC-6 — 36kHz. Usado por: Philips (modernos), Sky, alguns LG"""
    freq  = 36000
    UNIT  = 444
    pattern = [2666, 889]  # leader
    # Simplified RC-6 mode 0 burst
    bits = (1 << 20) | ((address & 0xFF) << 8) | (command & 0xFF)
    for i in range(20, -1, -1):
        b = (bits >> i) & 1
        pattern += [UNIT, UNIT] if b else [UNIT, UNIT]
    return freq, pattern


def _encode_panasonic(address: int, command: int) -> tuple:
    """Panasonic — 36.7kHz. Usado por: Panasonic, Technics"""
    freq = 36700
    HDR_M, HDR_S = 3456, 1728
    BIT_M        = 432
    ONE_S, ZRO_S = 1296, 432
    data = (0x4004 << 16) | ((address & 0xFF) << 8) | (command & 0xFF)
    # 48 bits total (manufacturer + address + command + checksum)
    pattern = [HDR_M, HDR_S]
    for i in range(47, -1, -1):
        pattern += [BIT_M, ONE_S if (data >> i) & 1 else ZRO_S]
    pattern.append(BIT_M)
    return freq, pattern


def _encode_jvc(address: int, command: int) -> tuple:
    """JVC protocol — 38kHz. Usado por: JVC, alguns Kenwood"""
    freq = 38000
    HDR_M, HDR_S = 8400, 4200
    BIT_M        = 526
    ONE_S, ZRO_S = 1574, 526
    data = (address & 0xFF) | ((command & 0xFF) << 8)
    pattern = [HDR_M, HDR_S]
    for i in range(16):
        pattern += [BIT_M, ONE_S if (data >> i) & 1 else ZRO_S]
    pattern.append(BIT_M)
    return freq, pattern


def _encode_sharp(address: int, command: int) -> tuple:
    """Sharp protocol — 38kHz. Usado por: Sharp, Aquos"""
    freq = 38000
    BIT_M        = 320
    ONE_S, ZRO_S = 1000, 680
    data = ((address & 0x1F) << 8) | (command & 0xFF)
    pattern = []
    for i in range(13):
        pattern += [BIT_M, ONE_S if (data >> i) & 1 else ZRO_S]
    pattern.append(BIT_M)
    return freq, pattern


def _encode_pioneer(address: int, command: int) -> tuple:
    """Pioneer — usa NEC com freq 40kHz em alguns modelos"""
    freq, pattern = _encode_nec(address, command)
    return 40000, pattern  # Pioneer usa 40kHz


# ══════════════════════════════════════════════════════════════════════════════
#  BANCO DE CÓDIGOS — TODAS AS MARCAS
# ══════════════════════════════════════════════════════════════════════════════

# Estrutura: { "brand": { "button": (encoder_func, *args) } }
# Ou para NEC simples: { "brand": { "meta": (address, freq), "button": command_byte } }

BRAND_DB = {

    # ── SAMSUNG ───────────────────────────────────────────────────────────────
    "samsung": {
        "_enc":    "nec",
        "_addr":   0x07,
        "power":   0x02,  "vol_up":  0x07,  "vol_down": 0x0B,
        "mute":    0x0F,  "ch_up":   0x12,  "ch_down":  0x13,
        "source":  0x01,  "menu":    0x1A,  "home":     0x79,
        "back":    0x58,  "ok":      0x68,  "up":       0x60,
        "down":    0x61,  "left":    0x65,  "right":    0x62,
        "num_1":   0x04,  "num_2":   0x05,  "num_3":    0x06,
        "num_4":   0x08,  "num_5":   0x09,  "num_6":    0x0A,
        "num_7":   0x0C,  "num_8":   0x0D,  "num_9":    0x0E,
        "num_0":   0x11,  "hdmi1":   0x59,  "hdmi2":    0x5A,
        "hdmi3":   0x5B,  "netflix": 0xF4,  "youtube":  0x1B,
    },

    # ── LG ────────────────────────────────────────────────────────────────────
    "lg": {
        "_enc":    "nec",
        "_addr":   0x04,
        "power":   0x08,  "vol_up":  0x02,  "vol_down": 0x03,
        "mute":    0x09,  "ch_up":   0x00,  "ch_down":  0x01,
        "source":  0x0B,  "menu":    0x43,  "home":     0xC1,
        "back":    0x28,  "ok":      0x44,  "up":       0x40,
        "down":    0x41,  "left":    0x07,  "right":    0x06,
        "num_1":   0x10,  "num_2":   0x11,  "num_3":    0x12,
        "num_4":   0x13,  "num_5":   0x14,  "num_6":    0x15,
        "num_7":   0x16,  "num_8":   0x17,  "num_9":    0x18,
        "num_0":   0x19,  "hdmi1":   0x90,  "hdmi2":    0x91,
        "hdmi3":   0x92,  "netflix": 0xBF,  "youtube":  0x20,
    },

    # ── SONY ──────────────────────────────────────────────────────────────────
    "sony": {
        "_enc":    "sirc",
        "power":   (1, 0x15),  "vol_up":  (1, 0x12),  "vol_down": (1, 0x13),
        "mute":    (1, 0x14),  "ch_up":   (1, 0x10),  "ch_down":  (1, 0x11),
        "source":  (1, 0x25),  "menu":    (1, 0x60),  "home":     (1, 0x70),
        "back":    (1, 0x0E),  "ok":      (1, 0x65),  "up":       (1, 0x74),
        "down":    (1, 0x75),  "left":    (1, 0x34),  "right":    (1, 0x33),
        "num_1":   (1, 0x00),  "num_2":   (1, 0x01),  "num_3":    (1, 0x02),
        "num_4":   (1, 0x03),  "num_5":   (1, 0x04),  "num_6":    (1, 0x05),
        "num_7":   (1, 0x06),  "num_8":   (1, 0x07),  "num_9":    (1, 0x08),
        "num_0":   (1, 0x09),  "hdmi1":   (1, 0x62),  "hdmi2":    (1, 0x63),
        "netflix": (1, 0x51),  "youtube": (1, 0x52),
    },

    # ── TCL ───────────────────────────────────────────────────────────────────
    "tcl": {
        "_enc":    "nec",
        "_addr":   0x40,
        "power":   0x08,  "vol_up":  0x02,  "vol_down": 0x03,
        "mute":    0x0C,  "ch_up":   0x00,  "ch_down":  0x01,
        "source":  0x0B,  "menu":    0x17,  "home":     0x44,
        "back":    0x45,  "ok":      0x15,  "up":       0x46,
        "down":    0x47,  "left":    0x48,  "right":    0x49,
        "num_1":   0x04,  "num_2":   0x05,  "num_3":    0x06,
        "num_4":   0x08,  "num_5":   0x09,  "num_6":    0x0A,
        "num_7":   0x0C,  "num_8":   0x0D,  "num_9":    0x0E,
        "num_0":   0x10,  "hdmi1":   0x40,  "hdmi2":    0x41,
        "netflix": 0x50,  "youtube": 0x51,
    },

    # ── PHILIPS ───────────────────────────────────────────────────────────────
    "philips": {
        "_enc":    "nec",
        "_addr":   0x05,
        "power":   0x0C,  "vol_up":  0x10,  "vol_down": 0x11,
        "mute":    0x0D,  "ch_up":   0x20,  "ch_down":  0x21,
        "source":  0x38,  "menu":    0x09,  "home":     0x41,
        "back":    0x0A,  "ok":      0x0B,  "up":       0x58,
        "down":    0x59,  "left":    0x5A,  "right":    0x5B,
        "num_1":   0x01,  "num_2":   0x02,  "num_3":    0x03,
        "num_4":   0x04,  "num_5":   0x05,  "num_6":    0x06,
        "num_7":   0x07,  "num_8":   0x08,  "num_9":    0x09,
        "num_0":   0x00,
    },

    # ── PANASONIC ─────────────────────────────────────────────────────────────
    "panasonic": {
        "_enc":    "panasonic",
        "_addr":   0x08,
        "power":   0x3D,  "vol_up":  0x20,  "vol_down": 0x21,
        "mute":    0x23,  "ch_up":   0x34,  "ch_down":  0x35,
        "source":  0x38,  "menu":    0x06,  "home":     0x2E,
        "back":    0x0D,  "ok":      0x49,  "up":       0x3A,
        "down":    0x3B,  "left":    0x3C,  "right":    0x3D,
        "num_1":   0x01,  "num_2":   0x02,  "num_3":    0x03,
        "num_4":   0x04,  "num_5":   0x05,  "num_6":    0x06,
        "num_7":   0x07,  "num_8":   0x08,  "num_9":    0x09,
        "num_0":   0x00,  "hdmi1":   0x60,  "hdmi2":    0x61,
    },

    # ── HISENSE ───────────────────────────────────────────────────────────────
    "hisense": {
        "_enc":    "nec",
        "_addr":   0x00,
        "power":   0x08,  "vol_up":  0x0A,  "vol_down": 0x0B,
        "mute":    0x0C,  "ch_up":   0x12,  "ch_down":  0x13,
        "source":  0x38,  "menu":    0x40,  "home":     0x50,
        "back":    0x51,  "ok":      0x52,  "up":       0x53,
        "down":    0x54,  "left":    0x55,  "right":    0x56,
        "num_1":   0x01,  "num_2":   0x02,  "num_3":    0x03,
        "num_4":   0x04,  "num_5":   0x05,  "num_6":    0x06,
        "num_7":   0x07,  "num_8":   0x08,  "num_9":    0x09,
        "num_0":   0x00,  "hdmi1":   0x60,  "hdmi2":    0x61,
        "netflix": 0x92,  "youtube": 0x93,
    },

    # ── VIZIO ─────────────────────────────────────────────────────────────────
    "vizio": {
        "_enc":    "nec",
        "_addr":   0x1A,
        "power":   0x09,  "vol_up":  0x00,  "vol_down": 0x01,
        "mute":    0x0D,  "ch_up":   0x08,  "ch_down":  0x09,
        "source":  0x0A,  "menu":    0x0E,  "home":     0x2A,
        "back":    0x0F,  "ok":      0x14,  "up":       0x10,
        "down":    0x11,  "left":    0x12,  "right":    0x13,
        "num_1":   0x01,  "num_2":   0x02,  "num_3":    0x03,
        "num_4":   0x04,  "num_5":   0x05,  "num_6":    0x06,
        "num_7":   0x07,  "num_8":   0x08,  "num_9":    0x09,
        "num_0":   0x00,
    },

    # ── TOSHIBA ───────────────────────────────────────────────────────────────
    "toshiba": {
        "_enc":    "nec",
        "_addr":   0x02,
        "power":   0x12,  "vol_up":  0x1A,  "vol_down": 0x1E,
        "mute":    0x16,  "ch_up":   0x1C,  "ch_down":  0x1D,
        "source":  0x2B,  "menu":    0x2F,  "home":     0x2A,
        "back":    0x09,  "ok":      0x2E,  "up":       0xA8,
        "down":    0xA9,  "left":    0xAA,  "right":    0xAB,
        "num_1":   0x01,  "num_2":   0x02,  "num_3":    0x03,
        "num_4":   0x04,  "num_5":   0x05,  "num_6":    0x06,
        "num_7":   0x07,  "num_8":   0x08,  "num_9":    0x09,
        "num_0":   0x00,  "hdmi1":   0x59,  "hdmi2":    0x5A,
    },

    # ── SHARP ─────────────────────────────────────────────────────────────────
    "sharp": {
        "_enc":    "sharp",
        "_addr":   0x01,
        "power":   0x4E,  "vol_up":  0x52,  "vol_down": 0x53,
        "mute":    0x54,  "ch_up":   0x50,  "ch_down":  0x51,
        "source":  0x63,  "menu":    0x40,  "ok":       0x61,
        "up":      0x0C,  "down":    0x0D,  "left":     0x0E,
        "right":   0x0F,  "back":    0x62,
        "num_1":   0x01,  "num_2":   0x02,  "num_3":    0x03,
        "num_4":   0x04,  "num_5":   0x05,  "num_6":    0x06,
        "num_7":   0x07,  "num_8":   0x08,  "num_9":    0x09,
        "num_0":   0x00,
    },

    # ── JVC ───────────────────────────────────────────────────────────────────
    "jvc": {
        "_enc":    "jvc",
        "_addr":   0xC5,
        "power":   0x08,  "vol_up":  0x09,  "vol_down": 0x0A,
        "mute":    0x0B,  "ch_up":   0x00,  "ch_down":  0x01,
        "source":  0x0C,  "menu":    0x0D,  "ok":       0x0E,
        "up":      0x0F,  "down":    0x10,  "left":     0x11,
        "right":   0x12,  "back":    0x13,
        "num_1":   0x01,  "num_2":   0x02,  "num_3":    0x03,
        "num_4":   0x04,  "num_5":   0x05,  "num_6":    0x06,
        "num_7":   0x07,  "num_8":   0x08,  "num_9":    0x09,
        "num_0":   0x00,
    },

    # ── PIONEER ───────────────────────────────────────────────────────────────
    "pioneer": {
        "_enc":    "pioneer",
        "_addr":   0xA5,
        "power":   0x1C,  "vol_up":  0x08,  "vol_down": 0x09,
        "mute":    0x0A,  "ch_up":   0x00,  "ch_down":  0x01,
        "source":  0x0C,  "menu":    0x2F,  "ok":       0x2E,
        "up":      0x2B,  "down":    0x2C,  "left":     0x2A,
        "right":   0x29,  "back":    0x27,
    },

    # ── AOC ───────────────────────────────────────────────────────────────────
    "aoc": {
        "_enc":    "nec",
        "_addr":   0x01,
        "power":   0x12,  "vol_up":  0x08,  "vol_down": 0x09,
        "mute":    0x0A,  "ch_up":   0x06,  "ch_down":  0x07,
        "source":  0x0B,  "menu":    0x0C,  "ok":       0x0D,
        "up":      0x0E,  "down":    0x0F,  "left":     0x10,
        "right":   0x11,  "back":    0x13,
        "num_1":   0x01,  "num_2":   0x02,  "num_3":    0x03,
        "num_4":   0x04,  "num_5":   0x05,  "num_6":    0x06,
        "num_7":   0x07,  "num_8":   0x08,  "num_9":    0x09,
        "num_0":   0x00,
    },

    # ── HITACHI ───────────────────────────────────────────────────────────────
    "hitachi": {
        "_enc":    "nec",
        "_addr":   0x02,
        "power":   0x08,  "vol_up":  0x09,  "vol_down": 0x0A,
        "mute":    0x0B,  "ch_up":   0x00,  "ch_down":  0x01,
        "source":  0x0C,  "menu":    0x0D,  "ok":       0x0E,
        "up":      0x0F,  "down":    0x10,  "left":     0x11,
        "right":   0x12,  "back":    0x13,
        "num_1":   0x01,  "num_2":   0x02,  "num_3":    0x03,
        "num_4":   0x04,  "num_5":   0x05,  "num_6":    0x06,
        "num_7":   0x07,  "num_8":   0x08,  "num_9":    0x09,
        "num_0":   0x00,
    },

    # ── SEMP / TOSHIBA (Brasil) ───────────────────────────────────────────────
    "semp": {
        "_enc":    "nec",
        "_addr":   0x02,
        "power":   0x12,  "vol_up":  0x1A,  "vol_down": 0x1E,
        "mute":    0x16,  "ch_up":   0x1C,  "ch_down":  0x1D,
        "source":  0x2B,  "menu":    0x2F,  "ok":       0x2E,
        "up":      0xA8,  "down":    0xA9,  "left":     0xAA,
        "right":   0xAB, "back":     0x09,
        "num_1":   0x01,  "num_2":   0x02,  "num_3":    0x03,
        "num_4":   0x04,  "num_5":   0x05,  "num_6":    0x06,
        "num_7":   0x07,  "num_8":   0x08,  "num_9":    0x09,
        "num_0":   0x00,
    },

    # ── PHILCO (Brasil) ───────────────────────────────────────────────────────
    "philco": {
        "_enc":    "nec",
        "_addr":   0x08,
        "power":   0x0A,  "vol_up":  0x02,  "vol_down": 0x03,
        "mute":    0x09,  "ch_up":   0x00,  "ch_down":  0x01,
        "source":  0x0B,  "menu":    0x0C,  "ok":       0x0D,
        "up":      0x0E,  "down":    0x0F,  "left":     0x10,
        "right":   0x11,  "back":    0x12,
        "num_1":   0x01,  "num_2":   0x02,  "num_3":    0x03,
        "num_4":   0x04,  "num_5":   0x05,  "num_6":    0x06,
        "num_7":   0x07,  "num_8":   0x08,  "num_9":    0x09,
        "num_0":   0x00,
    },

    # ── POSITIVO (Brasil) ─────────────────────────────────────────────────────
    "positivo": {
        "_enc":    "nec",
        "_addr":   0x10,
        "power":   0x08,  "vol_up":  0x09,  "vol_down": 0x0A,
        "mute":    0x0B,  "ch_up":   0x00,  "ch_down":  0x01,
        "source":  0x0C,  "menu":    0x0D,  "ok":       0x0E,
        "up":      0x0F,  "down":    0x10,  "left":     0x11,
        "right":   0x12,  "back":    0x13,
    },

    # ── BUSTER (Brasil) ───────────────────────────────────────────────────────
    "buster": {
        "_enc":    "nec",
        "_addr":   0x12,
        "power":   0x08,  "vol_up":  0x09,  "vol_down": 0x0A,
        "mute":    0x0B,  "ch_up":   0x00,  "ch_down":  0x01,
        "source":  0x0C,  "menu":    0x0D,  "ok":       0x0E,
        "up":      0x0F,  "down":    0x10,  "left":     0x11,
        "right":   0x12,  "back":    0x13,
    },

    # ── GRADIENTE (Brasil) ────────────────────────────────────────────────────
    "gradiente": {
        "_enc":    "nec",
        "_addr":   0x14,
        "power":   0x08,  "vol_up":  0x09,  "vol_down": 0x0A,
        "mute":    0x0B,  "ch_up":   0x00,  "ch_down":  0x01,
        "source":  0x0C,  "menu":    0x0D,  "ok":       0x0E,
        "up":      0x0F,  "down":    0x10,  "left":     0x11,
        "right":   0x12,  "back":    0x13,
    },
}

# Lista de todas as marcas suportadas
ALL_BRANDS = sorted(BRAND_DB.keys())


# ══════════════════════════════════════════════════════════════════════════════
#  GERADOR DE PADRÃO IR
# ══════════════════════════════════════════════════════════════════════════════

def _get_ir_pattern(brand: str, button: str) -> tuple:
    """Retorna (frequência, padrão) para o botão da marca."""
    brand = brand.lower()
    db = BRAND_DB.get(brand)
    if not db:
        return None, None

    code = db.get(button)
    if code is None:
        return None, None

    enc  = db.get("_enc", "nec")
    addr = db.get("_addr", 0x00)

    if enc == "nec":
        return _encode_nec(addr, code)
    elif enc == "sirc":
        device, command = code
        return _encode_sirc(device, command)
    elif enc == "panasonic":
        return _encode_panasonic(addr, code)
    elif enc == "jvc":
        return _encode_jvc(addr, code)
    elif enc == "sharp":
        return _encode_sharp(addr, code)
    elif enc == "pioneer":
        return _encode_pioneer(addr, code)
    elif enc == "rc5":
        return _encode_rc5(addr, code)
    elif enc == "rc6":
        return _encode_rc6(addr, code)
    else:
        return _encode_nec(addr, code)


# ══════════════════════════════════════════════════════════════════════════════
#  ENVIO VIA ADB
# ══════════════════════════════════════════════════════════════════════════════

def _send_ir(device_id: str, freq: int, pattern: list, repeat: int = 1):
    """Envia padrão IR via ADB."""
    pattern_str = ",".join(str(p) for p in pattern)
    cmd = ["adb"]
    if device_id:
        cmd += ["-s", device_id]
    cmd += ["shell", "cmd", "irservice", "transmit", str(freq), pattern_str]
    for _ in range(repeat):
        subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        time.sleep(0.08)


def send_button(device_id: str, brand: str, button: str,
                repeat: int = 1, silent: bool = False) -> bool:
    """Envia um botão IR. Retorna True se o código existir."""
    freq, pattern = _get_ir_pattern(brand, button)
    if freq is None:
        if not silent:
            console.print(f"[dim yellow]  ⚠ '{button}' não mapeado para {brand}[/]")
        return False
    _send_ir(device_id, freq, pattern, repeat)
    if not silent:
        console.print(f"  [green]✓[/] [{brand.upper()}] [bold cyan]{button}[/]")
    return True


def _check_ir_support(device_id: str) -> bool:
    """Verifica se o dispositivo tem transmissor IR."""
    cmd = ["adb"]
    if device_id:
        cmd += ["-s", device_id]
    cmd += ["shell", "cmd", "irservice", "transmit", "38000", "1,1"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    output = (result.stdout + result.stderr).lower()
    return "not supported" not in output and "unavailable" not in output


# ══════════════════════════════════════════════════════════════════════════════
#  DESLIGAR TUDO — BROADCAST POWER OFF
# ══════════════════════════════════════════════════════════════════════════════

def broadcast_power_off(device_id: str, brands: list = None, repeat: int = 3):
    """
    Manda comando POWER para todas as marcas (ou lista específica).
    Envia múltiplas vezes por marca para garantir recepção.
    """
    targets = brands or ALL_BRANDS
    total   = len(targets)

    console.print(Panel(
        f"[bold red]⚡ DESLIGAR TUDO[/]\n\n"
        f"[white]Enviando Power OFF para [bold]{total}[/] marca(s)...\n"
        f"Repete [bold]{repeat}x[/] por marca para garantir recepção.[/]",
        border_style="red", padding=(0, 2)
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        TextColumn("[bold white]{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task("Enviando...", total=total)

        for brand in targets:
            progress.update(task, description=f"[bold yellow]{brand.upper()}[/]")
            freq, pattern = _get_ir_pattern(brand, "power")
            if freq and pattern:
                for _ in range(repeat):
                    _send_ir(device_id, freq, pattern)
                    time.sleep(0.15)
                progress.console.print(
                    f"  [green]✓[/] {brand.upper()} — "
                    f"[dim]{freq/1000:.1f}kHz × {repeat}x[/]"
                )
            else:
                progress.console.print(
                    f"  [dim]— {brand.upper()} sem código power[/]"
                )
            progress.advance(task)

    console.print(Panel(
        "[bold green]✓ Broadcast Power OFF concluído![/]\n\n"
        f"[white]Enviado para [bold]{total}[/] marcas.[/]",
        border_style="green", padding=(0, 2)
    ))


# ══════════════════════════════════════════════════════════════════════════════
#  MENU DO CONTROLE REMOTO
# ══════════════════════════════════════════════════════════════════════════════

REMOTE_LAYOUT = [
    ("⏻  Power",   "power"),    ("🔇 Mudo",     "mute"),
    ("🔊 Vol +",   "vol_up"),   ("🔉 Vol -",    "vol_down"),
    ("📺 Canal +", "ch_up"),    ("📺 Canal -",  "ch_down"),
    ("🔌 Source",  "source"),   ("📋 Menu",     "menu"),
    ("🏠 Home",    "home"),     ("↩  Back",     "back"),
    ("⬆  Cima",    "up"),       ("⬇  Baixo",    "down"),
    ("⬅  Esq",     "left"),     ("➡  Dir",      "right"),
    ("✅ OK",       "ok"),       ("🎬 Netflix",  "netflix"),
    ("▶  YouTube", "youtube"),  ("🔵 HDMI 1",   "hdmi1"),
    ("🔵 HDMI 2",  "hdmi2"),    ("🔵 HDMI 3",   "hdmi3"),
    ("1️⃣  1",       "num_1"),    ("2️⃣  2",        "num_2"),
    ("3️⃣  3",       "num_3"),    ("4️⃣  4",        "num_4"),
    ("5️⃣  5",       "num_5"),    ("6️⃣  6",        "num_6"),
    ("7️⃣  7",       "num_7"),    ("8️⃣  8",        "num_8"),
    ("9️⃣  9",       "num_9"),    ("0️⃣  0",        "num_0"),
    ("🚪 Sair",    None),
]


def _print_remote_menu(brand: str):
    t = Table(
        title=f"\n[bold magenta]📺 Controle — {brand.upper()}[/]\n",
        box=box.DOUBLE_EDGE, border_style="magenta",
        header_style="bold cyan", show_lines=True, min_width=56,
    )
    t.add_column(" # ", style="bold cyan", width=5, no_wrap=True)
    t.add_column("Botão", style="bold white", min_width=14)
    t.add_column(" # ", style="bold cyan", width=5, no_wrap=True)
    t.add_column("Botão", style="bold white", min_width=14)
    half = (len(REMOTE_LAYOUT) + 1) // 2
    for i in range(half):
        L = REMOTE_LAYOUT[i]
        R = REMOTE_LAYOUT[i + half] if i + half < len(REMOTE_LAYOUT) else ("", None)
        t.add_row(str(i+1), L[0],
                  str(i+half+1) if R[0] else "", R[0])
    console.print(t)


def _print_brands_table():
    t = Table(
        title="[bold magenta]📺 Marcas Suportadas[/]",
        box=box.SIMPLE_HEAVY, border_style="magenta",
        header_style="bold cyan", show_lines=False,
    )
    t.add_column("#",     style="bold cyan", width=4)
    t.add_column("Marca", style="bold white", min_width=14)
    t.add_column("#",     style="bold cyan", width=4)
    t.add_column("Marca", style="bold white", min_width=14)
    half = (len(ALL_BRANDS) + 1) // 2
    for i in range(half):
        L = ALL_BRANDS[i]
        R = ALL_BRANDS[i + half] if i + half < len(ALL_BRANDS) else ""
        t.add_row(str(i+1), L.upper(), str(i+half+1) if R else "", R.upper())
    console.print(t)


# ══════════════════════════════════════════════════════════════════════════════
#  FUNÇÃO PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def ir_remote_menu(device_id: str = None):
    """Menu principal do controle IR universal."""
    console.rule("[bold magenta]📺 Universal IR Remote[/]")

    # ── Verifica IR ───────────────────────────────────────────────────────────
    console.print("[cyan]Verificando suporte a IR...[/]")
    if not _check_ir_support(device_id):
        console.print(Panel(
            "[bold yellow]⚠ Adaptador IR pode não estar ativo.[/]\n\n"
            "• Conecte o adaptador IR no telefone\n"
            "• Abra o app de IR (se necessário)\n\n"
            "[dim]Tentando enviar mesmo assim...[/]",
            border_style="yellow", padding=(0, 2)
        ))
    else:
        console.print("[green]✓ IR detectado![/]")

    # ── Modo ──────────────────────────────────────────────────────────────────
    mode = Prompt.ask(
        "\n[cyan]Modo[/]",
        choices=["controle", "desligar_tudo"],
        default="controle"
    )

    # ── DESLIGAR TUDO ─────────────────────────────────────────────────────────
    if mode == "desligar_tudo":
        console.print("\n")
        _print_brands_table()
        custom = Confirm.ask(
            "\n[cyan]Enviar para TODAS as marcas?[/] (Não = escolher)",
            default=True
        )
        if custom:
            selected = ALL_BRANDS
        else:
            nums = Prompt.ask(
                f"[cyan]Números separados por vírgula (1-{len(ALL_BRANDS)})[/]"
            )
            idxs = [int(x.strip())-1 for x in nums.split(",")
                    if x.strip().isdigit()]
            selected = [ALL_BRANDS[i] for i in idxs
                        if 0 <= i < len(ALL_BRANDS)]

        repeat = IntPrompt.ask("[cyan]Repetições por marca[/]", default=3)
        broadcast_power_off(device_id, selected, repeat)
        return

    # ── CONTROLE SIMPLES ──────────────────────────────────────────────────────
    console.print()
    _print_brands_table()
    brand_num = IntPrompt.ask(
        f"[cyan]Número da marca (1-{len(ALL_BRANDS)})[/]", default=1
    )
    brand = ALL_BRANDS[max(0, min(brand_num-1, len(ALL_BRANDS)-1))]

    console.print(Panel(
        f"[bold white]Marca:[/]      [bold yellow]{brand.upper()}[/]\n"
        f"[bold white]Dispositivo:[/] {device_id or 'auto'}\n\n"
        "[dim]Aponte o telefone para a TV antes de enviar.[/]",
        border_style="magenta", padding=(0, 2)
    ))

    while True:
        console.print()
        _print_remote_menu(brand)
        total   = len(REMOTE_LAYOUT)
        choices = [str(i) for i in range(1, total + 1)]
        choice  = Prompt.ask("[bold cyan]Botão ▶[/]",
                             choices=choices, show_choices=False)
        idx = int(choice) - 1
        label, btn_key = REMOTE_LAYOUT[idx]
        if btn_key is None:
            console.print("[bold magenta]↩ Saindo.[/]")
            break
        send_button(device_id, brand, btn_key)
        time.sleep(0.05)
