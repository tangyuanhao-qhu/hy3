from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
W, H = 1280, 720


def font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def frame(title: str, subtitle: str, cards: list[tuple[str, str, str]]) -> Image.Image:
    image = Image.new("RGB", (W, H), "#F7F9FC")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((40, 30, W - 40, H - 30), radius=24, fill="white", outline="#DDE3EC", width=2)
    draw.text((80, 65), title, fill="#182230", font=font(38, True))
    draw.text((80, 120), subtitle, fill="#526273", font=font(22))
    y = 190
    for heading, body, color in cards:
        draw.rounded_rectangle((80, y, W - 80, y + 125), radius=18, fill=color, outline="#CED6E0", width=2)
        draw.text((110, y + 18), heading, fill="#182230", font=font(25, True))
        draw.text((110, y + 60), body, fill="#334155", font=font(21))
        y += 145
    return image


def main() -> None:
    frames = [
        frame("Hy3 VerifyLab", "One complete solve-and-review flow: E03 Two Sum", [("Input", "Task, function signature, constraints, and visible tests", "#E8F1FF"), ("Run", "Hy3 returns auditable steps S1...Sn and executable code", "#F4EEFF")]),
        frame("Structured Hy3 solution", "Keep reasoning claims separate from executable code", [("S1 - invalid claim", "Sorting preserves original indices; return sorted positions", "#FFE9E7"), ("S2", "Actual code uses a seen hash map to find complements in O(n)", "#EAF8F1")]),
        frame("Automatic answer check", "Run visible and hidden tests in an isolated subprocess", [("Candidate code", "Hash lookup returns two distinct original indices", "#E8F1FF"), ("Execution evidence", "Visible tests pass; hidden tests 3/3 pass", "#EAF8F1"), ("Final answer", "CORRECT", "#EAF8F1")]),
        frame("Process-level evaluation", "Combine rule evidence with a separate Hy3 semantic review", [("Strong contradiction", "Sorting does not preserve the original index mapping", "#FFE9E7"), ("First error", "S1", "#FFF4E5"), ("Error category", "Concept error", "#FFF4E5")]),
        frame("Critical sample detected", "Passing every test does not prove that the process is valid", [("Final answer", "CORRECT", "#EAF8F1"), ("Reasoning process", "INVALID", "#FFE9E7"), ("Verdict", "Correct answer, unsupported process", "#FFF4E5")]),
        frame("Hy3 run2 summary", "All 90 stratified tasks completed with downloadable evidence", [("Answer", "90/90 tasks and 680/680 hidden assertions pass", "#EAF8F1"), ("Process - corrected estimate", "85/90 valid; 5 correct answers have unsupported processes", "#FFF4E5"), ("Evaluator validity", "Localization, false alarms, error types, and human audit", "#F4EEFF")]),
    ]
    out = ROOT / "assets" / "demo.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=2200, loop=0, optimize=True)
    print(out)


if __name__ == "__main__":
    main()
