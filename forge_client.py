"""SD Forge API client for txt2img generation and model resolution."""

import requests

TIMEOUT_CHECK = 5
TIMEOUT_GENERATE = 600


class ForgeClient:
    def __init__(self, host: str = '127.0.0.1', port: str = '7860'):
        self.base_url = f'http://{host}:{port}'
        self._models_cache = None

    def check_connection(self) -> bool:
        """Check if Forge API is accessible."""
        try:
            resp = requests.get(
                f'{self.base_url}/sdapi/v1/options',
                timeout=TIMEOUT_CHECK,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def get_models(self) -> list[dict]:
        """Get list of available models from Forge."""
        if self._models_cache is not None:
            return self._models_cache
        try:
            resp = requests.get(
                f'{self.base_url}/sdapi/v1/sd-models',
                timeout=TIMEOUT_CHECK,
            )
            resp.raise_for_status()
            self._models_cache = resp.json()
            return self._models_cache
        except Exception:
            return []

    def resolve_model(self, model_name: str | None, model_hash: str | None) -> str | None:
        """Resolve model checkpoint name from metadata.

        Tries:
        1. Match by hash (exact match on hash field)
        2. Match by model_name (substring match on title)

        Returns the full model title for override_settings, or None.
        """
        models = self.get_models()
        if not models:
            return None

        # Try hash match first
        if model_hash:
            for m in models:
                if m.get('hash') == model_hash:
                    return m.get('title')

        # Try name substring match
        if model_name:
            for m in models:
                title = m.get('title', '')
                if model_name in title:
                    return title

        return None

    def build_payload(self, metadata: dict) -> dict:
        """Convert parsed PNG metadata to txt2img API payload.

        Uses the 'infotext' approach: pass the raw metadata text to Forge
        and let it parse all fields (including Hires fix, schedulers, etc.).
        Only override prompt/negative_prompt with edited versions.
        """
        payload = {
            'prompt': metadata.get('positive_prompt', ''),
            'negative_prompt': metadata.get('negative_prompt', ''),
            'send_images': True,
            'save_images': False,
            'override_settings_restore_afterwards': True,
        }

        # Use infotext to let Forge parse all generation parameters natively
        raw_infotext = metadata.get('_raw')
        if raw_infotext:
            payload['infotext'] = raw_infotext

        # Model resolution via override_settings
        override = {}
        model_name = metadata.get('Model')
        model_hash = metadata.get('Model hash')
        resolved = self.resolve_model(model_name, model_hash)
        if resolved:
            override['sd_model_checkpoint'] = resolved

        if override:
            payload['override_settings'] = override

        return payload

    def txt2img(self, payload: dict) -> dict:
        """Call txt2img API.

        Returns the API response dict.
        Raises on HTTP or connection errors.
        """
        resp = requests.post(
            f'{self.base_url}/sdapi/v1/txt2img',
            json=payload,
            timeout=TIMEOUT_GENERATE,
        )
        if not resp.ok:
            body = resp.text
            try:
                j = resp.json()
                detail = j.get('detail') or j.get('error') or j.get('errors') or body
            except Exception:
                detail = body
            raise RuntimeError(f"Forge API HTTP {resp.status_code}\n{detail}")
        return resp.json()
