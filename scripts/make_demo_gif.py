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
        frame("Hy3 VerifyLab", "Verifiable code tasks: beyond test pass/fail", [("Task E03: Two Sum", "Prompt, constraints, visible tests, and hidden tests", "#E8F1FF"), ("Run", "Hy3 returns concise auditable steps and code", "#F4EEFF")]),
        frame("Structured solution", "Every claim has a stable step ID and checkable evidence", [("S1", "Store previously visited value-index pairs in seen", "#EAF8F1"), ("S2", "Query complement; return distinct indices; O(n)", "#EAF8F1")]),
        frame("Three-way verification", "Model judgment is anchored by executable evidence", [("Execution", "Visible tests 2/2; hidden tests 3/3", "#E8F1FF"), ("Rules and static evidence", "Constraints, boundaries, contradictions, code policy", "#FFF4E5"), ("Hy3 review", "Step validity, first error, and error category", "#F4EEFF")]),
        frame("Critical mismatch", "All tests may pass while the stated process is invalid", [("Final answer", "CORRECT", "#EAF8F1"), ("Process step S1", "'Sorting preserves original indices' is false", "#FFE9E7"), ("Verdict", "Correct answer, unsupported process", "#FFF4E5")]),
        frame("Batch evaluation", "Analyze difficulty and validate the evaluator", [("Core metrics", "Answer accuracy, process accuracy, error distribution", "#E8F1FF"), ("Reliability", "Localization accuracy, false-positive rate, audit log", "#F4EEFF")]),
    ]
    out = ROOT / "assets" / "demo.gif"
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=1500, loop=0, optimize=True)
    print(out)


if __name__ == "__main__":
    main()
