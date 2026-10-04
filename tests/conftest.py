import pytest

from nirantar.bharat_fleet.world import make_world
from nirantar.dhanvantari.tier_c import fit_tier_c
from nirantar.records import to_frames
from nirantar.sanjaya.ensemble import P0
from nirantar.sanjaya.twin import Twin


@pytest.fixture(scope="session")
def world():
    return make_world(seed=7)


@pytest.fixture(scope="session")
def family_of(world):
    return {p: v.family for p, v in world.pns.items()}


@pytest.fixture(scope="session")
def history(world):
    """Five years of status-quo history with records."""
    return Twin(world, P0, 1825, seed=99, record=True).run()


@pytest.fixture(scope="session")
def frames(history):
    return to_frames(history.records)


@pytest.fixture(scope="session")
def model(frames, family_of):
    return fit_tier_c(frames["spells"], family_of)
