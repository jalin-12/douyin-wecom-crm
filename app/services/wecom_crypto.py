"""企业微信回调加解密（AES-256-CBC + SHA1 签名）。"""
import base64
import hashlib
import hmac
import os
import struct
import xml.etree.ElementTree as ET
from typing import Any

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class WeComCrypto:
    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        self.token = token
        self.corp_id = corp_id
        self.key = base64.b64decode(encoding_aes_key + "=")

    def signature(self, timestamp: str, nonce: str, encrypt: str) -> str:
        items = sorted([self.token, timestamp, nonce, encrypt])
        return hashlib.sha1("".join(items).encode()).hexdigest()

    def verify(self, signature: str, timestamp: str, nonce: str, encrypt: str) -> bool:
        expected = self.signature(timestamp, nonce, encrypt)
        return hmac.compare_digest(expected, signature or "")

    def decrypt(self, encrypt: str) -> str:
        cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.key[:16]))
        decryptor = cipher.decryptor()
        plain = decryptor.update(base64.b64decode(encrypt)) + decryptor.finalize()

        pad = plain[-1]
        if pad < 1 or pad > 32:
            raise ValueError("非法的补位长度")
        content = plain[:-pad]

        msg_len = struct.unpack(">I", content[16:20])[0]
        msg = content[20:20 + msg_len].decode("utf-8")
        receive_id = content[20 + msg_len:].decode("utf-8")
        if self.corp_id and receive_id != self.corp_id:
            raise ValueError("corpid 校验失败")
        return msg

    def encrypt(self, msg: str, timestamp: str, nonce: str) -> tuple[str, str]:
        raw = msg.encode("utf-8")
        payload = os.urandom(16) + struct.pack(">I", len(raw)) + raw + self.corp_id.encode()
        pad = 32 - len(payload) % 32
        payload += bytes([pad]) * pad

        cipher = Cipher(algorithms.AES(self.key), modes.CBC(self.key[:16]))
        encryptor = cipher.encryptor()
        encrypted = base64.b64encode(encryptor.update(payload) + encryptor.finalize()).decode()
        return encrypted, self.signature(timestamp, nonce, encrypted)


def parse_xml(xml_text: str) -> dict[str, Any]:
    """把企微回调 XML 解析成扁平 dict，尽量保留简短字段。"""
    root = ET.fromstring(xml_text)
    data: dict[str, Any] = {}
    for child in root:
        if len(child) > 0:
            data[child.tag] = parse_xml(ET.tostring(child, encoding="unicode"))
        else:
            data[child.tag] = (child.text or "").strip()
    return data
