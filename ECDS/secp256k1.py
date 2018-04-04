import secrets
import message

import ECDS
from number_theory_stuff import mulinv, modsqrt
from transformations import int_to_bytes, bytes_to_int, hex_to_int, bytes_to_hex, hex_to_bytes

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F

# Generator
G = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798, 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

# Order
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

CURVE = ECDS.Curve(P, 0, 7, G, N, name='secp256k1')


class Point(ECDS.Point):

    def __init__(self, x, y):
        super().__init__(x, y, CURVE)


class PrivateKey(message.Message):

    @classmethod
    def random(cls):
        key = secrets.randbelow(N)
        return cls.from_int(key)

    @classmethod
    def from_wif(cls, wif):
        from btctools import base58, sha256
        bts = base58.decode(wif)
        bt80, key, checksum = bts[0:1], bts[1:-4], bts[-4:]
        assert sha256(sha256(bt80 + key))[:4] == checksum, 'Invalid Checksum'
        assert bt80 == b'\x80', 'Invalid Format'
        if key.endswith(b'\x01'):
            key = key[:-1]
            compressed = True  # TODO
        else:
            compressed = False  # TODO
        return cls(key)

    def wif(self, compressed=False):
        from btctools import base58, sha256
        extended = b'\x80' + self.bytes() + (b'\x01' if compressed else b'')
        hashed = sha256(sha256(extended))
        checksum = hashed[:4]
        return base58.encode(extended + checksum)

    def to_public(self):
        point = CURVE.G * self.int()
        return PublicKey(point)

    def __repr__(self):
        return f"PrivateKey({self.msg})"


class PublicKey:

    def __init__(self, point):
        self.point = point

    def __eq__(self, other):
        return self.point == other.point

    def __repr__(self):
        return f"PublicKey({self.x}, {self.y})"

    @classmethod
    def decode(cls, key):
        if key.startswith(b'\x04'):        # uncompressed key
            assert len(key) == 65, 'An uncompressed public key must be 65 bytes long'
            x, y = bytes_to_int(key[1:33]), bytes_to_int(key[33:])
        else:                              # compressed key
            assert len(key) == 33, 'A compressed public key must be 33 bytes long'
            x = bytes_to_int(key[1:])
            root = modsqrt(CURVE.f(x), P)
            if key.startswith(b'\x03'):    # odd root
                y = root if root % 2 == 1 else -root % P
            elif key.startswith(b'\x02'):  # even root
                y = root if root % 2 == 0 else -root % P
            else:
                assert False, 'Wrong key format'

        return cls(Point(x, y))

    @classmethod
    def from_private(cls, prv):
        key = PrivateKey(prv) if isinstance(prv, int) else prv
        return key.to_public()

    @classmethod
    def from_hex(cls, hexstring):
        return cls.decode(hex_to_bytes(hexstring))

    @property
    def x(self):
        """X coordinate of the (X, Y) point"""
        return self.point.x

    @property
    def y(self):
        """Y coordinate of the (X, Y) point"""
        return self.point.y

    def encode(self, compressed=False):
        if compressed:
            if self.y & 1:  # odd root
                return b'\x03' + int_to_bytes(self.x).zfill(32)
            else:           # even root
                return b'\x02' + int_to_bytes(self.x).zfill(32)
        return b'\x04' + int_to_bytes(self.x).zfill(32) + int_to_bytes(self.y).zfill(32)

    def hex(self, compressed=False):
        return bytes_to_hex(self.encode(compressed=compressed))

    def to_address(self, addrtype):
        from btctools.address import pubkey_to_address
        return pubkey_to_address(self, addrtype)


def generate_keypair():
    private = PrivateKey.random()
    public = private.to_public()
    return private, public


class Message(message.Message):

    def sign(self, private):

        e = hex_to_int(self.hash())
        r, s = 0, 0
        while r == 0 or s == 0:
            k = secrets.randbelow(N)
            point = CURVE.G * k
            r = point.x % N

            inv_k = mulinv(k, N)
            s = (inv_k * (e + r * private.int())) % N

        return message.Signature(r=r, s=s)

    def verify(self, signature, public):

        r, s = signature.r, signature.s
        if not (1 <= r < N and 1 <= s < N):
            return False

        e = hex_to_int(self.hash())
        w = mulinv(s, N)
        u1 = (e * w) % N
        u2 = (r * w) % N

        point = CURVE.G * u1 + public.point * u2
        return r % N == point.x % N

