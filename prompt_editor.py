"""Prompt tokenizer and editor for Stable Diffusion prompts."""

import re


def tokenize(prompt: str) -> list[str]:
    """Split a prompt into tokens respecting bracket depth.

    Commas inside parentheses/brackets/angle brackets are NOT treated as separators.
    Examples:
        "masterpiece, (tag1, tag2:1.3), <lora:name:0.8>"
        -> ["masterpiece", "(tag1, tag2:1.3)", "<lora:name:0.8>"]
    """
    tokens = []
    current = []
    depth_round = 0   # ()
    depth_square = 0  # []
    depth_angle = 0   # <>

    for ch in prompt:
        if ch == '(' :
            depth_round += 1
            current.append(ch)
        elif ch == ')':
            depth_round = max(0, depth_round - 1)
            current.append(ch)
        elif ch == '[':
            depth_square += 1
            current.append(ch)
        elif ch == ']':
            depth_square = max(0, depth_square - 1)
            current.append(ch)
        elif ch == '<':
            depth_angle += 1
            current.append(ch)
        elif ch == '>':
            depth_angle = max(0, depth_angle - 1)
            current.append(ch)
        elif (ch == ',' or ch == '\n') and depth_round == 0 and depth_square == 0 and depth_angle == 0:
            token = ''.join(current).strip()
            if token:
                tokens.append(token)
            current = []
        else:
            current.append(ch)

    # Last token
    token = ''.join(current).strip()
    if token:
        tokens.append(token)

    return tokens


def tokens_to_prompt(tokens: list[str]) -> str:
    """Join tokens back into a prompt string."""
    return ', '.join(tokens)


# Pattern to strip outer brackets and weight suffix
# Matches: (content:weight), (content), [content], ((content)), etc.
_re_outer_parens = re.compile(r'^[\(\[]+(.+?)(?::\s*[\d.]+)?[\)\]]+$')


def extract_core(token: str) -> str:
    """Extract the core tag from a token by stripping brackets and weights.

    Examples:
        "(masterpiece:1.2)" -> "masterpiece"
        "((best quality))" -> "best quality"
        "[lowres]" -> "lowres"
        "masterpiece" -> "masterpiece"
        "<lora:name:0.8>" -> "<lora:name:0.8>"  (LORA kept as-is)
    """
    t = token.strip()

    # Don't strip angle brackets (LORA/embedding syntax)
    if t.startswith('<') and t.endswith('>'):
        return t

    # Repeatedly strip outer parentheses/brackets and weight
    prev = None
    while t != prev:
        prev = t
        m = _re_outer_parens.match(t)
        if m:
            t = m.group(1).strip()

    return t


def remove_tags(prompt: str, tags_to_remove: list[str]) -> str:
    """Remove specified tags from a prompt.

    Matching is done on the core part (brackets/weights stripped).
    Case-insensitive comparison.
    """
    if not tags_to_remove:
        return prompt

    # Normalize removal targets
    remove_cores = set()
    for tag in tags_to_remove:
        for sub_tag in tokenize(tag):
            remove_cores.add(extract_core(sub_tag).lower())

    tokens = tokenize(prompt)
    filtered = [t for t in tokens if extract_core(t).lower() not in remove_cores]
    return tokens_to_prompt(filtered)


def add_tags(prompt: str, tags_to_add: str) -> str:
    """Add tags to the end of a prompt."""
    tags_to_add = tags_to_add.strip()
    if not tags_to_add:
        return prompt
    prompt = prompt.strip()
    if not prompt:
        return tags_to_add
    return prompt + ', ' + tags_to_add


def find_common_tags(prompts: list[str]) -> list[str]:
    """Find tags common to ALL prompts.

    Returns list of core tags present in every prompt.
    """
    if not prompts:
        return []

    # Build sets of core tags for each prompt
    tag_sets = []
    for p in prompts:
        cores = set()
        for token in tokenize(p):
            cores.add(extract_core(token).lower())
        tag_sets.append(cores)

    # Intersection of all sets
    common = tag_sets[0]
    for s in tag_sets[1:]:
        common = common & s

    # Return in the order they appear in the first prompt, using original form
    result = []
    seen = set()
    for token in tokenize(prompts[0]):
        core = extract_core(token).lower()
        if core in common and core not in seen:
            result.append(extract_core(token))
            seen.add(core)

    return result


def apply_edits(prompt: str, remove: str, add: str) -> str:
    """Apply tag removals and additions to a prompt.

    Args:
        prompt: Original prompt string.
        remove: Comma-separated tags to remove.
        add: Comma-separated tags to add.

    Returns:
        Edited prompt string.
    """
    remove_list = [t.strip() for t in remove.split(',') if t.strip()] if remove.strip() else []
    result = remove_tags(prompt, remove_list)
    result = add_tags(result, add)
    return result
