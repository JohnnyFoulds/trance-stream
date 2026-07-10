# ASCII Video Conversion Methodology

## Summary

Two new animations were added to the trance-stream visualiser alongside the existing
Bad Apple and Star Wars overlays: **Nyan Cat** and the **spinning donut (torus)**.
Both render in full-canvas cover mode (fill ratio ≥ 0.98) with high visual quality.

**New assets added:**
- `ascii_videos/nyan_cat_14fps_60x19.txt` — 12 frames, 28 KB
- `ascii_videos/donut_25fps_60x28.txt` — 90 frames, 167 KB

**New tools added:**
- `tools/convert_to_ascii.py` — general-purpose GIF/video-to-ASCII converter
- `tools/fetch_nyan_cat.py` — downloads and converts Nyan Cat from nyan.cat
- `tools/fetch_donut.py` — generates the spinning donut programmatically (no download)

---

## Content selection criteria

For a visualization to match Bad Apple's visual quality in the trance-stream overlay
system, it must satisfy three requirements:

### 1. Full-canvas fill ratio (≥ 0.9)

The visualiser uses `content_fill_ratio()` from `tools/ascii_video.py` to detect whether
content is full-canvas (fill ≥ 0.9) or logo/portrait art (fill < 0.9). Full-canvas content
triggers **cover-mode scaling**: the entire CA rain area is coloured, producing an immersive
effect. Both new animations achieve fill ≥ 0.98.

### 2. Character gradient spanning all four visualiser tiers

The visualiser's `_av_color()` function (visualiser.py:764–772) maps source characters to
four ANSI brightness tiers:

| Tier | Characters | ANSI effect |
|------|-----------|-------------|
| BG | `' '` | dim blue (recedes) |
| FADE | `.,:;``'"_-` | dim cyan (fade trail) |
| MID | `!|/\()[]{}+~?<>^*` | cyan (active mid-tone) |
| BRIGHT | `#@%MW&$X08B` | bold white (maximum brightness) |

The 10-character luminance gradient `' .,:-+*%@#'` maps pixel luminances to
representatives of all four tiers. Both animations use all four tiers.

### 3. Genuine animation (multiple unique frames)

Static or single-frame content produces a frozen image, not an animation. Verified that:
- Nyan Cat: 12 frames total, 7 pixel-distinct frames
- Donut: 90 frames, all distinct (continuous rotation)

### Why color GIFs don't work well

Colorful internet GIFs (e.g. Hatsune Miku from Giphy) typically fail for two reasons:
1. Giphy CDN often serves a static preview as the `.gif` endpoint — all frames are
   pixel-identical despite the response having multiple GIF frames.
2. Even when genuine, color→grayscale conversion of animation with similar luminance
   across regions produces mid-tone soup at 60-column resolution — no visible structure.

The overlay system only uses luminance, so content must have strong luminance contrast
(not just hue contrast) to look recognizable. Silhouette animations and purpose-built
B&W content (Bad Apple, Star Wars) work best. The donut avoids this entirely by
being generated directly in ASCII.

---

## Converter algorithm

### Tool: `tools/convert_to_ascii.py`

**Public API:**
```python
GRADIENT = ' .,:-+*%@#'  # 10 chars: BG + 4×FADE + 2×MID + 3×BRIGHT

def convert_gif(input_path, output_dir, target_width=60) -> tuple[str, int, int, int]:
    """Returns (out_path, fps, width, height)."""
```

### Luminance quantization

Each pixel's luminance value L ∈ [0, 255] is mapped to a character index via:

```python
idx = min(int(L / 256 * N), N - 1)   # N = 10
char = GRADIENT[idx]
```

Numpy vectorised implementation:
```python
arr = np.asarray(gray_image)                           # shape (H, W), uint8
indices = np.clip(arr.astype(np.int32) * N // 256, 0, N - 1)
rows = [''.join(GRADIENT[i] for i in row) for row in indices.tolist()]
```

**Why not `'=''`?** The character `=` is absent from all four `_av_color` tier sets.
It falls through `_av_color()` to dim-blue — visually identical to a space.
Using `,` at position 2 ensures a FADE-tier character there.

### Grayscale conversion

Each frame is converted via `frame.convert('RGBA').convert('L')`. The RGBA intermediate
handles GIF palette mode ('P') with transparency: converting P→RGBA expands the palette
and applies alpha; transparent areas become near-black (lum ≈ 0) → space in ASCII output.

### GIF frame compositing

**Critical bug fixed**: `ImageSequence.Iterator` fails on GIFs with disposal mode 2
(restore-to-background) — it returns the same composited canvas for every frame.
The correct approach is `img.copy()` + seek loop:

```python
frames = []
try:
    while True:
        frames.append(img.copy())
        img.seek(img.tell() + 1)
except EOFError:
    pass
```

`img.copy()` forces PIL to materialize the composited frame at the current seek position.

### Aspect ratio and height

Terminal cells are approximately 2× taller than they are wide. The 0.5 correction:
```python
target_height = max(12, round(target_width / pixel_ar * 0.5))
```

