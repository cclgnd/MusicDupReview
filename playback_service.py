import io
import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    import pygame
    pygame.mixer.init()
    AUDIO_AVAILABLE = True
except Exception:
    pygame = None
    AUDIO_AVAILABLE = False


class PlaybackError(RuntimeError):
    pass


class PlaybackService:
    @property
    def available(self):
        return AUDIO_AVAILABLE

    def duration(self, path):
        if not AUDIO_AVAILABLE:
            return 0.0
        try:
            sound = pygame.mixer.Sound(path)
            value = float(sound.get_length())
            del sound
            return value
        except Exception:
            return 0.0

    def play(self, path):
        if not AUDIO_AVAILABLE:
            raise PlaybackError("pygame not available")
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()

    def seek(self, seconds):
        if not AUDIO_AVAILABLE:
            return
        pygame.mixer.music.play(start=seconds)

    def pause(self):
        if not AUDIO_AVAILABLE:
            return
        pygame.mixer.music.pause()

    def resume(self):
        if not AUDIO_AVAILABLE:
            return
        pygame.mixer.music.unpause()

    def stop(self):
        if not AUDIO_AVAILABLE:
            return
        pygame.mixer.music.stop()

    def position_seconds(self):
        if not AUDIO_AVAILABLE:
            return -1.0
        return pygame.mixer.music.get_pos() / 1000.0

    def is_busy(self):
        return bool(AUDIO_AVAILABLE and pygame.mixer.music.get_busy())

    def release(self):
        if not AUDIO_AVAILABLE:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        try:
            pygame.mixer.music.unload()
        except Exception:
            try:
                empty_wav = (b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
                             b"\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00"
                             b"\x02\x00\x10\x00data\x00\x00\x00\x00")
                pygame.mixer.music.load(io.BytesIO(empty_wav))
            except Exception:
                pass
