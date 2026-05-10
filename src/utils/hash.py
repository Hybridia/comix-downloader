"""
Comix.to API request signing.

Ported from HaruNeko's ``ComixTo.ts`` (May 2026 revision). The site
swapped algorithms with the migration to the ``/api/v1`` API: new keys,
a new mutation table, and the round structure inverted (mutate first,
then RC4 — the old code did the opposite).

This is the **fast path**. When the server accepts the produced token,
we paginate the chapter list and fetch per-chapter pages over plain
HTTP. When it returns ``Invalid token`` (which it currently does as of
2026-05-10 — even HaruNeko's own May-8 keys are rejected), the API
wrapper falls back to a Playwright capture in ``comix_capture.py``.

Keep this file in sync with HaruNeko upstream:
``manga-download/haruneko`` → ``web/src/engine/websites/ComixTo.ts``.
When their fix lands, the only thing that should need updating here is
the ``KEYS`` array (and possibly the ``Mutate`` table).
"""

import base64
import urllib.parse
from typing import List


class ComixHash:
    """RC4 + per-round mutation cipher used to sign Comix.to API paths."""

    # ── Cipher key triples (RC4 key, mutation key, prefix key) per round ──
    KEYS = [
        "JxTcdyiA5GZxnbrmthXBQfU2IMTKcY1+3nNhbq98Sgo=", "3PordjODbhqla382Cxapmo/1JiABJQcjiJj1+48gTJ4=", "OaKvnI5ARA==",
        "MHNBHYWA7lvy867fXgvGcJwWDk79KqUJUVFsh3RwnnI=", "8i0Cru/VJBSVB2Y1GcMDVpzx2WepOcfnWdd81yxICl4=", "Fyskubz8VvA=",
        "B46L1x+UeWP+19cRpQ+OZvdLAK9EHID8g3mSgn57tew=", "DTSTmUt6LpDUw9r1lSQqyb3YlFTzruT8tk8wUGkwehQ=", "vY/meeI=",
        "7xWfIF5THL5LAnRgAARg+4mjWHPU9n3PQwvzbaMNi+Q=", "bewtiTuV+HJk56xxkf2iCljLgruCpBmN9BgE8i6gc9M=", "/Xcb2zAu8AU=",
        "WgeCQ3T8R51uTwVSiVa7Zy0dN6JOg6Z5JleMS+HV8Aw=", "yXayUVFrrcW56jQCEfZzuCidjpnWKjTDUNT7XeX9i7k=", "tSLco2w=",
    ]

    # (rc4_idx, mut_idx, pref_idx, prefix_limit) per round.
    _ROUND_CFG = {
        1: (0, 1, 2, 7),
        2: (3, 4, 5, 8),
        3: (6, 7, 8, 5),
        4: (9, 10, 11, 8),
        5: (12, 13, 14, 5),
    }

    @staticmethod
    def _key_bytes() -> List[bytes]:
        return [base64.b64decode(k) for k in ComixHash.KEYS]

    @staticmethod
    def rc4(key: bytes, data: bytes) -> bytes:
        if not key:
            return bytes(data)
        s = list(range(256))
        j = 0
        for i in range(256):
            j = (j + s[i] + key[i % len(key)]) & 0xff
            s[i], s[j] = s[j], s[i]
        i = 0
        j = 0
        out = bytearray(len(data))
        for k in range(len(data)):
            i = (i + 1) & 0xff
            j = (j + s[i]) & 0xff
            s[i], s[j] = s[j], s[i]
            out[k] = data[k] ^ s[(s[i] + s[j]) & 0xff]
        return bytes(out)

    # ── Bit-shuffle primitives used by the mutation table. ──
    @staticmethod
    def _sr7l1(e: int) -> int: return ((e >> 7) | (e << 1)) & 0xff
    @staticmethod
    def _sl1r7(e: int) -> int: return ((e << 1) | (e >> 7)) & 0xff
    @staticmethod
    def _sr2l6(e: int) -> int: return ((e >> 2) | (e << 6)) & 0xff
    @staticmethod
    def _sl4r4(e: int) -> int: return ((e << 4) | (e >> 4)) & 0xff
    @staticmethod
    def _sr4l4(e: int) -> int: return ((e >> 4) | (e << 4)) & 0xff

    @staticmethod
    def _get_mut_key(mk: bytes, idx: int) -> int:
        return mk[idx % 32] if (len(mk) > 0 and idx % 32 < len(mk)) else 0

    @classmethod
    def _mutate(
        cls,
        data: bytes,
        mut_key: bytes,
        pref_key: bytes,
        pref_limit: int,
        rnd: int,
    ) -> bytes:
        out = bytearray()
        for o, byte in enumerate(data):
            if o < pref_limit and o < len(pref_key):
                out.append(pref_key[o])
            n = (byte ^ cls._get_mut_key(mut_key, o)) & 0xff
            m = o % 10
            if rnd == 1:
                if m == 0: n = cls._sr7l1(n)
                elif m == 1: n ^= 37
                elif m == 2: n ^= 81
                elif m == 3: n ^= 147
                elif m == 4: n = cls._sr2l6(n)
                elif m in (5, 8): n = cls._sr4l4(n)
                elif m == 6: n ^= 218
                elif m == 7: n = (n + 159) & 0xff
                elif m == 9: n ^= 180
            elif rnd == 2:
                if m in (0, 9): n ^= 180
                elif m == 1: n = cls._sl1r7(n)
                elif m == 2: n ^= 147
                elif m == 3: n = cls._sr7l1(n)
                elif m == 4: n = cls._sr2l6(n)
                elif m == 5: n = cls._sr4l4(n)
                elif m in (6, 8): n = (n + 159) & 0xff
                elif m == 7: n = (n + 34) & 0xff
            elif rnd == 3:
                if m == 0: n ^= 81
                elif m == 1: n = cls._sr4l4(n)
                elif m in (2, 9): n = cls._sl4r4(n)
                elif m == 3: n ^= 37
                elif m == 4: n = (n + 159) & 0xff
                elif m == 5: n = cls._sl1r7(n)
                elif m == 6: n ^= 180
                elif m == 7: n = (n + 34) & 0xff
                elif m == 8: n = cls._sr2l6(n)
            elif rnd == 4:
                if m in (0, 7): n ^= 218
                elif m in (1, 4): n = cls._sl1r7(n)
                elif m == 2: n = cls._sr7l1(n)
                elif m == 3: n = (n + 159) & 0xff
                elif m in (5, 8): n ^= 180
                elif m == 6: n ^= 147
                elif m == 9: n ^= 37
            elif rnd == 5:
                if m == 0: n = cls._sl4r4(n)
                elif m in (1, 3): n ^= 147
                elif m == 2: n = (n + 34) & 0xff
                elif m in (4, 9): n ^= 218
                elif m in (5, 7): n = cls._sl1r7(n)
                elif m == 6: n ^= 180
                elif m == 8: n = cls._sr2l6(n)
            out.append(n & 0xff)
        return bytes(out)

    @classmethod
    def _round(cls, data: bytes, n: int) -> bytes:
        kb = cls._key_bytes()
        rc4_idx, mut_idx, pref_idx, plimit = cls._ROUND_CFG[n]
        return cls.rc4(kb[rc4_idx], cls._mutate(data, kb[mut_idx], kb[pref_idx], plimit, n))

    @classmethod
    def generate_hash(cls, path: str, body_size: int = 0, time: int = 1) -> str:
        """
        Generate the URL-safe base64 ``_=`` token for a request path.

        ``body_size`` and ``time`` are accepted for backward compatibility
        with the old ``/api/v2`` signature but are ignored — the new
        algorithm hashes the path alone (HaruNeko upstream confirmed).
        """
        encoded = urllib.parse.quote(path, safe="-_.!~*'()")
        data = encoded.encode("utf-8")
        for n in range(1, 6):
            data = cls._round(data, n)
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def generate_comix_hash(path: str, body_size: int = 0, time: int = 1) -> str:
    """Convenience wrapper kept for the existing ``ComixAPI`` callsites."""
    return ComixHash.generate_hash(path, body_size, time)
