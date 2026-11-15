"""Fail closed on access restrictions before yt-dlp can try fallback clients.

These hooks are tested against the pinned yt-dlp version; review on every upgrade.
"""

from yt_dlp.extractor.youtube import YoutubeIE

from app.models.task import AppError


class RestrictedYoutubeIE(YoutubeIE):
    @classmethod
    def ie_key(cls):
        return "Youtube"

    def _download_initial_webpage(self, webpage_url, webpage_client, video_id):
        # Do not send yt-dlp's default has_verified / bpctr age-gate parameters.
        return self._download_webpage_with_retries(webpage_url, video_id)

    def _invalid_player_response(self, response, video_id):
        if response and response.get("playabilityStatus", {}).get("status") != "OK":
            raise AppError(
                "YouTube ограничил доступ к ролику. Импортируйте законно полученный файл."
            )
        return super()._invalid_player_response(response, video_id)

    @staticmethod
    def _is_agegated(response):
        if YoutubeIE._is_agegated(response):
            raise AppError(
                "Ролик имеет возрастное ограничение. Обход ограничений не поддерживается."
            )
        return False
