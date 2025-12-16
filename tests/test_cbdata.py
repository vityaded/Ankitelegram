import uuid

from app.utils.cbdata import pack_uuid, unpack_uuid


def test_pack_unpack_roundtrip():
    original = str(uuid.uuid4())
    packed = pack_uuid(original)
    assert unpack_uuid(packed) == original


def test_packed_callback_length():
    deck_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    callback = f"ad_student:{pack_uuid(deck_id)}:{pack_uuid(user_id)}:0"
    assert len(callback) <= 64