The `max(12, ...)` floor ensures the one-frame-per-line format detection in `load_frames()`
fires correctly (requires `literal_nl > real_nl * 10`; at h=12 the ratio is 11 > 10).

### FPS detection

```python
avg_ms = sum(durations_ms) / len(durations_ms)
fps = max(1, round(1000 / avg_ms))
```

Default duration is 100 ms if a frame's `info['duration']` key is absent.

### Output format

One-frame-per-line format with literal `\n` row separators:
```python
lines = ['\\n'.join(row for row in frame) for frame in frames]
path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
```

Output filename encodes dimensions: `{stem}_{fps}fps_{width}x{height}.txt`

---

## Content sources

### Nyan Cat

| Property | Value |
|----------|-------|
| Original creator | Torres, C. (prguitarman) |
| Source URL | `https://www.nyan.cat/cats/original.gif` |
| Pixel dimensions | 272 × 168 px |
| Frame count | 12 (7 pixel-distinct) |
| Frame duration | 70 ms uniform → fps = 14 |
| Download size | 27,954 bytes |
| ASCII output | `ascii_videos/nyan_cat_14fps_60x19.txt` (28 KB) |
| Fill ratio | 1.000 |
| ASCII dimensions | 60 × 19 chars |
| Fetch script | `tools/fetch_nyan_cat.py` |

The Nyan Cat animation is a short seamless loop created by Chris Torres in 2011.
The original GIF is hosted at nyan.cat, confirmed to serve genuine multi-frame content.

**Note**: Giphy CDN URLs (e.g. `media.giphy.com/media/*/giphy.gif`) should not be used
as they frequently serve a static single-frame preview image for all 46 "frames" — all
frames are pixel-identical despite having distinct GIF frame boundaries.

### Spinning Donut

| Property | Value |
|----------|-------|
| Algorithm author | Sloane, A. (a1k0n) |
| Source | Programmatically generated — no download required |
| Frame count | 90 (all distinct) |
| FPS | 25 |
| ASCII output | `ascii_videos/donut_25fps_60x28.txt` (167 KB) |
| Fill ratio | 0.983 |
| ASCII dimensions | 60 × 28 chars |
| Generator script | `tools/fetch_donut.py` |

The donut is generated by rotating a parametric torus and computing surface luminance
from a dot-product with a fixed light direction. Each point on the torus surface maps
to a luminance value → GRADIENT character. The `A` (x-axis tilt) and `B` (z-axis spin)
angles advance at different rates per frame (A += 0.08, B += 0.04) producing a tumbling
rotation rather than a flat spin.

---

## Reproduction steps

### Nyan Cat
```
pip install -r tools/requirements-research.txt  # for Pillow
python tools/fetch_nyan_cat.py
```

### Donut (no dependencies beyond stdlib + numpy)
```
python tools/fetch_donut.py
```

### Verify both
```
pytest tests/test_ascii_video_discovery.py tests/test_convert_to_ascii.py -v
```

---

## Known quality considerations

**Nyan Cat character aspect ratio.** The 0.5 vertical compression assumes 2:1 terminal
cell aspect ratio. In practice the cat looks slightly tall in some fonts; the original
source is low-resolution enough that this is not perceptible.

**GIF frame compositing.** `ImageSequence.Iterator` fails on disposal mode 2 GIFs
(returns the same frame every time). Fixed by using `img.copy()` + seek loop. See
implementation in `_gif_to_ascii_frames()` in `tools/convert_to_ascii.py`.

**Giphy static preview problem.** Many Giphy `.gif` URLs return a static preview image,
not the actual animated GIF. Symptom: 46 frames are returned but all are pixel-identical
(zero unique frames). Use `hashlib.md5` on frame bytes to detect this before converting.

**Donut K1 scaling.** The `K1` constant controls how large the donut appears in the frame.
Setting `K1 = width * K2 * 3.0 / (8.0 * (R1 + R2))` gives fill ≈ 0.98 at 60×28.
Adjusting R1, R2, or K2 changes the torus proportions; adjusting K1 changes apparent size.

---

## References

Clark, A., & contributors. (2024). *Pillow (Version 10.x)* [Software]. The Pillow
    maintainers. https://pillow.readthedocs.io/

Harris, C. R., Millman, K. J., van der Walt, S. J., Gommers, R., Virtanen, P., Cournapeau,
    D., Wieser, E., Taylor, J., Berg, S., Smith, N. J., Kern, R., Picus, M., Hoyer, S.,
    van Kerkwijk, M. H., Brett, M., Haldane, A., del Río, J. F., Wiebe, M., Peterson, P.,
    … Oliphant, T. E. (2020). Array programming with NumPy. *Nature*, *585*, 357–362.
    https://doi.org/10.1038/s41586-020-2649-2

Sloane, A. (2011). *Donut math: how donut.c works* [Blog post].
    https://www.a1k0n.net/2011/07/20/donut-math.html

Torres, C. [prguitarman]. (2011). *Nyan Cat* [Animated GIF]. nyan.cat
