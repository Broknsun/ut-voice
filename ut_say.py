#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ut_say.py — Undertale 风格文字发声器（纯标准库，无需第三方包）

每个可见字符触发一段极短的音，音高带随机抖动，标点处静音拉长，
听感接近 UT 里角色"说话"的 blip，而不是真人语音。

用法:
    python ut_say.py "heh. ok."                    # 用默认音色直接念
    python ut_say.py -v papyrus "NYEH HEH HEH!"
    python ut_say.py -f lines.txt -v toriel -o out.wav
    echo "my child..." | python ut_say.py -v toriel

音色: sans papyrus toriel flowey undyne alphys blook
"""

import argparse
import math
import os
import random
import struct
import sys
import tempfile
import wave

SR = 44100

VOICES = {
    "sans":    dict(type="square",   base=112, spread=0.10, dur=0.048, gain=1.00, rhythm=1.00, drop=0.94),
    "papyrus": dict(type="square",   base=330, spread=0.05, dur=0.042, gain=0.55, rhythm=0.82, drop=1.00),
    "toriel":  dict(type="triangle", base=214, spread=0.04, dur=0.055, gain=0.75, rhythm=1.12, drop=0.97),
    "flowey":  dict(type="square",   base=545, spread=0.03, dur=0.030, gain=0.34, rhythm=0.74, drop=1.03),
    "undyne":  dict(type="sawtooth", base=268, spread=0.07, dur=0.052, gain=0.42, rhythm=0.88, drop=0.96),
    "alphys":  dict(type="triangle", base=404, spread=0.12, dur=0.040, gain=0.50, rhythm=1.18, drop=1.05),
    "blook":   dict(type="sine",     base=96,  spread=0.02, dur=0.070, gain=0.85, rhythm=1.45, drop=0.92),
    "maxiang": dict(type="sine",     base=74,  spread=0.04, dur=0.085, gain=1.00, rhythm=1.58, drop=0.90),
}

PAUSE_COMMA = 0.15
PAUSE_STOP  = 0.25
PAUSE_NL    = 0.34
PAUSE_QUOTE = 0.06


def osc(kind, phase):
    """返回 [-1, 1] 的波形采样。phase 为 0..1 的循环相位。"""
    if kind == "square":
        return 1.0 if phase < 0.5 else -1.0
    if kind == "triangle":
        # 三角波，柔和
        return 4.0 * abs(phase - 0.5) - 1.0
    if kind == "sawtooth":
        return 2.0 * phase - 1.0
    # sine
    return math.sin(2.0 * math.pi * phase)


def render_blip(buf, freq, dur, kind, gain):
    """把一个短音叠加进采样缓冲（float 列表）。带快起快落包络，防爆音。"""
    n = int(SR * dur)
    if n <= 0:
        return
    phase = 0.0
    step = freq / SR
    attack = max(1, int(SR * 0.004))
    release = max(1, int(SR * 0.012))
    for i in range(n):
        # 包络：线性起音 → 保持 → 指数释放
        if i < attack:
            env = i / attack
        elif i > n - release:
            k = (n - i) / release
            env = k * k
        else:
            env = 1.0
        buf_i = len(buf) - n + i
        buf[buf_i] += osc(kind, phase) * env * gain
        phase += step
        if phase >= 1.0:
            phase -= 1.0


def silence(buf, dur):
    buf.extend([0.0] * int(SR * dur))


def synth(text, voice="sans", speed=1.0, jitter=0.06, volume=0.30, seed=None):
    v = VOICES[voice]
    if seed is not None:
        random.seed(seed)
    buf = []
    for ch in text:
        if ch == "\n":
            silence(buf, PAUSE_NL * v["rhythm"] / speed)
            continue
        if ch.isspace():
            silence(buf, 0.026 * v["rhythm"] / speed)
            continue
        if ch in "，,、；;：:":
            silence(buf, PAUSE_COMMA * v["rhythm"] / speed)
            continue
        if ch in "。.！!？?—…":
            silence(buf, PAUSE_STOP * v["rhythm"] / speed)
            continue
        if ch in "\"'“”‘’()（）[]【】《》":
            silence(buf, PAUSE_QUOTE * v["rhythm"] / speed)
            continue

        mul = 1.0 + (random.random() * 2.0 - 1.0) * jitter
        mul *= v["drop"]
        if ch in "？?":
            mul *= 1.22
        elif ch in "！!":
            mul *= 1.10

        is_cjk = ord(ch) > 0x2E80
        dur = v["dur"] * speed * (1.15 if is_cjk else 1.0) * v["rhythm"]
        # 预留静音槽，然后把音叠加进去
        silence(buf, dur)
        render_blip(buf, v["base"] * mul, dur, v["type"], v["gain"] * volume)
        silence(buf, 0.010 * v["rhythm"] / speed)

    silence(buf, 0.12)
    return buf


def write_wav(path, buf, volume=0.30):
    peak = max(1e-9, max(abs(x) for x in buf))
    scale = 0.92 / peak if peak > 0.999 else 1.0
    frames = bytearray()
    for x in buf:
        s = int(max(-1.0, min(1.0, x * scale)) * 32767)
        frames += struct.pack("<h", s)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))


def play(path):
    if os.name == "nt":
        import subprocess
        ps = (
            "$p = New-Object System.Media.SoundPlayer('%s'); "
            "$p.PlaySync();" % path.replace("'", "''")
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=False)
    else:
        for cmd in (["afplay", path], ["aplay", path], ["paplay", path]):
            try:
                import subprocess
                subprocess.run(cmd, check=True)
                return
            except Exception:
                continue
        print("已生成，但没有可用播放器:", path, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Undertale 风格文字发声器")
    ap.add_argument("text", nargs="?", help="要念的文本")
    ap.add_argument("-v", "--voice", default="sans", choices=sorted(VOICES))
    ap.add_argument("-f", "--file", help="从文件读取文本")
    ap.add_argument("-o", "--out", help="输出 wav 路径（默认临时文件）")
    ap.add_argument("-s", "--speed", type=float, default=1.0, help="语速倍率，越小越快")
    ap.add_argument("-j", "--jitter", type=float, default=0.06, help="音高抖动 0..0.3")
    ap.add_argument("--vol", type=float, default=0.30, help="音量 0..1")
    ap.add_argument("--seed", type=int, default=None, help="固定随机种子（可复现）")
    ap.add_argument("--no-play", action="store_true", help="只生成不播放")
    a = ap.parse_args()

    if a.file:
        with open(a.file, "r", encoding="utf-8") as f:
            text = f.read()
    elif a.text:
        text = a.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        text = "heh. ok."

    text = text.replace("\r\n", "\n").strip("\n")
    if not text:
        print("没有文本。", file=sys.stderr)
        sys.exit(1)

    buf = synth(text, a.voice, a.speed, a.jitter, a.vol, a.seed)
    out = a.out or os.path.join(tempfile.gettempdir(), "ut_say_%s.wav" % a.voice)
    write_wav(out, buf, a.vol)
    print(out)
    if not a.no_play:
        play(out)


if __name__ == "__main__":
    main()
