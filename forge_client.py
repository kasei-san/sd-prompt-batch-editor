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

        Metadata keys -> API keys mapping:
            positive_prompt -> prompt
            negative_prompt -> negative_prompt
            Steps -> steps
            Sampler -> sampler_name
            Schedule type -> scheduler
            CFG scale -> cfg_scale
            Seed -> seed
            Size-1, Size-2 -> width, height
            Model + Model hash -> override_settings.sd_model_checkpoint
            Clip skip -> override_settings.CLIP_stop_at_last_layers
            Hires upscale -> hr_scale (+ enable_hr: true)
            Hires steps -> hr_second_pass_steps
            Hires upscaler -> hr_upscaler
            Denoising strength -> denoising_strength
        """
        payload = {
            'prompt': metadata.get('positive_prompt', ''),
            'negative_prompt': metadata.get('negative_prompt', ''),
            'steps': int(metadata.get('Steps', 20)),
            'sampler_name': metadata.get('Sampler', 'Euler a'),
            'cfg_scale': float(metadata.get('CFG scale', 7)),
            'seed': int(metadata.get('Seed', -1)),
            'width': int(metadata.get('Size-1', 512)),
            'height': int(metadata.get('Size-2', 512)),
            'send_images': True,
            'save_images': False,
            'override_settings_restore_afterwards': True,
        }

        # Scheduler
        schedule_type = metadata.get('Schedule type')
        if schedule_type and schedule_type != 'Automatic':
            payload['scheduler'] = schedule_type

        # Override settings
        override = {}

        # Model resolution
        model_name = metadata.get('Model')
        model_hash = metadata.get('Model hash')
        resolved = self.resolve_model(model_name, model_hash)
        if resolved:
            override['sd_model_checkpoint'] = resolved

        # Clip skip
        clip_skip = metadata.get('Clip skip')
        if clip_skip is not None:
            try:
                override['CLIP_stop_at_last_layers'] = int(clip_skip)
            except (ValueError, TypeError):
                pass

        if override:
            payload['override_settings'] = override

        # Hires fix
        hires_upscale = metadata.get('Hires upscale')
        if hires_upscale:
            try:
                payload['enable_hr'] = True
                payload['hr_scale'] = float(hires_upscale)
            except (ValueError, TypeError):
                pass

            hires_steps = metadata.get('Hires steps')
            if hires_steps:
                try:
                    payload['hr_second_pass_steps'] = int(hires_steps)
                except (ValueError, TypeError):
                    pass

            hires_upscaler = metadata.get('Hires upscaler')
            if hires_upscaler:
                payload['hr_upscaler'] = hires_upscaler

            # Forge requires this field when hires is enabled, otherwise crashes with NoneType error
            payload['hr_additional_modules'] = ['Use same choices']

        # Denoising strength
        denoise = metadata.get('Denoising strength')
        if denoise is not None:
            try:
                payload['denoising_strength'] = float(denoise)
            except (ValueError, TypeError):
                pass

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
        resp.raise_for_status()
        return resp.json()
