import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from scripts.m2_apk_envelope import decrypt, encrypt


class ApkEnvelopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cls.private_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        cls.public_pem = key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def test_private_round_trip_is_bound_to_source_sha(self):
        source_sha = "a" * 40
        apk = b"PK\x03\x04review-build"
        envelope, manifest = encrypt(apk, source_sha, self.public_pem)
        self.assertNotIn(apk, envelope)
        self.assertEqual(decrypt(envelope, manifest, source_sha, self.private_pem), apk)
        with self.assertRaises(ValueError):
            decrypt(envelope, manifest, "b" * 40, self.private_pem)

    def test_corruption_is_rejected(self):
        source_sha = "a" * 40
        envelope, manifest = encrypt(b"PK\x03\x04review-build", source_sha, self.public_pem)
        altered = bytearray(envelope)
        altered[-1] ^= 1
        with self.assertRaises(ValueError):
            decrypt(bytes(altered), manifest, source_sha, self.private_pem)


if __name__ == "__main__":
    unittest.main()
