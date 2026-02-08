"""PNG metadata parser - extracts and parses Stable Diffusion generation parameters."""

import re
from PIL import Image

re_param = re.compile(r'\s*(\w[\w \-/]+):\s*("(?:\\.|[^\\"])+"|[^,]*)(?:,|$)')
re_imagesize = re.compile(r"^(\d+)x(\d+)$")

# Numeric fields that should be converted from string
_INT_FIELDS = {'Steps', 'Seed', 'Clip skip', 'Hires steps', 'Size-1', 'Size-2'}
_FLOAT_FIELDS = {'CFG scale', 'Denoising strength', 'Hires upscale'}


def read_metadata(filepath: str) -> str | None:
    """Read the 'parameters' text chunk from a PNG file.

    Returns the raw parameters string, or None if not found.
    """
    try:
        with Image.open(filepath) as img:
            return img.info.get('parameters')
    except Exception:
        return None


def is_sd_metadata(text: str) -> bool:
    """Check if the text looks like SD generation parameters (not ComfyUI/NovelAI)."""
    return 'Steps:' in text


def _unquote(s: str) -> str:
    """Remove surrounding quotes and unescape."""
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
        s = s.replace('\\"', '"').replace('\\\\', '\\')
    return s


def parse_generation_parameters(x: str) -> dict:
    """Parse generation parameters string from PNG metadata.

    Ported from Forge's infotext_utils.py:parse_generation_parameters.

    Returns a dict with keys:
        - positive_prompt: str
        - negative_prompt: str
        - Plus all key-value pairs from the settings line (Steps, Sampler, etc.)
        - Size is split into Size-1 (width) and Size-2 (height)
        - Numeric fields are converted to int/float
    """
    res = {}
    prompt = ""
    negative_prompt = ""
    done_with_prompt = False

    *lines, lastline = x.strip().split("\n")

    # If the last line doesn't look like a settings line, treat it as prompt text
    if len(re_param.findall(lastline)) < 3:
        lines.append(lastline)
        lastline = ''

    for line in lines:
        line = line.strip()
        if line.startswith("Negative prompt:"):
            done_with_prompt = True
            line = line[16:].strip()
        if done_with_prompt:
            negative_prompt += ("" if negative_prompt == "" else "\n") + line
        else:
            prompt += ("" if prompt == "" else "\n") + line

    # Parse key-value pairs from the settings line
    for k, v in re_param.findall(lastline):
        try:
            v = _unquote(v)

            m = re_imagesize.match(v)
            if m is not None:
                res[f"{k}-1"] = m.group(1)
                res[f"{k}-2"] = m.group(2)
            else:
                res[k] = v
        except Exception:
            pass

    res['positive_prompt'] = prompt
    res['negative_prompt'] = negative_prompt

    # Set defaults
    if 'Clip skip' not in res:
        res['Clip skip'] = '1'
    if 'Schedule type' not in res:
        res['Schedule type'] = 'Automatic'

    # Convert numeric fields
    for field in _INT_FIELDS:
        if field in res:
            try:
                res[field] = int(res[field])
            except (ValueError, TypeError):
                pass

    for field in _FLOAT_FIELDS:
        if field in res:
            try:
                res[field] = float(res[field])
            except (ValueError, TypeError):
                pass

    return res


def reconstruct_infotext(original_raw: str, new_positive: str, new_negative: str) -> str:
    """Reconstruct raw infotext text with edited prompts.

    Replaces the positive and negative prompts in the raw metadata text
    while preserving the settings line. This ensures Forge sees consistent
    prompt data in both the explicit fields and the infotext.
    """
    lines = original_raw.strip().split("\n")

    # Find the settings line (last line with 3+ key-value pairs)
    *content_lines, lastline = lines
    if len(re_param.findall(lastline)) < 3:
        # Last line is not a settings line, treat as content
        content_lines.append(lastline)
        lastline = ''

    # Reconstruct: new_positive + Negative prompt: new_negative + settings line
    parts = [new_positive]
    if new_negative:
        parts.append(f"Negative prompt: {new_negative}")
    if lastline:
        parts.append(lastline)

    return '\n'.join(parts)


def extract_metadata(filepath: str) -> dict | None:
    """Read a PNG file and extract parsed generation parameters.

    Returns None if the file has no valid SD metadata.
    The returned dict includes '_raw' key with the original parameters text.
    """
    raw = read_metadata(filepath)
    if raw is None or not is_sd_metadata(raw):
        return None
    result = parse_generation_parameters(raw)
    result['_raw'] = raw
    return result
