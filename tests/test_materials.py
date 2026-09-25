from clapback import materials
from clapback.room import OCTAVE_BANDS_HZ


def test_database_loads_and_is_sane():
    db = materials.load()
    assert len(db) > 10
    for m in db.values():
        assert len(m.alpha) == len(OCTAVE_BANDS_HZ)
        assert all(0 < a < 1 for a in m.alpha), m.id
