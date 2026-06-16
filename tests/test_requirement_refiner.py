from zenie_code.requirement_refiner import is_vague_request


def test_vague_symptom_routes_to_diagnosis():
    assert is_vague_request("aplikasi tidak bisa login")

def test_specific_edit_does_not_route_to_diagnosis():
    assert not is_vague_request("perbaiki fungsi login pada src/auth.py")
