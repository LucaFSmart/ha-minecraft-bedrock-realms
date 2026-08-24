from custom_components.minecraft_bedrock_realms.exceptions import XboxLiveError


def test_known_xerr_code_maps_to_readable_message():
    err = XboxLiveError.from_response({"XErr": 2148916233, "Message": "raw"})
    assert err.xerr == 2148916233
    assert "no Xbox profile" in str(err)


def test_unknown_xerr_code_falls_back_to_generic_message():
    err = XboxLiveError.from_response({"XErr": 999999999})
    assert err.xerr == 999999999
    assert "999999999" in str(err)


def test_missing_xerr_field_still_produces_a_message():
    err = XboxLiveError.from_response({})
    assert err.xerr is None
    assert "Xbox Live rejected" in str(err)
